"""
パスキー選択画面でTabキーを100回押下してフォーカス移動を目視確認するテスト
kabuStationの起動からパスキー選択画面まで自動で進め、その後Tab×100を送信する
"""
import sys
import time
import win32gui
import win32api
import win32con
from pathlib import Path

# kabu_autologin.pyの関数を再利用
sys.path.insert(0, str(Path(__file__).parent))
from kabu_autologin import (
    launch_kabustation, is_kabustation_running,
    get_gmail_service,
    submit_account_number,
    find_login_dialog, log
)


def find_target():
    hwnd = win32gui.FindWindow(None, "ログイン")
    if not hwnd:
        print("ログインウィンドウが見つかりません")
        return None

    cef_hwnd = [None]
    def _find_cef(child, _):
        if win32gui.GetClassName(child) == "Chrome_RenderWidgetHostHWND":
            cef_hwnd[0] = child
            return False
        return True
    try:
        win32gui.EnumChildWindows(hwnd, _find_cef, None)
    except Exception:
        pass

    target = cef_hwnd[0] or hwnd
    cls = win32gui.GetClassName(target)
    print(f"送信先: {cls} (hwnd={target})")
    return target


def main():
    # 1. Gmail API初期化
    print("Gmail API 初期化中...")
    try:
        service = get_gmail_service()
        print("Gmail API 接続OK")
    except Exception as e:
        print(f"Gmail API初期化失敗: {e}")
        return

    # 2. kabuStation起動
    if not is_kabustation_running():
        print("kabuStation起動中...")
        if not launch_kabustation():
            return
        time.sleep(10)
    else:
        print("kabuStationは既に起動中")

    # 3. ログインダイアログ待機
    print("ログインダイアログ待機中...")
    dialog = find_login_dialog()
    if dialog is None:
        print("ログインダイアログが見つかりません")
        return

    # 4. 口座番号入力 → Enter×2
    print("口座番号入力 → Enter×2...")
    if not submit_account_number():
        return

    # 5. パスキー選択画面の読み込み待機（2FAスキップ、仮テスト用）
    print("パスキー選択画面待機中（10秒）...")
    time.sleep(10)

    # 8. Shift+Tab×2 + Enter 送信
    print("=== Shift+Tab×2 + Enter 送信 ===")
    target = find_target()
    if not target:
        return

    # Shiftを押しっぱなしでTab×2
    win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_SHIFT, 0x002A0001)
    time.sleep(0.05)
    for i in range(2):
        win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_TAB, 0x000F0001)
        time.sleep(0.1)
        win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_TAB, 0xC00F0001)
        time.sleep(0.3)
        print(f"Tab {i+1}回完了")
    win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_SHIFT, 0xC02A0001)

    time.sleep(0.3)
    win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0x001C0001)
    time.sleep(0.1)
    win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_RETURN, 0xC01C0001)
    print("Enter送信完了")


if __name__ == "__main__":
    main()
