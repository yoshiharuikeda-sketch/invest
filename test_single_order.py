"""
sendorder 調査:
- 現物 FundType=AA で通るか
- 本番銘柄1617で信用新規が通るか
発注成功した場合は即キャンセルする
"""
import sys
import os
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, TOKEN_CACHE, KABU_API_BASE, API_PASSWORD

CANDIDATES = [
    # 「預り区分が未設定」を修正: 現物 + FundType=AA
    {"label": "現物 1321 FundType=AA",
     "Symbol": "1321", "CashMargin": 1, "DelivType": 2, "FundType": "AA", "AccountType": 4},
    # 本番銘柄で信用新規を試行（1617=食品）
    {"label": "信用新規 1617 DelivType=0 FundType='  '",
     "Symbol": "1617", "CashMargin": 2, "DelivType": 0, "FundType": "  ", "AccountType": 4},
    {"label": "信用新規 1617 DelivType=0 FundType=AA",
     "Symbol": "1617", "CashMargin": 2, "DelivType": 0, "FundType": "AA", "AccountType": 4},
]

def try_order(token, c):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {
        "Password":       API_PASSWORD,
        "Symbol":         c["Symbol"],
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
    print("  sendorder 調査: 現物/信用 × 複数銘柄")
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
                print(f"  ⚠️  キャンセル: {cr}")
                print(f"     kabuステーション画面から手動キャンセルしてください")
        else:
            code = result.get('Code')
            msg = result.get('Message', '')
            marker = "⚠️  エラーコード変化!" if code != 4001005 else ""
            print(f"  ❌ ({status}): Code={code} {marker}")
            if msg:
                print(f"       {msg}")
        print()

    print("─" * 65)
    print("kabuSログの確認:")
    print(r"  Get-ChildItem $env:APPDATA\kabuStation -Recurse -Filter '*.log' | sort LastWriteTime -Desc | select -First 3 | % { Write-Host $_.FullName; Get-Content $_.FullName -Tail 30 }")

if __name__ == "__main__":
    main()
