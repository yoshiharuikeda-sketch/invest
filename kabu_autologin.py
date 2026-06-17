"""
kabuステーション® 自動起動・ログイン・終了スクリプト
=====================================================
【使い方】
  python kabu_autologin.py              # 起動 + ログイン（デフォルト）
  python kabu_autologin.py --mode login    # 同上
  python kabu_autologin.py --mode shutdown # kabuステーション終了

【動作フロー（loginモード）】
  1. kabu APIが既に使えるならスキップ（ログイン済み）
  2. kabuステーションが未起動なら起動
  3. ログインダイアログを待つ
  4. 口座番号フィールドでEnter×2（ログイン開始）
  5. パスキー認証選択ウィンドウを待つ
  6. Tab×9 + Enter（2FA送信トリガー）
  7. GmailからOTPを取得
  8. OTPを入力して「続ける」ボタンを押す
  9. API確認でログイン完了を検証

【動作フロー（shutdownモード）】
  1. kabuステーションのメインウィンドウを探す
  2. WM_CLOSE を送信（グレースフルシャットダウン）
  3. 15秒待ってまだ起動していれば強制終了（taskkill）
"""

import argparse
import ctypes
import json
import os
import re
import time
import base64
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# GUI自動化
import pyautogui
import win32gui
import win32api
import win32con
import win32clipboard

pyautogui.FAILSAFE = False

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# =====================================================================
# 設定
# =====================================================================

DIR = Path(__file__).parent

# Gmail API
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = DIR / "credentials.json"
TOKEN_FILE       = DIR / "token.json"

# 2FAメール設定
MAIL_SENDER_FILTER  = "kabu.com"
MAIL_SUBJECT_FILTER = "認証"
CODE_PATTERN        = r"\b(\d{6})\b"
INVALID_CODES       = {"000000", "222228", "111111"}

# kabuステーション設定
KABUSTATION_EXE     = r"C:\Users\tropi\AppData\Local\kabuStation\KabuS.exe"
PROCESS_NAME        = "KabuS.exe"
KABU_API_BASE       = "http://localhost:18080/kabusapi"

STARTUP_WAIT_SEC    = 120   # 起動からAPIが使えるまでの最大待ち秒数
LOGIN_WAIT_SEC      = 90    # ログインダイアログ検出の最大待ち秒数
AUTH_WAIT_SEC       = 120   # 2FAメール到着の最大待ち秒数
AUTH_CHECK_INTERVAL = 4     # 2FAメール確認間隔（秒）
SHUTDOWN_WAIT_SEC   = 5     # WM_CLOSE/「はい」確定後、強制終了に移るまでの待ち秒数（旧15秒のムダ待ちを短縮）
PASSKEY_WAIT_SEC    = 30    # パスキー選択ウィンドウの最大待ち秒数

# ログ
LOG_FILE = DIR / "log_autologin.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger()


# =====================================================================
# プロセス管理
# =====================================================================

def is_kabustation_running() -> bool:
    """KabuS.exe が実行中か確認"""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/NH"],
        capture_output=True, text=True
    )
    return PROCESS_NAME in result.stdout


def launch_kabustation() -> bool:
    """kabuステーションを起動する"""
    exe = Path(KABUSTATION_EXE)
    if not exe.exists():
        log.error(f"実行ファイルが見つかりません: {exe}")
        return False
    log.info(f"kabuステーション起動: {exe}")
    subprocess.Popen([str(exe)])
    return True


