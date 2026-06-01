"""
kabuStation(R) API 約定照会スクリプト
引成決済後（15:32頃）に実行し、今日の全約定価格を fills_YYYYMMDD.csv に保存する。
"""

import sys
import csv
import logging
import requests
from datetime import date
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
LOG_FILE   = SCRIPT_DIR / "log_fills.txt"
BASE_URL   = "http://localhost:18080/kabusapi"

logging.basicConfig(
    filename=str(LOG_FILE), level=logging.INFO,
    format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger(__name__)


def _load_api_password() -> str:
    env_path = SCRIPT_DIR / ".env_windows"
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("KABU_API_PASSWORD="):
                return line.split("=", 1)[1].strip()
    raise ValueError("KABU_API_PASSWORD not found")


def _get_token() -> str:
    resp = requests.post(
        f"{BASE_URL}/token",
        json={"APIPassword": _load_api_password()},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["Token"]


def _get_fill_price(order: dict) -> float | None:
    """Details 内で Price > 0 の最初のレコードから約定価格を返す"""
    for d in order.get("Details", []):
        price = d.get("Price", 0)
        if price and float(price) > 0:
            return float(price)
    return None


def fetch_and_save():
    japan_date  = date.today().strftime("%Y-%m-%d")
    date_nodash = japan_date.replace("-", "")
    out_path    = SCRIPT_DIR / f"fills_{date_nodash}.csv"

    log.info(f"=== fetch_fills 開始: {japan_date} ===")
    print(f"=== 約定照会: {japan_date} ===")

    token = _get_token()
    log.info("トークン取得成功")

    resp = requests.get(
        f"{BASE_URL}/orders",
        params={"product": 2},
        headers={"X-API-KEY": token},
        timeout=30,
    )
    resp.raise_for_status()
    orders = resp.json() or []
    log.info(f"注文照会: {len(orders)}件")

    fills = []
    for order in orders:
        order_id = str(order.get("ID", ""))
        if not order_id.startswith(date_nodash):
            continue
        if order.get("CumQty", 0) == 0:
            continue

        fill_price = _get_fill_price(order)
        if fill_price is None:
            log.warning(f"  約定価格取得不可: {order_id}")
            continue

        fills.append({
            "OrderId":    order_id,
            "Symbol":     str(order.get("Symbol", "")),
            "Side":       str(order.get("Side", "")),       # "1"=売 "2"=買
            "CashMargin": int(order.get("CashMargin", 0)),  # 2=新規 3=返済
            "Qty":        int(order.get("CumQty", 0)),
            "Price":      fill_price,
        })

    log.info(f"約定データ: {len(fills)}件")

    if not fills:
        log.warning("約定データなし")
        print("  ⚠️  約定データが取得できませんでした")
        return

    fieldnames = ["OrderId", "Symbol", "Side", "CashMargin", "Qty", "Price"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(fills)

    log.info(f"保存完了: {out_path.name}  {len(fills)}件")
    print(f"  ✅ {out_path.name}  {len(fills)}件 保存")

    for r in fills:
        side_str = "買い" if r["Side"] == "2" else "売り"
        cm_str   = "新規" if r["CashMargin"] == 2 else "返済"
        print(f"    [{r['Symbol']}] {side_str} {cm_str} {r['Qty']}口 @ {r['Price']:,.0f}円")


def main():
    try:
        fetch_and_save()
    except Exception as e:
        log.error(f"エラー: {e}")
        print(f"  ❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
