"""
kabuStation(R) API 約定照会スクリプト
引成決済後（15:32頃）に実行し、今日の全約定価格と東証始値・終値を
fills_YYYYMMDD.csv に保存する。
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
EXCHANGE   = 1   # 東証

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


def _get_board(token: str, symbol: str) -> dict | None:
    """銘柄の板情報（始値・現在値含む）を取得"""
    try:
        resp = requests.get(
            f"{BASE_URL}/board/{symbol}@{EXCHANGE}",
            headers={"X-API-KEY": token},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f"  板情報取得失敗 {symbol}: {e}")
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

    # ---- 板情報から始値・現在値（引け後≒終値）を取得 ----
    unique_symbols = sorted({r["Symbol"] for r in fills})
    market_prices = {}   # symbol → (open, close)
    for sym in unique_symbols:
        board = _get_board(token, sym)
        if board:
            mo = board.get("OpeningPrice") or 0
            mc = board.get("CurrentPrice") or 0
            market_prices[sym] = (float(mo) if mo else None,
                                  float(mc) if mc else None)
        else:
            market_prices[sym] = (None, None)

    log.info(f"板情報取得: {len(unique_symbols)}銘柄")

    for r in fills:
        mo, mc = market_prices.get(r["Symbol"], (None, None))
        r["MarketOpen"]  = mo
        r["MarketClose"] = mc

    fieldnames = ["OrderId", "Symbol", "Side", "CashMargin", "Qty",
                  "Price", "MarketOpen", "MarketClose"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(fills)

    log.info(f"保存完了: {out_path.name}  {len(fills)}件")
    print(f"  ✅ {out_path.name}  {len(fills)}件 保存")

    for r in fills:
        side_str = "買い" if r["Side"] == "2" else "売り"
        cm_str   = "新規" if r["CashMargin"] == 2 else "返済"
        mo = r.get("MarketOpen")
        mc = r.get("MarketClose")
        mo_str = f"{mo:,.0f}" if mo else "—"
        mc_str = f"{mc:,.0f}" if mc else "—"
        print(f"    [{r['Symbol']}] {side_str} {cm_str} {r['Qty']}口 "
              f"@ {r['Price']:,.0f}円  市場OP:{mo_str} / CL:{mc_str}")


def main():
    try:
        fetch_and_save()
    except Exception as e:
        log.error(f"エラー: {e}")
        print(f"  ❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
