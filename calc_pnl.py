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
    当日データがない場合（休場等）は空DataFrameを返す。
    """
    date_str  = date.strftime("%Y-%m-%d")
    next_date = pd.Timestamp(date) + pd.offsets.BDay(1)
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
# 損益計算
# =====================================================================

def calc_day_pnl(signal_df: pd.DataFrame, ohlc: pd.DataFrame,
                 portfolio: int) -> pd.DataFrame:
    """
    1日分の仮想損益を計算する。

    ポジションサイズ = abs(ウェイト%) / 100 * portfolio_value
    LONG  P&L = +size * (close - open) / open
    SHORT P&L = -size * (close - open) / open
    """
    rows = []
    for _, row in signal_df.iterrows():
        ticker = row["Ticker"]
        pos    = row["ポジション"]       # +0.2 or -0.2
        weight = abs(row["ウェイト(%)"]) / 100.0  # 0.2

        if ticker not in ohlc.index:
            rows.append({
                "Ticker": ticker,
                "名称":   row["名称"],
                "方向":   row["方向"].strip(),
                "始値":   None,
                "終値":   None,
                "OC騰落率(%)": None,
                "配分金額(円)": None,
                "損益(円)":  None,
                "備考":   "価格データなし",
            })
            continue

        open_  = ohlc.loc[ticker, "Open"]
        close_ = ohlc.loc[ticker, "Close"]

        if pd.isna(open_) or pd.isna(close_) or open_ == 0:
            rows.append({
                "Ticker": ticker,
                "名称":   row["名称"],
                "方向":   row["方向"].strip(),
                "始値":   open_,
                "終値":   close_,
                "OC騰落率(%)": None,
                "配分金額(円)": None,
                "損益(円)":  None,
                "備考":   "価格異常",
            })
            continue

        oc_ret = (close_ - open_) / open_       # Open-to-Close リターン
        alloc  = weight * portfolio              # 配分金額（円）
        pnl    = pos * alloc * oc_ret            # 損益（pos=+/-で方向が決まる）

        rows.append({
            "Ticker":       ticker,
            "名称":         row["名称"],
            "方向":         row["方向"].strip(),
            "始値":         round(open_, 2),
            "終値":         round(close_, 2),
            "OC騰落率(%)":  round(oc_ret * 100, 3),
            "配分金額(円)":  int(alloc),
            "損益(円)":     round(pnl),
            "備考":         "",
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

    tickers = signal_df["Ticker"].tolist()
    ohlc    = fetch_ohlc(tickers, date)

    if ohlc.empty:
        print(f"  {date.strftime('%Y-%m-%d')}: 価格データ取得失敗（休場？）")
        return None

    detail = calc_day_pnl(signal_df, ohlc, PORTFOLIO_VALUE)
    total_pnl = detail["損益(円)"].sum(skipna=True)

    print(f"\n{'='*60}")
    print(f"  {date.strftime('%Y-%m-%d')}  ポートフォリオ: {PORTFOLIO_VALUE:,}円")
    print(f"{'='*60}")
    print(detail[["名称", "方向", "始値", "終値",
                  "OC騰落率(%)", "損益(円)", "備考"]].to_string(index=False))
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