def _confirm_exit_dialog(main_hwnd: int, timeout_sec: int = 8) -> bool:
    """WM_CLOSE後に出る終了確認ポップアップ（「終了しますか？」はい/いいえ・既定=はい）
    を「はい」で確定して正常終了させる。スクリーンロック/モニターオフ中でも効くよう
    PostMessage/UIA で操作する。

    検出は厳密に行う（端末など無関係な窓の誤検出を防ぐ）:
      ① main_hwnd が所有する有効なポップアップ（GW_ENABLEDPOPUP＝モーダル確認窓）
      ② ①が無ければ、同一プロセス(PID)かつ子に「はい」を持つ可視窓
    """
    import win32process
    try:
        _, main_pid = win32process.GetWindowThreadProcessId(main_hwnd)
    except Exception:
        main_pid = None

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        dlg = None

        # ① main_hwnd 所有の有効なポップアップ（モーダル確認窓）
        try:
            popup = win32gui.GetWindow(main_hwnd, win32con.GW_ENABLEDPOPUP)
            if popup and popup != main_hwnd and win32gui.IsWindowVisible(popup):
                dlg = popup
        except Exception:
            pass

        # ② 同一プロセス(PID)の WinForms 確認窓（端末等は別PIDなので除外される）
        if not dlg and main_pid is not None:
            found = [None]
            def _cb(hwnd, _):
                if found[0] or hwnd == main_hwnd or not win32gui.IsWindowVisible(hwnd):
                    return True
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    return True
                if pid == main_pid and "WindowsForms10.Window" in win32gui.GetClassName(hwnd):
                    found[0] = hwnd
                return True
            try:
                win32gui.EnumWindows(_cb, None)
            except Exception:
                pass
            dlg = found[0]

        if dlg:
            log.info(f"終了確認ダイアログ検出: hwnd={dlg} "
                     f"class={win32gui.GetClassName(dlg)} '{win32gui.GetWindowText(dlg)}'")
            # 子ウィンドウ列挙（診断 + ボタン特定）
            children = []
            def _enumc(ch, _):
                try:
                    children.append((ch, win32gui.GetClassName(ch), win32gui.GetWindowText(ch)))
                except Exception:
                    pass
                return True
            try:
                win32gui.EnumChildWindows(dlg, _enumc, None)
            except Exception:
                pass
            for ch, cls, txt in children:
                log.info(f"  子: hwnd={ch} class={cls} text='{txt}'")

            # 1) 「はい」を含む子ボタンに BM_CLICK
            yes = next((ch for ch, cls, txt in children if "はい" in txt), None)
            if yes:
                win32api.PostMessage(yes, 0x00F5, 0, 0)  # BM_CLICK
                log.info(f"終了確認: 「はい」にBM_CLICK hwnd={yes}")
                return True

            # 2) UIAで「はい」ボタンをInvoke
            try:
                from pywinauto import Application
                w = Application(backend="uia").connect(handle=dlg).window(handle=dlg)
                for pat in (".*はい.*", ".*OK.*"):
                    try:
                        btn = w.child_window(title_re=pat, control_type="Button")
                        if btn.exists(timeout=1):
                            btn.invoke()
                            log.info(f"終了確認: 「はい」をInvoke ({pat})")
                            return True
                    except Exception:
                        continue
            except Exception as e:
                log.info(f"終了確認UIA失敗: {e}")

            # 3) フォールバック: PostMessageでEnter送出（ロック安全・フォーカスを奪わない・既定=はい）
            #    ※ 実機検証(2026-06-06)では、この終了ダイアログのボタンは windowless 描画で
            #      BM_CLICK/UIA/Enter のいずれでも閉じず、結局 taskkill になった。
            #      そのため確実な高速化は SHUTDOWN_WAIT_SEC 短縮（15→5秒）で担保し、
            #      以下は将来ダイアログ仕様が変わった場合のベストエフォートとして残す。
            cef = [None]
            def _find_cef2(ch, _):
                if win32gui.GetClassName(ch) == "Chrome_RenderWidgetHostHWND":
                    cef[0] = ch
                    return False
                return True
            try:
                win32gui.EnumChildWindows(dlg, _find_cef2, None)
            except Exception:
                pass
            key_target = cef[0] or dlg
            win32api.PostMessage(key_target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
            time.sleep(0.1)
            win32api.PostMessage(key_target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
            log.info(f"終了確認: PostMessage Enter送出（{win32gui.GetClassName(key_target)} hwnd={key_target}）")
            return True

        time.sleep(0.5)

    log.info("終了確認ダイアログ未検出（出ないか検出失敗 → 強制終了にフォールバック）")
    return False


def shutdown_kabustation() -> bool:
    """
    kabuステーションを終了する。
    1. メインウィンドウに WM_CLOSE を送信
    2. 「終了しますか？」確認ポップアップに「はい」を送って正常終了させる
    3. 15秒待って終了しなければ taskkill /F で強制終了
    """
    if not is_kabustation_running():
        log.info("kabuステーションは既に終了しています")
        return True

    # メインウィンドウ（ログインダイアログではないウィンドウ）を探す
    main_hwnd = None

    def _enum(hwnd, _):
        nonlocal main_hwnd
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if "kabuステーション" in title and "ログイン" not in title:
            main_hwnd = hwnd
        return True

    win32gui.EnumWindows(_enum, None)

    if main_hwnd:
        log.info(f"メインウィンドウへ WM_CLOSE 送信: hwnd={main_hwnd}")
        win32gui.PostMessage(main_hwnd, win32con.WM_CLOSE, 0, 0)
        # 「終了しますか？」確認ポップアップ（既定=はい）に「はい」を送って正常終了させる
        time.sleep(1.0)
        _confirm_exit_dialog(main_hwnd)
    else:
        # ログイン画面のみの場合はそちらを閉じる
        login_hwnd = win32gui.FindWindow(None, "ログイン")
        if login_hwnd:
            log.info(f"ログインウィンドウへ WM_CLOSE 送信: hwnd={login_hwnd}")
            win32gui.PostMessage(login_hwnd, win32con.WM_CLOSE, 0, 0)

    # 終了を待つ
    deadline = time.time() + SHUTDOWN_WAIT_SEC
    while time.time() < deadline:
        time.sleep(2)
        if not is_kabustation_running():
            log.info("kabuステーション正常終了")
            return True

    # 強制終了
    log.warning(f"{SHUTDOWN_WAIT_SEC}秒後も終了しないため強制終了します")
    subprocess.run(["taskkill", "/F", "/IM", PROCESS_NAME], capture_output=True)
    time.sleep(3)

    if not is_kabustation_running():
        log.info("kabuステーション強制終了完了")
        return True
    else:
        log.error("kabuステーションを終了できませんでした")
        return False


# =====================================================================
# API確認
# =====================================================================

def _read_env(key: str) -> str:
    """'.env_windows' から指定キーの値を読み込む"""
    pw_file = DIR / ".env_windows"
    try:
        with open(pw_file, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip().rstrip("\r")
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().rstrip("\r")
    except Exception as e:
        log.error(f".env_windows 読み込み失敗: {e}")
    return ""


def _read_api_password() -> str:
    """'.env_windows' からAPIパスワードを読み込む"""
    return _read_env("KABU_API_PASSWORD")


def is_api_ready() -> bool:
    """kabu APIトークンが取得できるか（ログイン済み確認）。
    成功時は kabu_order.py と共有する .kabu_token.json にトークンを保存する。
    """
    import requests
    password = _read_api_password()
    if not password:
        return False
    try:
        resp = requests.post(
            f"{KABU_API_BASE}/token",
            json={"APIPassword": password},
            timeout=5,
        )
        if resp.status_code == 200:
            token = resp.json().get("Token")
            if token:
                today = datetime.now().strftime("%Y-%m-%d")
                token_cache = DIR / ".kabu_token.json"
                with open(token_cache, "w") as f:
                    json.dump({"date": today, "token": token}, f)
            return True
        return False
    except Exception:
        return False


# =====================================================================
# Gmail API
# =====================================================================

def get_gmail_service():
    """Gmail APIサービスを取得（初回はブラウザ認証）"""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json が見つかりません: {CREDENTIALS_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def fetch_2fa_code(service, since_dt: datetime, timeout_sec: int = AUTH_WAIT_SEC) -> str | None:
    """2FAコードが記載されたメールをポーリングして取得する"""
    deadline = time.time() + timeout_sec
    since_epoch_ms = int(since_dt.timestamp() * 1000)

    log.info(f"2FAメール待機中（最大{timeout_sec}秒）...")
    while time.time() < deadline:
        try:
            query = (f"from:{MAIL_SENDER_FILTER} subject:{MAIL_SUBJECT_FILTER} "
                     f"after:{int(since_dt.timestamp())}")
            results = service.users().messages().list(
                userId="me", q=query, maxResults=5
            ).execute()

            for msg_ref in results.get("messages", []):
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="full"
                ).execute()

                if int(msg.get("internalDate", 0)) < since_epoch_ms:
                    continue

                body = _extract_body(msg.get("payload", {}))
                candidates = [c for c in re.findall(CODE_PATTERN, body)
                              if c not in INVALID_CODES]
                if candidates:
                    code = candidates[0]
                    log.info(f"2FAコード取得: {code}")
                    return code

        except Exception as e:
            log.warning(f"Gmail取得エラー: {e}")

        time.sleep(AUTH_CHECK_INTERVAL)

    log.error("2FAコードの取得がタイムアウトしました")
    return None


def _extract_body(payload: dict) -> str:
    """メールペイロードから本文テキストを抽出"""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            elif "parts" in part:
                body += _extract_body(part)
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body


# =====================================================================
# GUI操作（SendInput / オレンジスキャン）
# =====================================================================

def _build_send_input():
    """SendInput API を使った OS レベルのマウスクリック関数を返す"""
    import ctypes, ctypes.wintypes
    INPUT_MOUSE      = 0
    MOUSEEVENTF_MOVE     = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP   = 0x0004
    MOUSEEVENTF_ABSOLUTE = 0x8000

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        _anonymous_ = ("_i",)
        _fields_ = [("type", ctypes.c_ulong), ("_i", _I)]

    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)

    def send_click(x, y):
        nx, ny = int(x * 65535 / sw), int(y * 65535 / sh)
        inputs = (INPUT * 3)()
        for i, flags in enumerate([MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                                    MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE,
                                    MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE]):
            inputs[i].type = INPUT_MOUSE
            inputs[i].mi.dx = nx
            inputs[i].mi.dy = ny
            inputs[i].mi.dwFlags = flags
        user32.SendInput(3, inputs, ctypes.sizeof(INPUT))

    return send_click


def _scan_orange_button(y_min: int, y_max: int, x_min: int = 1000, x_max: int = 1450):
    """
    画面上のオレンジ色ボタンをスクリーンショット+numpyで高速検出して中心座標を返す。
    pyautogui.pixel() のループ（数十秒）の代わりに1回の screenshot で完結する。
    """
    import numpy as np
    from PIL import ImageGrab

    # 対象領域だけキャプチャ（高速）
    region = (x_min, y_min, x_max, y_max)
    img = ImageGrab.grab(bbox=region)
    arr = np.array(img)  # shape: (height, width, 3) RGB

    # オレンジ条件: R>220, G<130, B<30
    mask = (arr[:, :, 0] > 220) & (arr[:, :, 1] < 130) & (arr[:, :, 2] < 30)
    ys_rel, xs_rel = np.where(mask)

    if len(xs_rel) == 0:
        return None, None

    # 絶対座標に変換
    xs_abs = xs_rel + x_min
    ys_abs = ys_rel + y_min
    return int((xs_abs.min() + xs_abs.max()) // 2), int((ys_abs.min() + ys_abs.max()) // 2)


def _force_foreground(hwnd: int):
    """AttachThreadInput を使ってウィンドウをフォアグラウンドにする（失敗は警告のみ）"""
    if not hwnd:
        log.warning("_force_foreground: hwnd=0、スキップ")
        return
    import ctypes
    import win32process
    try:
        fg = win32gui.GetForegroundWindow()
        fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
        my_tid = win32api.GetCurrentThreadId()
        ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, True)
        win32gui.SetForegroundWindow(hwnd)
        ctypes.windll.user32.AttachThreadInput(fg_tid, my_tid, False)
    except Exception as e:
        log.warning(f"SetForegroundWindow 失敗（続行）: {e}")
    time.sleep(0.8)


def _get_visible_window_handles() -> set:
    """現在表示されているトップレベルウィンドウのhwndセットを返す"""
    handles = set()
    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            handles.add(hwnd)
        return True
    win32gui.EnumWindows(_cb, None)
    return handles


def find_login_dialog(timeout_sec: int = LOGIN_WAIT_SEC):
    """ログインダイアログ（タイトル "ログイン"、幅>400px）をポーリングで探す"""
    from pywinauto import Desktop
    log.info(f"ログインダイアログ待機中（最大{timeout_sec}秒）...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            for w in Desktop(backend="uia").windows():
                try:
                    title = w.window_text()
                    if "ログイン" in title:
                        rect = w.rectangle()
                        if rect.width() > 400:
                            log.info(f"ログインダイアログ検出: '{title}' "
                                     f"L:{rect.left} T:{rect.top} R:{rect.right} B:{rect.bottom}")
                            time.sleep(8)  # CEFコンテンツが完全にロードされるまで待つ
                            return w
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(2)
    log.error("ログインダイアログが見つかりませんでした")
    return None


def submit_account_number() -> bool:
    """
    ログインダイアログ起動時、口座番号入力フィールドにフォーカスがある状態で
    口座番号を入力してEnterキーを2度押下してログイン処理を開始する。
    スクリーンロック中でも動作するようPostMessage経由で操作する。
    """
    account_number = _read_env("KABU_ACCOUNT_NUMBER")
    if not account_number:
        log.error("KABU_ACCOUNT_NUMBER が .env_windows に未設定")
        return False

    try:
        hwnd = win32gui.FindWindow(None, "ログイン")
        if not hwnd:
            log.error("ログインウィンドウが見つかりません")
            return False

        cef_hwnd = [None]
        def _find_cef(child_hwnd, _):
            if win32gui.GetClassName(child_hwnd) == "Chrome_RenderWidgetHostHWND":
                cef_hwnd[0] = child_hwnd
                return False
            return True
        try:
            win32gui.EnumChildWindows(hwnd, _find_cef, None)
        except Exception:
            pass

        target = cef_hwnd[0] or hwnd
        log.info(f"口座番号入力: {win32gui.GetClassName(target)} (hwnd={target})")

        # WM_CHAR で1文字ずつ入力（フォーカスは起動時から口座番号フィールドにある）
        for ch in account_number:
            win32api.PostMessage(target, win32con.WM_CHAR, ord(ch), 0)
            time.sleep(0.1)
        log.info(f"口座番号WM_CHAR入力完了（{len(account_number)}文字）")
        time.sleep(0.5)

        for _ in range(2):
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
            time.sleep(0.1)
            win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
            time.sleep(1.5)
        log.info("Enterキー×2押下完了")
        return True

    except Exception as e:
        log.error(f"口座番号送信失敗: {e}")
        return False


def _resend_login_enter() -> None:
    """ログイン送信のEnterがCEFに登録されず（フォーカス外れ等で）2FAが要求されない事象の
    リトライ用。口座番号は再入力せず、ログイン窓を一瞬だけ最前面化してEnterを再送する。
    （初回はフォーカス操作しない方針だが、失敗時のリトライに限り最前面化して確実に送る）"""
    try:
        hwnd = win32gui.FindWindow(None, "ログイン")
        if not hwnd:
            log.info("Enter再送: ログイン窓が見つからない（既に遷移済みの可能性）")
            return
        # 再送時のみ最前面化してCEFにキーボードフォーカスを当てる
        _force_foreground(hwnd)
        cef_hwnd = [None]
        def _find_cef(child_hwnd, _):
            if win32gui.GetClassName(child_hwnd) == "Chrome_RenderWidgetHostHWND":
                cef_hwnd[0] = child_hwnd
                return False
            return True
        try:
            win32gui.EnumChildWindows(hwnd, _find_cef, None)
        except Exception:
            pass
        target = cef_hwnd[0] or hwnd
        for _ in range(2):
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
            time.sleep(0.1)
            win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
            time.sleep(1.0)
        log.info(f"Enter再送完了（{win32gui.GetClassName(target)} hwnd={target}）")
    except Exception as e:
        log.info(f"Enter再送 失敗: {e}")


def find_passkey_dialog(known_handles: set, timeout_sec: int = PASSKEY_WAIT_SEC) -> int | None:
    """
    Enter×2後に表示されるパスキー認証選択ウィンドウを検出する。
    known_handles に含まれない新規の可視ウィンドウをポーリングで探す。
    """
    log.info(f"パスキー選択ウィンドウ待機中（最大{timeout_sec}秒）...")
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        current = []
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                current.append(hwnd)
            return True
        win32gui.EnumWindows(_cb, None)

        for hwnd in current:
            if hwnd in known_handles:
                continue
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            log.info(f"新規ウィンドウ検出: '{title}' hwnd={hwnd} size=({w}×{h})")
            if w > 300 and h > 200:
                log.info(f"パスキー選択ウィンドウ検出: '{title}' hwnd={hwnd} size=({w}×{h})")
                time.sleep(3)
                return hwnd
        time.sleep(2)

    log.error("パスキー選択ウィンドウが見つかりませんでした")
    return None


def handle_passkey_dialog(hwnd: int) -> bool:
    """
    パスキー選択画面で「パスキーなしで続行」を選択する。
    1. 「パスキーなしで続行」をUIAで直接Invoke（最優先）
    2. UIA失敗時は「パスキーを作成」にSetFocus → Tab×1 → Enter
    3. 最終フォールバック: オレンジボタン検出 → ホバー → Tab×1 → Enter

    ※ 2026-06-06: 「UIA Invokeを多数回リトライ」案は、リトライ中にパスキー
       ウィンドウのハンドルが無効化し、従来有効だった高速フォールバックが
       ウィンドウ消失後に走って失敗する回帰を起こしたため撤回（実績ある高速版に復帰）。
       併せて「パスキーウィンドウが既に消えている＝ログイン進行済み」を True 扱いに
       するガードを追加（最終的な成否は do_login のAPI確認が判定する）。
    """
    try:
        cef_hwnd = [None]
        def _find_cef(child_hwnd, _):
            if win32gui.GetClassName(child_hwnd) == "Chrome_RenderWidgetHostHWND":
                cef_hwnd[0] = child_hwnd
                return False
            return True
        try:
            win32gui.EnumChildWindows(hwnd, _find_cef, None)
        except Exception:
            pass
        target = cef_hwnd[0] or hwnd
        log.info(f"パスキー選択ウィンドウ: {win32gui.GetClassName(target)} (hwnd={target})")

        invoked = False

        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=hwnd)
            win = app.window(handle=hwnd)

            # 1. 「パスキーなしで続行」ボタンをUIAで直接Invoke（最優先）
            try:
                btn_skip = win.child_window(title_re=".*パスキーなし.*")
                if btn_skip.exists(timeout=2):
                    btn_skip.invoke()
                    log.info("UIA: 「パスキーなしで続行」をInvoke完了")
                    invoked = True
            except Exception as e:
                log.info(f"「パスキーなしで続行」Invoke失敗: {e}")

            # 2. 「パスキーを作成」にSetFocus → WM_SETFOCUS → Tab×1 → Enter
            if not invoked:
                btn = win.child_window(title="パスキーを作成", control_type="Button")
                btn.set_focus()
                log.info("UIA: 「パスキーを作成」にSetFocus完了")
                time.sleep(0.5)
                # Win32レベルのキーボードフォーカスをCEFに確立してからキー送信
                win32api.PostMessage(target, win32con.WM_SETFOCUS, 0, 0)
                time.sleep(0.3)
                win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_TAB, 0x000F0001)
                time.sleep(0.1)
                win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_TAB, 0xC00F0001)
                time.sleep(0.3)
                win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
                time.sleep(0.1)
                win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
                log.info("「パスキーを作成」フォーカス → Tab×1 → Enter 完了")

        except Exception as e:
            log.info(f"UIA 失敗（続行）: {e}")

        # 3. UIA完全失敗時: オレンジボタン検出 → WM_MOUSEMOVEホバー → Tab×1 → Enter
        if not invoked:
            if not win32gui.IsWindow(hwnd):
                log.info("パスキーウィンドウ消失（ログイン進行済みとみなしAPI確認へ）")
                return True
            win_rect = win32gui.GetWindowRect(hwnd)
            win_left, win_top, win_right, win_bottom = win_rect
            orange_x, orange_y = _scan_orange_button(
                y_min=win_top + 300,
                y_max=win_bottom - 50,
                x_min=win_left,
                x_max=win_right,
            )
            if orange_x is not None:
                client_pt = win32gui.ScreenToClient(target, (orange_x, orange_y))
                cx, cy = client_pt
                log.info(f"オレンジボタン検出: screen({orange_x}, {orange_y}) → client({cx}, {cy})")
            else:
                cx, cy = 580, 420
                log.warning(f"オレンジボタン未検出 → 固定座標: client({cx}, {cy})")
            lparam = win32api.MAKELONG(cx, cy)
            win32api.PostMessage(target, win32con.WM_MOUSEMOVE, 0, lparam)
            log.info(f"WM_MOUSEMOVEホバー: client({cx}, {cy})")
            time.sleep(0.3)
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_TAB, 0x000F0001)
            time.sleep(0.1)
            win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_TAB, 0xC00F0001)
            time.sleep(0.3)
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
            time.sleep(0.1)
            win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
            log.info("フォールバック: Tab×1 → Enter 完了")
        return True

    except Exception as e:
        # ウィンドウが既に消えている = ログインが先に進んだ可能性 → API確認に委ねる
        try:
            gone = not win32gui.IsWindow(hwnd)
        except Exception:
            gone = True
        if gone:
            log.info(f"パスキーウィンドウ消失（ログイン進行済みとみなしAPI確認へ）: {e}")
            return True
        log.error(f"パスキー選択画面操作失敗: {e}")
        return False


