"""
1321（野村日経225連動型上場投信）を1口だけ信用新規買いするテスト
明日の寄付き成行で執行される
確認後はkabuステーション画面から手動キャンセル可能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, get_board, send_order, API_PASSWORD, TOKEN_CACHE

import json

def main():
    print("=" * 60)
    print("  テスト発注: 1321（日経225ETF）１口 信用新規買い")
    print("  執行タイミング: 明日の寄付き成行")
    print("=" * 60)

    # トークンキャッシュ削除（再起動後の陳藐化防止）
    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    print("\n【認証】")
    try:
        token = get_token()
        print("  ✅ トークン取得成功")
    except Exception as e:
        print(f"  ❌ 認証失敗: {e}")
        return

    print("\n【板情報確認: 1321】")
    try:
        board = get_board(token, "1321")
        price = board.get("CurrentPrice") or board.get("CalcPrice", 0)
        print(f"  現在値: {price:,.0f}円 / 出来高: {board.get('TradingVolume', 'N/A')}口")
    except Exception as e:
        print(f"  ❌ 板情報取得失敗: {e}")
        return

    print("\n【発注、1321 信用新規買い 1口 寄付き成行")
    result = send_order(
        token=token,
        symbol="1321",
        side="2",           # 買い
        qty=1,
        order_type=1,       # 成行
        price=0,
        cash_margin=2,      # 信用新規
        front_order_type=10,  # 寄付き成行（明日の寄付き）
        dry_run=False,      # 実発注
    )

    print()
    if result and result.get("Result") == 0:
        print(f"  ✅ 発注成功！ OrderId: {result.get('OrderId')}")
        print()
        print("  ⚠️  注意: 明日の寄付きで執行されます")
        print("  キャンセルする場合はkabuステーション画面から注文取消してください")
    else:
        print(f"  ❌ 発注失敗: {result}")

if __name__ == "__main__":
    main()
