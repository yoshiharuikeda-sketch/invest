"""
sendorder 4001005エラーの切り分け: 現物 vs 信用
"""
import sys
import os
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, TOKEN_CACHE, KABU_API_BASE, API_PASSWORD

CANDIDATES = [
    # 信用新規（修正済みパラメータ）
    {"label": "信用新規 (CashMargin=2, DelivType=0, FundType='  ')",
     "CashMargin": 2, "DelivType": 0, "FundType": "  ", "AccountType": 4},
    # 現物（元のパラメータでテスト）
    {"label": "現物 (CashMargin=1, DelivType=2, FundType='  ')",
     "CashMargin": 1, "DelivType": 2, "FundType": "  ", "AccountType": 4},
    # 現物（DelivType=0）
    {"label": "現物 (CashMargin=1, DelivType=0, FundType='  ')",
     "CashMargin": 1, "DelivType": 0, "FundType": "  ", "AccountType": 4},
]

def try_order(token, c):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {
        "Password":       API_PASSWORD,
        "Symbol":         "1321",
        "Exchange":       1,
        "SecurityType":   1,
        "Side":           "2",
        "CashMargin":     c["CashMargin"],
        "DelivType":      c["DelivType"],
        "FundType":       c["FundType"],
        "AccountType":    c["AccountType"],
        "Qty":            1,
        "FrontOrderType": 10,
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
    print("=" * 65)
    print("  sendorder 切り分けテスト: 1321 1口 寄付き成行")
    print("=" * 65)

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
            cr = cancel(token, order_id)
            if cr.get("Result") == 0:
                print(f"  ✅ 即キャンセル成功 → ポジションなし")
            else:
                print(f"  ⚠️  キャンセル: {cr} → kabuステーション画面から手動キャンセル")
            print("\n=== 完了 ===")
            return
        else:
            code = result.get('Code')
            msg = result.get('Message', '')
            print(f"  ❌ ({status}): Code={code}")
            if code != 4001005:
                print(f"  ⚠️  エラーコードが変わった: {msg}")
        print()

    print("=== 全パターン失敗 ===")
    print()
    print("次のコマンドでkabuSログを確認してください:")
    print(r"  dir $env:APPDATA\kabuStation")
    print(r"  Get-ChildItem $env:APPDATA\kabuStation -Recurse -Filter '*.log' | sort LastWriteTime -Desc | select -First 5")

if __name__ == "__main__":
    main()