def enter_2fa_code(code: str, dialog) -> bool:
    """
    2FAコードをCEFのOTP入力フィールドに入力して送信する。
    スクリーンロック中でも動作するようPostMessage経由で操作する。

    Chrome_RenderWidgetHostHWND に WM_CHAR を直接送信することで
    フォーカス不要でCEFへのキー入力が可能。
    """
    try:
        hwnd = win32gui.FindWindow(None, "ログイン")
        if not hwnd:
            log.error("ログインウィンドウが見つかりません")
            return False

        # Chrome_RenderWidgetHostHWND（CEF描画ウィンドウ）を探す
        cef_hwnd = [None]
        def _find_cef(child_hwnd, _):
            if win32gui.GetClassName(child_hwnd) == "Chrome_RenderWidgetHostHWND":
                cef_hwnd[0] = child_hwnd
                return False
            return True
        try:
            win32gui.EnumChildWindows(hwnd, _find_cef, None)
        except Exception:
            pass

        target = cef_hwnd[0] or hwnd
        log.info(f"2FA入力対象: {win32gui.GetClassName(target)} (hwnd={target})")

        # 6桁コードをWM_CHARで1文字ずつ入力（カーソルは既にOTPフィールドにある）
        for char in code:
            win32api.PostMessage(target, win32con.WM_CHAR, ord(char), 0)
            time.sleep(0.05)
        log.info(f"コード入力（WM_CHAR）: {code}")
        time.sleep(0.3)

        # Enterキーで送信
        win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
        time.sleep(0.1)
        win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
        log.info("Enterキーで送信（WM_KEYDOWN）")
        return True

    except Exception as e:
        log.error(f"2FAコード入力失敗: {e}")
        return False


