# -*- coding: utf-8 -*-
"""現在の信用建玉を一覧表示する（読み取り専用・発注なし）。
月曜の手動返済前に、実際に残っている建玉を確認するためのヘルパー。
kabuステーションが起動・ログイン済みのときに実行すること。

  python -X utf8 check_positions.py
"""
import os
import sys
import requests

BASE = "http://localhost:18080/kabusapi"


def load_env():
    pw = None
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env_windows"), os.path.join(here, ".env")):
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.startswith("KABU_API_PASSWORD"):
                    pw = line.split("=", 1)[1].strip()
    return pw


def main():
    pw = load_env()
    if not pw:
        print("KABU_API_PASSWORD が見つかりません (.env_windows)")
        sys.exit(1)
    try:
        r = requests.post(f"{BASE}/token", json={"APIPassword": pw}, timeout=5)
    except requests.exceptions.ConnectionError:
        print("kabuステーションに接続できません（起動・ログイン済みか確認してください）")
        sys.exit(1)
    if r.status_code != 200:
        print(f"トークン取得失敗: {r.status_code} {r.text}")
        sys.exit(1)
    headers = {"X-API-KEY": r.json()["Token"]}
    p = requests.get(f"{BASE}/positions?product=2", headers=headers, timeout=5)
    if p.status_code != 200:
        print(f"建玉照会失敗: {p.status_code} {p.text}")
        sys.exit(1)
    data = [x for x in p.json() if float(x.get("LeavesQty", 0)) > 0]
    if not data:
        print("信用建玉はありません（すべて決済済み）。")
        return
    print(f"=== 現在の信用建玉: {len(data)}件 ===")
    print(f"{'銘柄':<8}{'方向':<14}{'残数量':>8}{'建値':>10}{'評価損益':>12}")
    total = 0.0
    for x in data:
        side = "買建(LONG)" if x.get("Side") == "2" else "売建(SHORT)"
        sym = x.get("Symbol", "")
        qty = x.get("LeavesQty", 0)
        price = x.get("Price", 0)
        pl = x.get("ProfitLoss", 0) or 0
        total += float(pl)
        mark = "  ← 制度信用SHORT(手動返済要)" if x.get("Side") != "2" else ""
        print(f"{sym:<8}{side:<14}{qty:>8}{price:>10}{pl:>12,.0f}{mark}")
    print(f"{'合計評価損益':<30}{total:>12,.0f} 円")


if __name__ == "__main__":
    main()
