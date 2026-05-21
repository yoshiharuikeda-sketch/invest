"""
1321（野村日経225連動型上場投信）を1口だけ信用新規買い → 即キャンセル
sendorder と cancelorder の両APIをテスト
ポジションは残らない
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, get_board, send_order, cancel_order, API_PASSWORD, TOKEN_CACHE, KABU_API_BASE
import requests

def main():
    print("=" * 60)
    print("  テスト発注: 1321（日経225ETF）１口 信用新規買い → 即キャンセル")
    print("  ※ 発注直後にキャンセルするためポジションは残りません")
    print("=" * 60)

    # トークンキャッシュ削除
    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    print("\n【1. 認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ 認証失敗: {e}")
        return

    print("\n【2. 板情報確認: 1321】")
    try:
        board = get_board(token, "1321")
        price = board.get("CurrentPrice") or board.get("CalcPrice", 0)
        print(f"  現在値: {price:,.0f}円 / 出来高: {board.get('TradingVolume', 'N/A')}口")
    except Exception as e:
        print(f"  ❌ 板情報取得失敗: {e}")
        return

    print("\n【3. 発注、1321 信用新規買い 1口 引成（本日大引け）")
    result = send_order(
        token=token,
        symbol="1321",
        side="2",              # 買い
        qty=1,
        order_type=1,          # 成行
        price=0,
        cash_margin=2,         # 信用新規
        front_order_type=13,   # 引成（本日15:30大引け）
        dry_run=False,
    )

    if not result or result.get("Result") != 0:
        print(f"  ❌ 発注失敗: {result}")
        return

    order_id = result.get("OrderId")
    print(f"  ✅ 発注成功！ OrderId: {order_id}")

    print(f"\n【4. 即キャンセル】OrderId: {order_id}")
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {"OrderId": order_id, "Password": API_PASSWORD}
    try:
        resp = requests.put(f"{KABU_API_BASE}/cancelorder", headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        cancel_result = resp.json()
        if cancel_result.get("Result") == 0:
            print(f"  ✅ キャンセル成功！ ポジションは残っていません")
        else:
            print(f"  ⚠️  キャンセル結果: {cancel_result}")
            print(f"     kabuステーション画面から手動でキャンセルしてください")
    except Exception as e:
        print(f"  ❌ キャンセル失敗: {e}")
        print(f"     kabuステーション画面から手動でキャンセルしてください")

    print("\n=== テスト完了 ===")

if __name__ == "__main__":
    main()