# =====================================================================
# メイン処理
# =====================================================================

# SetThreadExecutionState フラグ（スリープ抑制）
_ES_CONTINUOUS        = 0x80000000
_ES_SYSTEM_REQUIRED   = 0x00000001
_ES_DISPLAY_REQUIRED  = 0x00000002


def _prevent_sleep():
    """ログイン処理中にWindowsのスリープ・ディスプレイオフを禁止する"""
    ctypes.windll.kernel32.SetThreadExecutionState(
        _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
    )
    log.info("スリープ抑制: 有効")


def _allow_sleep():
    """スリープ禁止を解除する"""
    ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    log.info("スリープ抑制: 解除")


def _keep_awake_until(target_local: datetime):
    """target_local（naiveなローカル時刻）までスリープ抑制を維持し続ける。

    WakeToRun（タイマー復帰）が実機で不安定なため、午後ログイン後に決済・約定照会・
    レポート・自動終了(15:40)が走り終わるまでPCを起こし続け、復帰失敗による
    「kabuステーション持ち越し」を根絶する。ディスプレイは消えてよいので
    ES_DISPLAY_REQUIRED は付けない（システム稼働のみ維持）。
    """
    now = datetime.now()
    if target_local <= now:
        return
    wait_sec = (target_local - now).total_seconds()
    log.info(
        f"スリープ抑制を維持: {target_local.strftime('%H:%M')} まで"
        f"（約{int(wait_sec // 60)}分・WakeToRun非依存で午後の終了処理を保証）"
    )
    try:
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            # 定期的に再アサート（堅牢化）
            ctypes.windll.kernel32.SetThreadExecutionState(
                _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
            )
            time.sleep(min(30.0, max(1.0, deadline - time.time())))
    finally:
        _allow_sleep()
    log.info("スリープ抑制: 維持終了（午後の終了処理完了想定時刻に到達）")


