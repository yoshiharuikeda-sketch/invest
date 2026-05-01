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
SHUTDOWN_WAIT_SEC   = 15    # WM_CLOSE後に強制終了するまでの待ち秒数
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


def shutdown_kabustation() -> bool:
    """
    kabuステーションを終了する。
    1. メインウィンドウに WM_CLOSE を送信
    2. 15秒待って終了しなければ taskkill /F で強制終了
    """
    if not is_kabustation_running():
        log.info("kabuステーションは既に終了しています")
        return True

    # メインウィンドウ（ログインダイアログではないウィンドウ）を探す
    main_hwnd = None

    def _enum(hwnd, _):
        nonlocal main_hwnd
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if "kabuステーション" in title and "ログイン" not in title:
            main_hwnd = hwnd

    win32gui.EnumWindows(_enum, None)

    if main_hwnd:
        log.info(f"メインウィンドウへ WM_CLOSE 送信: hwnd={main_hwnd}")
        win32gui.PostMessage(main_hwnd, win32con.WM_CLOSE, 0, 0)
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
    """kabu APIトークンが取得できるか（ログイン済み確認）"""
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
        return resp.status_code == 200
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
    パスキー認証選択画面でTab×9、Enterを押下してパスキーをスキップし2FA送信を開始する。
    スクリーンロック中でも動作するようPostMessage経由で操作する。
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
        log.info(f"パスキー選択ウィンドウ操作: {win32gui.GetClassName(target)} (hwnd={target})")

        win32api.PostMessage(target, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        win32api.PostMessage(target, win32con.WM_SETFOCUS, 0, 0)
        time.sleep(0.3)

        # DOM起点クリックでフォーカスの起点を作る
        target_rect = win32gui.GetWindowRect(target)
        tw = target_rect[2] - target_rect[0]
        th = target_rect[3] - target_rect[1]
        cx, cy = int(tw * 0.50), int(th * 0.50)
        c_lparam = win32api.MAKELONG(cx, cy)
        win32api.PostMessage(target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, c_lparam)
        time.sleep(0.1)
        win32api.PostMessage(target, win32con.WM_LBUTTONUP, 0, c_lparam)
        log.info(f"DOM起点クリック: client({cx}, {cy})")
        time.sleep(0.5)

        # Tab×8回でボタンにフォーカスを移動
        for i in range(8):
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_TAB, 0x000F0001)
            time.sleep(0.1)
            win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_TAB, 0xC00F0001)
            time.sleep(0.15)
        log.info("Tabキー×8回完了")
        time.sleep(0.3)

        # Enter（2FA送信トリガー）
        win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
        time.sleep(0.1)
        win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
        log.info("Enterキー押下（パスキー選択完了 → 2FA送信）")
        return True

    except Exception as e:
        log.error(f"パスキー選択ウィンドウ操作失敗: {e}")
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

        # CEFウィンドウをアクティブ化
        win32api.PostMessage(target, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        win32api.PostMessage(target, win32con.WM_SETFOCUS, 0, 0)
        time.sleep(0.3)

        # ウィンドウ中央を1回クリックしてCEF DOM内にフォーカスの起点を作る
        # （WM_SETFOCUSだけではDOMフォーカスが入らないためTabが効かない）
        target_rect = win32gui.GetWindowRect(target)
        tw2 = target_rect[2] - target_rect[0]
        th2 = target_rect[3] - target_rect[1]
        cx = int(tw2 * 0.50)
        cy = int(th2 * 0.50)
        c_lparam = win32api.MAKELONG(cx, cy)
        win32api.PostMessage(target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, c_lparam)
        time.sleep(0.1)
        win32api.PostMessage(target, win32con.WM_LBUTTONUP, 0, c_lparam)
        log.info(f"DOM起点クリック: client({cx}, {cy})")
        time.sleep(0.5)

        # 既存テキストをBACKSPACEで削除（念のため）
        for _ in range(8):
            win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_BACK, 0)
            time.sleep(0.03)

        # 6桁コードをWM_CHARで1文字ずつ入力
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


def do_login() -> bool:
    """kabuステーションを起動してログインする"""
    log.info("=" * 60)
    log.info("kabuステーション 自動ログイン開始")
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

        # 2. 既にログイン済みなら終了
        if is_kabustation_running() and is_api_ready():
            log.info("kabuステーションは既にログイン済みです（APIトークン取得成功）")
            return True

        # 3. 未起動なら起動
        if not is_kabustation_running():
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

        # 5. 口座番号フィールドでEnter×2（ログイン開始 → パスキー選択画面が表示される）
        log.info("口座番号フィールドでEnter×2...")
        if not submit_account_number():
            return False

        # 6. パスキー選択画面の読み込みを待つ（CEFウィンドウ内に表示される）
        log.info("パスキー選択画面読み込み待機（5秒）...")
        time.sleep(5)

        # 7. Tab×9 + Enter（2FA送信トリガー）- 既存のログインダイアログに送信
        login_time = datetime.now(timezone.utc)
        log.info("パスキー選択画面でTab×9 + Enter（2FA送信）...")
        if not handle_passkey_dialog(dialog.handle):
            return False

        # 9. 2FAコードをGmailから取得
        code = fetch_2fa_code(service, since_dt=login_time)
        if code is None:
            log.error("2FAコード取得失敗 → 自動ログイン中断")
            return False

        # 10. 2FAフォームが表示されるまで待つ
        time.sleep(3)

        # 11. コードを入力して「続ける」ボタンを押す
        if not enter_2fa_code(code, dialog):
            log.error("2FAコード入力失敗")
            return False

        # 12. API確認でログイン完了を検証（最大STARTUP_WAIT_SEC秒リトライ）
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
                    log.warning(f"API認証失敗: {resp.status_code} {resp.text}")
                    return False
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
    args = parser.parse_args()

    if args.mode == "shutdown":
        success = do_shutdown()
    else:
        success = do_login()

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
