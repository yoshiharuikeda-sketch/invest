"""
パスキー選択画面でTabキーを100回押下してフォーカス移動を目視確認するテスト
kabuStationのログインダイアログが表示された状態で実行すること
"""
import time
import win32gui
import win32api
import win32con

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

print("3秒後にTabキー100回送信を開始します...")
time.sleep(3)

target = find_target()
if target:
    for i in range(1, 101):
        win32api.PostMessage(target, win32con.WM_KEYDOWN, win32con.VK_TAB, 0x000F0001)
        time.sleep(0.05)
        win32api.PostMessage(target, win32con.WM_KEYUP, win32con.VK_TAB, 0xC00F0001)
        time.sleep(0.2)
        if i % 10 == 0:
            print(f"{i}回完了")
    print("100回完了")