def do_login(force: bool = False) -> bool:
    """kabuステーションを起動してログインする。
    force=True のときは APIトークンが取れても（取引セッション失効対策で）
    既存を終了してフル再ログインする。"""
    log.info("=" * 60)
    log.info(f"kabuステーション 自動ログイン開始{'（force再ログイン）' if force else ''}")
    log.info("=" * 60)

    # スリープ抑制を有効化（タスク実行中にPCが再スリープするのを防ぐ）
    _prevent_sleep()

    try:
        # 1. Gmail API 初期化
        try:
            service = get_gmail_service()
            log.info("Gmail API 接続OK")
        except Exception as e:
            log.error(f"Gmail API初期化失敗: {e}")
            return False

        # 2. 既にログイン済みなら終了（force時は強制再ログイン）
        if is_kabustation_running() and is_api_ready():
            if not force:
                log.info("kabuステーションは既にログイン済みです（APIトークン取得成功）")
                return True
            log.info("force指定 → ログイン済みだが強制的に再ログインします")

        # 3. 起動確認・必要に応じて再起動
        if is_kabustation_running():
            # force、または起動中だがAPIが使えない残骸 → 再起動してクリーンな状態にする
            reason = "force再ログイン" if force else "API使用不可（前回ログイン失敗の残骸）"
            log.info(f"kabuステーション再起動します（{reason}）")
            if not shutdown_kabustation():
                log.error("kabuステーション終了失敗 → 多重起動を防ぐためログイン中断")
                return False
            time.sleep(3)

        log.info("kabuステーション未起動 → 起動します")
        if not launch_kabustation():
            return False
        # 起動直後は少し待つ
        time.sleep(10)

        # 4. ログインダイアログを待つ
        dialog = find_login_dialog(timeout_sec=LOGIN_WAIT_SEC)
        if dialog is None:
            # ログインダイアログが出なかった = 既にログイン済みの可能性
            if is_api_ready():
                log.info("ログインダイアログなし → APIは正常（ログイン済み）")
                return True
            log.error("ログインダイアログが見つかりません")
            return False

        # 5. 口座番号フィールドでEnter×2（ログイン開始 → 2FAメール送信）
        login_time = datetime.now(timezone.utc)
        log.info("口座番号フィールドでEnter×2...")
        if not submit_account_number():
            return False

        # 6. 2FAコードをGmailから取得（Enter取りこぼし対策のリトライ付き）
        #    口座番号送信のEnterがCEFに登録されないとOTPが要求されず2FAが来ない事象への対策。
        #    30秒待っても未着なら、ログイン窓を最前面化してEnterを再送し再待機（最大3回=約90秒）。
        #    login_time は更新しない（遅延到着のOTP・再送で出たOTPのどちらも拾えるようにする）。
        code = None
        for _attempt in range(3):
            code = fetch_2fa_code(service, since_dt=login_time, timeout_sec=30)
            if code:
                break
            if _attempt < 2:
                log.info(f"2FA未着（試行{_attempt + 1}/3, 30秒）→ ログイン窓を最前面化してEnter再送")
                _resend_login_enter()
        if code is None:
            log.info("2FAコード未着（再送含め約90秒）→ 2FAスキップしてパスキー選択へ進む")
        else:
            # 7. 2FAフォームが表示されるまで待つ
            time.sleep(3)

            # 8. コードを入力して「続ける」ボタンを押す
            if not enter_2fa_code(code, dialog):
                log.error("2FAコード入力失敗")
                return False

        # 9. パスキー選択画面の読み込みを待つ（CEFウィンドウ内に表示される）
        log.info("パスキー選択画面読み込み待機（8秒）...")
        time.sleep(8)

        # 10. 「パスキーを作成」にSetFocus → Tab×1 → Enter（パスキー選択スキップ）
        log.info("パスキー選択画面で「パスキーなしで続行」クリック...")
        if not handle_passkey_dialog(dialog.handle):
            return False

        # 11. API確認でログイン完了を検証（最大STARTUP_WAIT_SEC秒リトライ）
        import requests
        password = _read_api_password()
        if not password:
            log.error("APIパスワードが読み込めません")
            return False

        log.info(f"APIサーバー待機中（最大{STARTUP_WAIT_SEC}秒）...")
        deadline = time.time() + STARTUP_WAIT_SEC
        while time.time() < deadline:
            time.sleep(5)
            try:
                resp = requests.post(
                    f"{KABU_API_BASE}/token",
                    json={"APIPassword": password},
                    timeout=5,
                )
                if resp.status_code == 200:
                    log.info("✅ API認証成功 - ログイン完了")
                    return True
                else:
                    log.warning(f"API認証失敗: {resp.status_code} {resp.text}（リトライ継続）")
            except Exception:
                pass  # まだAPI未起動、リトライ

        log.error(f"APIサーバーが{STARTUP_WAIT_SEC}秒以内に起動しませんでした")
        return False

    finally:
        # 成功・失敗どちらの場合もスリープ抑制を解除
        _allow_sleep()


