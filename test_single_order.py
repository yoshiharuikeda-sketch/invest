"""
sendorder 調査: MarginTradeType（信用取引区分）を追加
1=制度信用, 2=一般信用(長期), 3=一般信用(デイトレ)
発注成功した場合は即キャンセル
"""
import sys
import os
import json
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, TOKEN_CACHE, KABU_API_BASE, API_PASSWORD

def try_order(token, body):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    resp = requests.post(f"{KABU_API_BASE}/sendorder", headers=headers, json=body, timeout=10)
    return resp.status_code, resp.json()

def cancel(token, order_id):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {"OrderId": order_id, "Password": API_PASSWORD}
    resp = requests.put(f"{KABU_API_BASE}/cancelorder", headers=headers, json=body, timeout=10)
    return resp.json()

def main():
    print("=" * 65)
    print("  MarginTradeType 追加テスト: 1617 信用新規買い 1口 寄付き")
    print("=" * 65)

    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    print("\n【認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ {e}")
        return

    base = {
        "Password":        API_PASSWORD,
        "Symbol":          "1617",
        "Exchange":        1,
        "SecurityType":    1,
        "Side":            "2",
        "CashMargin":      2,
        "DelivType":       0,
        "FundType":        "  ",
        "AccountType":     4,
        "Qty":             1,
        "FrontOrderType":  10,
        "Price":           0,
        "ExpireDay":       0,
    }

    candidates = [
        ("MarginTradeType=1 制度信用",           {**base, "MarginTradeType": 1}),
        ("MarginTradeType=2 一般信用(長期)",      {**base, "MarginTradeType": 2}),
        ("MarginTradeType=3 一般信用(デイトレ)",    {**base, "MarginTradeType": 3}),
    ]

    print()
    for label, body in candidates:
        print(f"--- {label} ---")
        status, result = try_order(token, body)
        if status == 200 and result.get("Result") == 0:
            order_id = result.get("OrderId")
            print(f"  ✅ 発注成功! OrderId={order_id}")
            cr = cancel(token, order_id)
            if cr.get("Result") == 0:
                print(f"  ✅ 即キャンセル成功 → ポジションなし")
            else:
                print(f"  ⚠️  キャンセル: {cr} → kabuステーション画面から手動キャンセル")
            print("\n=== 正解発見! ===")
            return
        else:
            code = result.get('Code')
            msg = result.get('Message', '')
            print(f"  ❌ ({status}): Code={code}: {msg}")
        print()

    print("=== 全パターン失敗 ===")

if __name__ == "__main__":
    main()
