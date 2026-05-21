"""
sendorder 4001005エラーの原因パラメータを特定する
発注成功した場合は即キャンセルする
"""
import sys
import os
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, TOKEN_CACHE, KABU_API_BASE, API_PASSWORD

# 試すパラメータ組み合わせ
CANDIDATES = [
    # AccountTypeを変える（FundType=" ", DelivType=0固定）
    {"label": "AccountType=2",  "AccountType": 2,  "FundType": "  ", "DelivType": 0, "FrontOrderType": 10, "SecurityType": 1},
    {"label": "AccountType=4",  "AccountType": 4,  "FundType": "  ", "DelivType": 0, "FrontOrderType": 10, "SecurityType": 1},
    {"label": "AccountType=0",  "AccountType": 0,  "FundType": "  ", "DelivType": 0, "FrontOrderType": 10, "SecurityType": 1},
    # FrontOrderTypeを変える（AccountType=2で試行）
    {"label": "FrontOrderType=1", "AccountType": 2, "FundType": "  ", "DelivType": 0, "FrontOrderType": 1,  "SecurityType": 1},
    {"label": "FrontOrderType=2", "AccountType": 2, "FundType": "  ", "DelivType": 0, "FrontOrderType": 2,  "SecurityType": 1},
]

def try_order(token, params):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {
        "Password":       API_PASSWORD,
        "Symbol":         "1321",
        "Exchange":       1,
        "SecurityType":   params["SecurityType"],
        "Side":           "2",
        "CashMargin":     2,
        "DelivType":      params["DelivType"],
        "FundType":       params["FundType"],
        "AccountType":    params["AccountType"],
        "Qty":            1,
        "FrontOrderType": params["FrontOrderType"],
        "Price":          0,
        "ExpireDay":      0,
    }
    resp = requests.post(f"{KABU_API_BASE}/sendorder", headers=headers, json=body, timeout=10)
    return resp.status_code, resp.json()

def cancel(token, order_id):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {"OrderId": order_id, "Password": API_PASSWORD}
    resp = requests.put(f"{KABU_API_BASE}/cancelorder", headers=headers, json=body, timeout=10)
    return resp.json()

def main():
    print("=" * 60)
    print("  sendorder パラメータ調査: 1321 信用新規買い 1口")
    print("=" * 60)

    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    print("\n【認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ {e}")
        return

    print()
    for c in CANDIDATES:
        print(f"--- {c['label']} ---")
        status, result = try_order(token, c)
        if status == 200 and result.get("Result") == 0:
            order_id = result.get("OrderId")
            print(f"  ✅ 発注成功! OrderId={order_id}")
            print(f"  → 正解: {c['label']}, AccountType={c['AccountType']}, FrontOrderType={c['FrontOrderType']}")
            cr = cancel(token, order_id)
            if cr.get("Result") == 0:
                print(f"  ✅ 即キャンセル成功")
            else:
                print(f"  ⚠️  キャンセル: {cr} → kabuステーション画面から手動キャンセルしてください")
            print("\n=== 完了 ===")
            return
        else:
            print(f"  ❌ ({status}): Code={result.get('Code')}, Msg={result.get('Message')}")
        print()

    print("=== 全パターン失敗 — kabuSログを確認してください ===")

if __name__ == "__main__":
    main()
