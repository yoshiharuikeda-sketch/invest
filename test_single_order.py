"""
sendorder 調査: FundTypeを完全に省略 + Swagger仕様確認
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
    print("  sendorder 調査 + Swagger仕様確認")
    print("=" * 65)

    # --- Swaggerから必須パラメータを確認 ---
    print("\n【Swagger 仕様書】")
    try:
        r = requests.get(f"{KABU_API_BASE}/swagger/kabustation_order_summary.json", timeout=5)
        if r.status_code == 200:
            spec = r.json()
            sendorder_schema = (
                spec.get("paths", {})
                    .get("/sendorder", {})
                    .get("post", {})
                    .get("requestBody", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
            )
            required = sendorder_schema.get("required", [])
            props = list(sendorder_schema.get("properties", {}).keys())
            print(f"  必須フィールド: {required}")
            print(f"  全フィールド: {props}")
        else:
            print(f"  Swagger取得失敗: {r.status_code}")
            # 別のURLを試行
            for url in ["/swagger/index.html", "/swagger", "/kabusapi/swagger"]:
                r2 = requests.get(f"http://localhost:18080{url}", timeout=3)
                if r2.status_code == 200:
                    print(f"  Swagger URL発見: http://localhost:18080{url}")
                    break
    except Exception as e:
        print(f"  Swaggerエラー: {e}")

    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    print("\n【認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ {e}")
        return

    # 共通ベース
    base = {
        "Password":       API_PASSWORD,
        "Symbol":         "1617",
        "Exchange":       1,
        "SecurityType":   1,
        "Side":           "2",
        "CashMargin":     2,
        "DelivType":      0,
        "AccountType":    4,
        "Qty":            1,
        "FrontOrderType": 10,
        "Price":          0,
        "ExpireDay":      0,
    }

    candidates = [
        ("FundTypeを1617から完全省略",     {**base}),
        ("FundType=None (null)",     {**base, "FundType": None}),
        ("FundType='AA' 1617",       {**base, "FundType": "AA"}),
    ]

    print()
    for label, body in candidates:
        print(f"--- {label} ---")
        print(f"    送信ベイ: {json.dumps({k:v for k,v in body.items() if k != 'Password'}, ensure_ascii=False)}")
        status, result = try_order(token, body)
        if status == 200 and result.get("Result") == 0:
            order_id = result.get("OrderId")
            print(f"  ✅ 発注成功! OrderId={order_id}")
            cr = cancel(token, order_id)
            print(f"  キャンセル: {'OK' if cr.get('Result')==0 else cr}")
            print("\n=== 正解パラメータ特定! ===")
            return
        else:
            print(f"  ❌ ({status}): Code={result.get('Code')} {result.get('Message','')}")
        print()

    print("=== 全パターン失敗 ===")

if __name__ == "__main__":
    main()
