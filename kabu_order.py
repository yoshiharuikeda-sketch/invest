"""
三菱UFJ eスマート証券（旧auカブコム証券）
kabuステーション® API 自動発注モジュール
==========================================

【前提条件】
  1. kabuステーション®（Windows版）を同一PCで起動していること
  2. Professionalプラン以上の口座
  3. APIタブでAPIを有効化していること

【APIエンドポイント】
  REST  : http://localhost:18080/kabusapi/
  PUSH  : ws://localhost:18081/kabusapi/websocket

【使い方】
  # シグナルを受け取って発注
  python3 kabu_order.py

  # 発注なしで接続テストのみ
  python3 kabu_order.py --test

  # 実際の発注（--dryrun なしで実行）
  python3 kabu_order.py --execute
"""

import warnings
warnings.filterwarnings("ignore")

import argparse
import os
import sys
import io
import time
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# Windows コンソールの文字化け対策
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# =====================================================================
# 設定
# =====================================================================

KABU_API_BASE   = "http://localhost:18080/kabusapi"
KABU_WS_URL     = "ws://localhost:18081/kabusapi/websocket"
TOKEN_CACHE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kabu_token.json")
_ENV_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env_windows")

def _load_api_password() -> str:
    """環境変数 → .env_windows の順で APIパスワードを取得"""
    pw = os.environ.get("KABU_API_PASSWORD", "")
    if pw:
        return pw
    try:
        with open(_ENV_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line.startswith("KABU_API_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

# kabuステーション®のAPIパスワード
API_PASSWORD    = _load_api_password()

# 発注設定
ORDER_TYPE      = 1      # 1: 成行, 2: 指値
FRONT_ORDER_TYPE = 10    # 10: 成行（寄付）, 13: 成行（引成）
CASH_MARGIN     = 2      # 1: 現物, 2: 信用新規
SIDE_BUY        = "2"   # 買い
SIDE_SELL       = "1"   # 売り

# TOPIX-17 ETF 銘柄コード（証券コード）
JP_TICKER_TO_CODE = {
    "1617.T": "1617", "1618.T": "1618", "1619.T": "1619",
    "1620.T": "1620", "1621.T": "1621", "1622.T": "1622",
    "1623.T": "1623", "1624.T": "1624", "1625.T": "1625",
    "1626.T": "1626", "1627.T": "1627", "1628.T": "1628",
    "1629.T": "1629", "1630.T": "1630", "1631.T": "1631",
    "1632.T": "1632", "1633.T": "1633",
}

JP_NAMES = {
    "1617.T": "食品",           "1618.T": "エネルギー資源",
    "1619.T": "建設・資材",     "1620.T": "素材・化学",
    "1621.T": "医薬品",         "1622.T": "自動車・輸送機",
    "1623.T": "鉄鋼・非鉄",    "1624.T": "機械",
    "1625.T": "電機・精密",     "1626.T": "情報通信・サービス",
    "1627.T": "電力・ガス",     "1628.T": "運輸・物流",
    "1629.T": "商社・卸売",     "1630.T": "小売",
    "1631.T": "銀行",           "1632.T": "金融（除く銀行）",
    "1633.T": "不動産",
}

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# =====================================================================
# 1. トークン管理
# =====================================================================

def get_token(password: str = API_PASSWORD, force_refresh: bool = False) -> str:
    """
    APIトークンを取得（キャッシュ付き）
    トークンは当日中有効のため、日付が変わったら再取得する
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # キャッシュ確認
    if not force_refresh and os.path.exists(TOKEN_CACHE):
        with open(TOKEN_CACHE) as f:
            cache = json.load(f)
        if cache.get("date") == today and cache.get("token"):
            return cache["token"]

    if not password:
        raise ValueError(
            "APIパスワードが設定されていません。\n"
            "環境変数 KABU_API_PASSWORD を設定してください:\n"
            "  export KABU_API_PASSWORD='your_password'"
        )

    url  = f"{KABU_API_BASE}/token"
    body = {"APIPassword": password}
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()

    token = resp.json()["Token"]

    # キャッシュ保存
    with open(TOKEN_CACHE, "w") as f:
        json.dump({"date": today, "token": token}, f)

    print(f"  ✅ トークン取得成功")
    return token


# =====================================================================
# 2. 口座情報・残高照会
# =====================================================================

def get_wallet(token: str) -> dict:
    """現物・信用の余力照会"""
    headers = {"X-API-KEY": token}
    resp_cash = requests.get(f"{KABU_API_BASE}/wallet/cash", headers=headers, timeout=10)
    resp_cash.raise_for_status()
    resp_margin = requests.get(f"{KABU_API_BASE}/wallet/margin", headers=headers, timeout=10)
    resp_margin.raise_for_status()
    return {**resp_cash.json(), **resp_margin.json()}


def get_positions(token: str) -> pd.DataFrame:
    """保有ポジション一覧"""
    headers = {"X-API-KEY": token}
    resp = requests.get(f"{KABU_API_BASE}/positions", headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def get_orders(token: str) -> pd.DataFrame:
    """当日の注文一覧"""
    headers = {"X-API-KEY": token}
    params  = {"product": 0}   # 0: 全商品
    resp = requests.get(f"{KABU_API_BASE}/orders", headers=headers,
                        params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def get_board(token: str, symbol: str, exchange: int = 1) -> dict:
    """
    板情報・現在値取得
    exchange: 1=東証, 3=名証, 5=福証, 6=札証
    """
    headers = {"X-API-KEY": token}
    resp = requests.get(
        f"{KABU_API_BASE}/board/{symbol}@{exchange}",
        headers=headers, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


# =====================================================================
# 3. 注文発注
# =====================================================================

def send_order(
    token: str,
    symbol: str,
    side: str,
    qty: int,
    order_type: int = ORDER_TYPE,
    price: float = 0,
    cash_margin: int = CASH_MARGIN,
    front_order_type: int = FRONT_ORDER_TYPE,
    dry_run: bool = True,
) -> Optional[dict]:
    """
    注文発注
    symbol         : 証券コード（例: "1617"）
    side           : "2"=買い, "1"=売り
    qty            : 株数（口数）
    order_type     : 1=成行, 2=指値
    price          : 指値価格（成行の場合は0）
    cash_margin    : 1=現物, 2=信用新規, 3=信用返済
    front_order_type: 10=成行寄付, 13=成行引成, 20=指値
    dry_run        : True=発注せず内容確認のみ
    """
    direction = "買い" if side == SIDE_BUY else "売り（空売り）"
    print(f"    [{symbol}] {JP_NAMES.get(symbol+'.T', symbol)} "
          f"{direction} {qty}口 ({'成行' if order_type==1 else f'指値{price}円'})"
          f" {'[DRY RUN]' if dry_run else '[実発注]'}")

    if dry_run:
        return {"OrderId": "DRY_RUN", "Result": 0}

    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body = {
        "Password":        API_PASSWORD,
        "Symbol":          symbol,
        "Exchange":        1,          # 東証
        "SecurityType":    1,          # 株式・ETF
        "Side":            side,
        "CashMargin":      cash_margin,
        "DelivType":       0,          # 0=指定なし（信用）
        "FundType":        "  ",       # 指定なし
        "AccountType":     4,          # 特定口座
        "MarginTradeType": 1,          # 1=制度信用, 2=一般信用(長期), 3=一般信用(デイトレ)
        "Qty":             qty,
        "FrontOrderType":  front_order_type,
        "Price":           price,
        "ExpireDay":       0,          # 0=当日
    }

    resp = requests.post(
        f"{KABU_API_BASE}/sendorder",
        headers=headers,
        json=body,
        timeout=10
    )

    if resp.status_code != 200:
        print(f"    ❌ 発注エラー: {resp.status_code} {resp.text}")
        return None

    result = resp.json()
    if result.get("Result") == 0:
        print(f"    ✅ 発注成功: OrderId={result.get('OrderId')}")
    else:
        print(f"    ⚠️  発注失敗: {result}")
    return result


def cancel_order(token: str, order_id: str, dry_run: bool = True) -> Optional[dict]:
    """注文取消"""
    print(f"    注文取消: OrderId={order_id} {'[DRY RUN]' if dry_run else '[実行]'}")
    if dry_run:
        return {"Result": 0}

    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    body    = {"OrderId": order_id, "Password": API_PASSWORD}
    resp    = requests.put(f"{KABU_API_BASE}/cancelorder",
                           headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


# =====================================================================
# 4. シグナルファイルの読み込み
# =====================================================================

def load_latest_signal() -> Optional[pd.DataFrame]:
    """最新のシグナルCSVを読み込む"""
    signal_files = sorted([
        f for f in os.listdir(DATA_DIR)
        if f.startswith("signal_") and f.endswith(".csv")
    ], reverse=True)

    if not signal_files:
        print("  ❌ シグナルファイルが見つかりません。先に daily_signal.py を実行してください。")
        return None

    latest = os.path.join(DATA_DIR, signal_files[0])
    date_str = signal_files[0].replace("signal_", "").replace(".csv", "")
    print(f"  シグナルファイル: {signal_files[0]}（{date_str}）")

    df = pd.read_csv(latest, encoding="utf-8-sig")
    return df


# =====================================================================
# 5. 発注数量の計算
# =====================================================================

def calc_order_qty(
    ticker: str,
    weight: float,
    portfolio_value: float,
    token: str,
) -> int:
    """
    ウェイトとポートフォリオ規模から発注口数を計算
    最低単元（1口）単位に切り下げ
    """
    code = JP_TICKER_TO_CODE.get(ticker)
    if not code:
        return 0

    try:
        board = get_board(token, code)
        price = board.get("CurrentPrice") or board.get("CalcPrice", 1000)
    except Exception:
        price = 1000   # 取得失敗時のデフォルト価格

    target_value = portfolio_value * abs(weight)
    qty = int(target_value / price)   # TOPIX-17 ETFは1口単位
    return max(qty, 1) if target_value > 0 else 0


# =====================================================================
# 6. メイン発注フロー
# =====================================================================

def run_orders(
    portfolio_value: float = 1_000_000,
    dry_run: bool = True,
    open_order: bool = True,   # True=寄付き発注, False=引け発注
):
    """
    シグナルに基づく発注フロー

    portfolio_value: 運用資産額（円）
    dry_run        : True=確認のみ（実際には発注しない）
    open_order     : True=寄付き成行, False=引成
    """
    print("=" * 65)
    print(f"  kabuステーションAPI 発注{'確認（DRY RUN）' if dry_run else '実行'}")
    print(f"  実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  運用資産: {portfolio_value:,.0f}円")
    print("=" * 65)

    # kabuStation再起動でトークンが無効になる場合があるため毎回新規取得
    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)

    # ---- トークン取得 ----
    print("\n【1. 認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ トークン取得失敗: {e}")
        return

    # ---- 残高確認 ----
    print("\n【2. 残高確認】")
    try:
        wallet = get_wallet(token)
        fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
        print(f"  現物買付余力: {fmt(wallet.get('StockAccountWallet', 'N/A'))}円")
        print(f"  信用新規余力: {fmt(wallet.get('MarginAccountWallet', 'N/A'))}円")
    except Exception as e:
        print(f"  ⚠️  残高取得エラー（続行します）: {e}")

    # ---- シグナル読み込み ----
    print("\n【3. シグナル読み込み】")
    df_signal = load_latest_signal()
    if df_signal is None:
        return

    longs  = df_signal[df_signal["ポジション"] > 0].copy()
    shorts = df_signal[df_signal["ポジション"] < 0].copy()
    print(f"  LONG : {len(longs)}銘柄 / SHORT: {len(shorts)}銘柄")

    # ---- 発注内容の確認 ----
    front_type = 10 if open_order else 13   # 10=成行寄付, 13=成行引成
    order_label = "寄付き成行" if open_order else "引成成行"
    print(f"\n【4. 発注内容（{order_label}）】")

    order_results = []

    # ロング（買い）
    print("\n  ▼ LONG（信用新規買い）")
    for _, row in longs.iterrows():
        ticker = row["Ticker"]
        code   = JP_TICKER_TO_CODE.get(ticker, "")
        if not code:
            continue
        qty = calc_order_qty(ticker, row["ポジション"], portfolio_value, token)
        if qty == 0:
            continue
        result = send_order(
            token, code, SIDE_BUY, qty,
            cash_margin=2,
            front_order_type=front_type,
            dry_run=dry_run
        )
        order_results.append({
            "Ticker": ticker, "Side": "BUY", "Qty": qty,
            "Result": result
        })

    # ショート（売り）
    print("\n  ▼ SHORT（信用新規売り）")
    for _, row in shorts.iterrows():
        ticker = row["Ticker"]
        code   = JP_TICKER_TO_CODE.get(ticker, "")
        if not code:
            continue
        qty = calc_order_qty(ticker, abs(row["ポジション"]), portfolio_value, token)
        if qty == 0:
            continue
        result = send_order(
            token, code, SIDE_SELL, qty,
            cash_margin=2,
            front_order_type=front_type,
            dry_run=dry_run
        )
        order_results.append({
            "Ticker": ticker, "Side": "SELL", "Qty": qty,
            "Result": result
        })

    # ---- サマリー ----
    print(f"\n【5. 発注サマリー】")
    print(f"  発注数: {len(order_results)}件")
    if dry_run:
        print("  ⚠️  DRY RUN モード: 実際の発注は行われていません")
        print("  実発注するには --execute オプションを付けて実行してください")
    else:
        success = sum(1 for r in order_results if r["Result"] and r["Result"].get("Result") == 0)
        print(f"  成功: {success}件 / 失敗: {len(order_results)-success}件")

    print("\n=== 完了 ===")
    return order_results


# =====================================================================
# 7. 接続テスト
# =====================================================================

def connection_test():
    """kabuステーションAPIへの接続テスト"""
    print("=" * 65)
    print("  kabuステーションAPI 接続テスト")
    print("=" * 65)

    print("\n【接続確認】")
    try:
        resp = requests.get(f"{KABU_API_BASE}/token", timeout=3)
        print(f"  ✅ kabuステーションAPI に接続できました（ポート18080）")
    except requests.exceptions.ConnectionError:
        print("  ❌ 接続失敗: kabuステーション® が起動していません")
        print("     → kabuステーション®（Windows版）を起動し、")
        print("       システム設定 > APIタブ でAPIを有効化してください")
        return False

    print("\n【認証テスト】")
    if not API_PASSWORD:
        print("  ⚠️  APIパスワード未設定")
        return False

    try:
        token = get_token()
        print(f"  ✅ 認証成功")
    except Exception as e:
        print(f"  ❌ 認証失敗: {e}")
        return False

    print("\n【残高照会テスト】")
    try:
        wallet = get_wallet(token)
        fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
        print(f"  ✅ 残高照会成功")
        print(f"     現物買付余力: {fmt(wallet.get('StockAccountWallet', 'N/A'))}円")
        print(f"     信用新規余力: {fmt(wallet.get('MarginAccountWallet', 'N/A'))}円")
    except Exception as e:
        print(f"  ❌ 残高照会失敗: {e}")

    print("\n【板情報テスト（1617.T 食品）】")
    try:
        board = get_board(token, "1617")
        print(f"  ✅ 板情報取得成功")
        print(f"     現在値: {board.get('CurrentPrice', 'N/A')}円")
        print(f"     出来高: {board.get('TradingVolume', 'N/A')}口")
    except Exception as e:
        print(f"  ❌ 板情報取得失敗: {e}")

    print("\n  接続テスト完了")
    return True


# =====================================================================
# エントリーポイント
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="kabuステーションAPI 自動発注")
    parser.add_argument("--test",    action="store_true", help="接続テストのみ実行")
    parser.add_argument("--execute", action="store_true", help="実際に発注を実行（デフォルトはDRY RUN）")
    parser.add_argument("--close",   action="store_true", help="引成発注（デフォルトは寄付き）")
    parser.add_argument("--value",   type=float, default=1_000_000, help="運用資産額（円）デフォルト: 100万円")
    args = parser.parse_args()

    if args.test:
        connection_test()
        return

    dry_run    = not args.execute
    open_order = not args.close

    run_orders(
        portfolio_value=args.value,
        dry_run=dry_run,
        open_order=open_order,
    )


if __name__ == "__main__":
    main()