def do_shutdown() -> bool:
    """kabuステーションを終了する"""
    log.info("=" * 60)
    log.info("kabuステーション 自動終了開始")
    log.info("=" * 60)
    return shutdown_kabustation()


def main():
    parser = argparse.ArgumentParser(description="kabuステーション 自動操作")
    parser.add_argument(
        "--mode",
        choices=["login", "shutdown"],
        default="login",
        help="login: 起動+ログイン（デフォルト）/ shutdown: 終了",
    )
    parser.add_argument(
        "--keep-awake-until",
        default=None,
        metavar="HH:MM",
        help="ログイン後、指定ローカル時刻までスリープ抑制を維持する"
             "（WakeToRun非依存の午後終了対策。未指定でも15時台ログインは自動で15:42まで維持）",
    )
    args = parser.parse_args()

    if args.mode == "shutdown":
        exit(0 if do_shutdown() else 1)

    success = do_login()

    # --- キープアウェイク対象時刻の決定 ---
    # WakeToRunが実機で不発のため、午後の引け処理ウィンドウにログインしたら
    # 自動終了(15:40)が終わる頃まで起こし続ける（ログイン成否に関わらず実施し、
    # 決済・自動終了が確実に起きている状態で走るようにする）。
    target = None
    now = datetime.now()
    if args.keep_awake_until:
        try:
            hh, mm = map(int, args.keep_awake_until.split(":"))
            t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if t > now:
                target = t
        except Exception as e:
            log.warning(f"--keep-awake-until の解釈に失敗（無視）: {e}")
    elif now.hour == 15 and now.minute < 40:
        # 午後ログイン(15:20想定)で自動有効化。15:42まで維持（15:40終了＋余裕）。
        target = now.replace(hour=15, minute=42, second=0, microsecond=0)

    if target:
        _keep_awake_until(target)

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
