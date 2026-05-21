"""
1321（野村日経225ETF）を使ってsendorderのパラメータ正しい組み合わせを特定する
発注成功した場合は即キャンセルする
"""
import sys
import os
import json
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kabu_order import get_token, get_board, TOKEN_CACHE, KABU_API_BASE, API_PASSWORD

# 試すパラメータ組み合わせ
CANDIDATES = [
    {"DelivType": 0, "FundType": "  "},   # 指定なし（元の値のDelivTypeだけ修正）
    {"DelivType": 0, "FundType": "AA"},   # 保護預かり
    {"DelivType": 0, "FundType": "02"},   # 信用代用有価証券
    {"DelivType": 0, "FundType": ""},     # 空文字列
]

def try_order(token, delit_type, fund_type):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {
        "Password":       API_PASSWORD,
        "Symbol":         "1321",
        "Exchange":       1,
        "SecurityType":   1,
        "Side":           "2",
        "CashMargin":     2,
        "DelivType":      delit_type,
        "FundType":       fund_type,
        "AccountType":    4,
        "Qty":            1,
        "FrontOrderType": 10,
        "Price":          0,
        "ExpireDay":      0,
    }
    print(f"    送信: DelivType={delit_type}, FundType={repr(fund_type)}")
    resp = requests.post(f"{KABU_API_BASE}/sendorder", headers=headers, json=body, timeout=10)
    return resp.status_code, resp.json()

def cancel(token, order_id):
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {"OrderId": order_id, "Password": API_PASSWORD}
    resp = requests.put(f"{KABU_API_BASE}/cancelorder", headers=headers, json=body, timeout=10)
    return resp.json()

def main():
    print("=" * 60)
    print("  sendorder パラメータ調査: 1321 信用新規買い 1口 寄付き")
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
        label = f"DelivType={c['DelivType']}, FundType={repr(c['FundType'])}"
        print(f"--- 試行: {label} ---")
        status, result = try_order(token, c["DelivType"], c["FundType"])
        if status == 200 and result.get("Result") == 0:
            order_id = result.get("OrderId")
            print(f"  ✅ 発注成功! OrderId={order_id}")
            print(f"  → 正しい組み合わせ: {label}")
            cr = cancel(token, order_id)
            if cr.get("Result") == 0:
                print(f"  ✅ 即キャンセル成功")
            else:
                print(f"  ⚠️  キャンセル結果: {cr} → 手動でキャンセルしてください")
            print("\n=== 完了: 正しいパラメータが見つかりました ===")
            return
        else:
            print(f"  ❌ 失敗 ({status}): {result}")
        print()

    print("=== 全ての組み合わせが失敗しました ===")

if __name__ == "__main__":
    main()
