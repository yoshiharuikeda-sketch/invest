"""
シグナルベース仮想損益計算スクリプト
signal_YYYYMMDD.csv を読み込み、当日の実際の寄値・引値から
Open-to-Close の仮想損益を計算する。

使い方:
  python calc_pnl.py              # 全シグナルファイルを集計
  python calc_pnl.py 20260420     # 指定日のみ
"""

import os
import sys
import glob
import re
import warnings
warnings.filterwarnings("ignore")

# Windows コンソールの文字化け対策
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# =====================================================================
# 設定
# =====================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_portfolio_value() -> int:
    """環境変数ファイルからポートフォリオ金額を読む"""
    env_path = os.path.join(SCRIPT_DIR, ".env_windows")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("PORTFOLIO_VALUE="):
                    return int(line.split("=", 1)[1].strip())
    return 990_000  # デフォルト

PORTFOLIO_VALUE = load_portfolio_value()

# kabu_order.py の発注コード変更と一致させる
ORDER_TICKER_MAP   = {"1625.T": "200A.T", "1633.T": "1343.T", "1629.T": "8058.T"}
SHORT_SKIP_TICKERS = {"1617.T", "1620.T", "1623.T"}

# =====================================================================
# シグナルCSV読み込み
# =====================================================================

def load_signal(csv_path: str) -> pd.DataFrame:
    """signal_YYYYMMDD.csv を読み込み、ポジションがある銘柄のみ返す"""
    df = pd.read_csv(csv_path)
    df = df[df["ポジション"] != 0].copy()
    return df


def get_date_from_filename(path: str):
    """signal_20260420.csv → datetime(2026, 4, 20)"""
    m = re.search(r"signal_(\d{8})\.csv", os.path.basename(path))
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d")

# =====================================================================
# 価格データ取得
# =====================================================================

def fetch_ohlc(tickers: list, date: datetime) -> pd.DataFrame:
    """
    指定日の Open / Close を yfinance から取得する。
    date はシグナルの米国日付なので、日本取引日 = date + 1 BDay で取得する。
    当日データがない場合（休場等）は空DataFrameを返す。
    """
    japan_date = pd.Timestamp(date) + pd.offsets.BDay(1)
    date_str  = japan_date.strftime("%Y-%m-%d")
    next_date = japan_date + pd.offsets.BDay(1)
    next_str  = next_date.strftime("%Y-%m-%d")

    raw = yf.download(
        tickers,
        start=date_str,
        end=next_str,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        return pd.DataFrame()

    # MultiIndex (field, ticker) → pivot
    if isinstance(raw.columns, pd.MultiIndex):
        opens  = raw["Open"].iloc[0]
        closes = raw["Close"].iloc[0]
    else:
        # 銘柄が1本のとき
        opens  = pd.Series({tickers[0]: raw["Open"].iloc[0]})
        closes = pd.Series({tickers[0]: raw["Close"].iloc[0]})

    result = pd.DataFrame({"Open": opens, "Close": closes})
    result.index.name = "Ticker"
    return result

# =====================================================================
# 実約定データ読み込み
# =====================================================================

def load_fills(japan_date: pd.Timestamp) -> tuple[dict, bool]:
    """
    fills_YYYYMMDD.csv（日本取引日）を読み込み、約定データを返す。
    キー: (Symbol, CashMargin, Side) → {"price": float, "qty": int}
    ファイルがなければ ({}, False) を返す。
    """
    fills_path = os.path.join(
        SCRIPT_DIR, f"fills_{japan_date.strftime('%Y%m%d')}.csv"
    )
    if not os.path.exists(fills_path):
        return {}, False

    result = {}
    df = pd.read_csv(fills_path, dtype={"Symbol": str, "Side": str})
    for _, row in df.iterrows():
        key = (row["Symbol"], int(row["CashMargin"]), row["Side"])
        result[key] = {"price": float(row["Price"]), "qty": int(row["Qty"])}
    return result, True


# =====================================================================
# 損益計算
# =====================================================================

def calc_day_pnl(signal_df: pd.DataFrame, ohlc: pd.DataFrame,
                 portfolio: int,
                 fills: dict | None = None,
                 fills_available: bool = False) -> pd.DataFrame:
    """
    1日分の損益を計算する。
    fills_available=True のとき実約定価格を優先し、yfinance をフォールバックに使う。

    fills キー: (Symbol, CashMargin, Side)
      CashMargin: 2=信用新規, 3=信用返済
      Side      : "2"=買い,   "1"=売り
    """
    fills = fills or {}
    rows = []

    for _, row in signal_df.iterrows():
        ticker = row["Ticker"]
        symbol = ticker.replace(".T", "")   # "1618.T" → "1618"
        pos    = row["ポジション"]
        weight = abs(row["ウェイト(%)"]) / 100.0

        # 新規/返済・売買方向を決定
        if pos > 0:   # LONG
            open_key  = (symbol, 2, "2")   # 信用新規買い
            close_key = (symbol, 3, "1")   # 信用返済売り
        else:         # SHORT
            open_key  = (symbol, 2, "1")   # 信用新規売り
            close_key = (symbol, 3, "2")   # 信用返済買い

        # --- 始値・終値・損益を決定 ---
        if fills_available:
            open_fill = fills.get(open_key)
            if open_fill is None:
                # 新規発注が約定していない → 実績なし
                rows.append({
                    "Ticker": ticker, "名称": row["名称"],
                    "方向": row["方向"].strip(),
                    "始値": None, "終値": None,
                    "OC騰落率(%)": None, "配分金額(円)": None,
                    "損益(円)": None, "スリッページ(円)": None, "備考": "発注失敗",
                })
                continue

            open_  = open_fill["price"]
            actual_qty = open_fill["qty"]

            close_fill = fills.get(close_key)
            if close_fill is None:
                # 決済未約定 → 未実現損益のためP&L計上しない
                rows.append({
                    "Ticker": ticker, "名称": row["名称"],
                    "方向": row["方向"].strip(),
                    "始値": round(open_, 2), "終値": None,
                    "OC騰落率(%)": None,
                    "配分金額(円)": int(actual_qty * open_),
                    "損益(円)": None, "スリッページ(円)": None, "備考": "決済未了",
                })
                continue

            close_  = close_fill["price"]
            source  = "実約定"
            oc_ret      = (close_ - open_) / open_
            actual_alloc = actual_qty * open_
            pnl         = np.sign(pos) * actual_qty * (close_ - open_)

            # スリッページ = 実損益 - 理論損益（yfinance価格 × 実約定数量）
            slip_pnl = None
            if ticker in ohlc.index:
                yf_open  = ohlc.loc[ticker, "Open"]
                yf_close = ohlc.loc[ticker, "Close"]
                if not pd.isna(yf_open) and not pd.isna(yf_close) and yf_open > 0:
                    theoretical = np.sign(pos) * actual_qty * (yf_close - yf_open)
                    slip_pnl = round(pnl - theoretical)

            rows.append({
                "Ticker":        ticker,
                "名称":          row["名称"],
                "方向":          row["方向"].strip(),
                "始値":          round(open_, 2),
                "終値":          round(close_, 2),
                "OC騰落率(%)":   round(oc_ret * 100, 3),
                "配分金額(円)":   int(actual_alloc),
                "損益(円)":      round(pnl),
                "スリッページ(円)": slip_pnl,
                "備考":          source,
            })
            continue

        # fills データなし → yfinance を使用
        if ticker not in ohlc.index:
            rows.append({
                "Ticker": ticker, "名称": row["名称"],
                "方向": row["方向"].strip(),
                "始値": None, "終値": None,
                "OC騰落率(%)": None, "配分金額(円)": None,
                "損益(円)": None, "スリッページ(円)": None, "備考": "価格データなし",
            })
            continue

        open_  = ohlc.loc[ticker, "Open"]
        close_ = ohlc.loc[ticker, "Close"]

        if pd.isna(open_) or pd.isna(close_) or open_ == 0:
            rows.append({
                "Ticker": ticker, "名称": row["名称"],
                "方向": row["方向"].strip(),
                "始値": open_, "終値": close_,
                "OC騰落率(%)": None, "配分金額(円)": None,
                "損益(円)": None, "スリッページ(円)": None, "備考": "価格異常",
            })
            continue

        oc_ret = (close_ - open_) / open_
        alloc  = weight * portfolio
        pnl    = np.sign(pos) * alloc * oc_ret

        rows.append({
            "Ticker":        ticker,
            "名称":          row["名称"],
            "方向":          row["方向"].strip(),
            "始値":          round(open_, 2),
            "終値":          round(close_, 2),
            "OC騰落率(%)":   round(oc_ret * 100, 3),
            "配分金額(円)":   int(alloc),
            "損益(円)":      round(pnl),
            "スリッページ(円)": None,
            "備考":          "",
        })

    return pd.DataFrame(rows)

# =====================================================================
# メイン処理
# =====================================================================

def process_one_day(csv_path: str) -> dict | None:
    """1日分を処理してサマリー辞書を返す"""
    date = get_date_from_filename(csv_path)
    if date is None:
        return None

    signal_df = load_signal(csv_path)
    if signal_df.empty:
        print(f"  {date.strftime('%Y-%m-%d')}: ポジションなし")
        return None

    # SHORTスキップ銘柄を除外（kabu_order.pyと同じルール）
    skip_mask = signal_df["Ticker"].isin(SHORT_SKIP_TICKERS) & (signal_df["ポジション"] < 0)
    if skip_mask.any():
        skipped = signal_df.loc[skip_mask, "名称"].tolist()
        print(f"  SHORT スキップ: {skipped}")
        signal_df = signal_df[~skip_mask].copy()

    # 実発注銘柄コードに変換（表示用に元コードを保持）
    signal_df["Ticker"] = signal_df["Ticker"].map(lambda t: ORDER_TICKER_MAP.get(t, t))

    # 日本取引日 = シグナル日（米国日付）+ 1 営業日
    japan_date = pd.Timestamp(date) + pd.offsets.BDay(1)
    fills, fills_available = load_fills(japan_date)

    tickers = signal_df["Ticker"].tolist()
    ohlc    = fetch_ohlc(tickers, date)

    if ohlc.empty and not fills_available:
        print(f"  {date.strftime('%Y-%m-%d')}: 価格データ取得失敗（休場？）")
        return None

    detail = calc_day_pnl(signal_df, ohlc, PORTFOLIO_VALUE,
                          fills=fills, fills_available=fills_available)
    total_pnl = detail["損益(円)"].sum(skipna=True)

    src_label = "実約定" if fills_available else "理論値"
    print(f"\n{'='*60}")
    print(f"  {date.strftime('%Y-%m-%d')}  ポートフォリオ: {PORTFOLIO_VALUE:,}円  [{src_label}]")
    print(f"{'='*60}")
    cols = ["名称", "方向", "始値", "終値", "OC騰落率(%)", "損益(円)", "スリッページ(円)", "備考"]
    print(detail[[c for c in cols if c in detail.columns]].to_string(index=False))
    print(f"{'─'*60}")
    print(f"  合計損益: {total_pnl:+,.0f} 円"
          f"  ({total_pnl / PORTFOLIO_VALUE * 100:+.3f}%)")

    return {
        "日付":       date.strftime("%Y-%m-%d"),
        "合計損益(円)": round(total_pnl),
        "損益率(%)":  round(total_pnl / PORTFOLIO_VALUE * 100, 3),
    }


def main():
    # 対象日の指定（引数があれば絞り込み）
    if len(sys.argv) > 1:
        target = sys.argv[1]  # e.g. "20260420"
        pattern = os.path.join(SCRIPT_DIR, f"signal_{target}.csv")
    else:
        pattern = os.path.join(SCRIPT_DIR, "signal_????????.csv")

    csv_files = sorted(glob.glob(pattern))

    if not csv_files:
        print("シグナルCSVが見つかりませんでした。")
        sys.exit(1)

    print(f"対象ファイル数: {len(csv_files)}件  ポートフォリオ: {PORTFOLIO_VALUE:,}円")

    summaries = []
    for path in csv_files:
        result = process_one_day(path)
        if result:
            summaries.append(result)

    if len(summaries) >= 2:
        print(f"\n{'='*60}")
        print("  集計サマリー")
        print(f"{'='*60}")
        summary_df = pd.DataFrame(summaries)
        print(summary_df.to_string(index=False))
        total = summary_df["合計損益(円)"].sum()
        avg   = summary_df["合計損益(円)"].mean()
        wins  = (summary_df["合計損益(円)"] > 0).sum()
        print(f"{'─'*60}")
        print(f"  累計損益 : {total:+,.0f} 円")
        print(f"  平均損益 : {avg:+,.0f} 円/日")
        print(f"  勝率     : {wins}/{len(summary_df)}日"
              f"  ({wins/len(summary_df)*100:.0f}%)")


if __name__ == "__main__":
    main()
