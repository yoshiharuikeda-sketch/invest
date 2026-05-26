"""
日米業種リードラグ投資戦略 - 毎日のシグナル計算ツール
=======================================================
使い方:
  python signal.py              # 本日のシグナルを計算・表示
  python signal.py --date 2025-03-28   # 特定日のシグナルを計算

出力:
  - ロング/ショートの日本業種ETFリスト
  - 各業種へのシグナルスコア
  - signal_YYYYMMDD.csv に保存
"""

import warnings
warnings.filterwarnings("ignore")

import argparse
import os
import numpy as np
import pandas as pd
from scipy.linalg import eigh
import yfinance as yf
from datetime import datetime, timedelta

# =====================================================================
# 設定（論文準拠）
# =====================================================================

US_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "XLC"]

JP_TICKERS = [
    "1617.T", "1618.T", "1619.T", "1620.T", "1621.T", "1622.T",
    "1623.T", "1624.T", "1626.T", "1627.T", "1628.T",
    "1629.T", "1630.T", "1631.T", "1632.T", "1633.T"
]

JP_NAMES = {
    "1617.T": "食品",
    "1618.T": "エネルギー資源",
    "1619.T": "建設・資材",
    "1620.T": "素材・化学",
    "1621.T": "医薬品",
    "1622.T": "自動車・輸送機",
    "1623.T": "鉄鋼・非鉄",
    "1624.T": "機械",
    "1626.T": "情報通信・サービス",
    "1627.T": "電力・ガス",
    "1628.T": "運輸・物流",
    "1629.T": "商社・卸売",
    "1630.T": "小売",
    "1631.T": "銀行",
    "1632.T": "金融（除く銀行）",
    "1633.T": "不動産",
}

US_NAMES = {
    "XLB":  "Materials（素材）",
    "XLE":  "Energy（エネルギー）",
    "XLF":  "Financials（金融）",
    "XLI":  "Industrials（資本財）",
    "XLK":  "Info. Technology（IT）",
    "XLP":  "Consumer Staples（生活必需品）",
    "XLRE": "Real Estate（不動産）",
    "XLU":  "Utilities（公益）",
    "XLV":  "Health Care（ヘルスケア）",
    "XLY":  "Consumer Discretionary（一般消費財）",
    "XLC":  "Communication Services（通信）",
}

US_CYCLICAL  = ["XLB", "XLE", "XLF", "XLRE"]
US_DEFENSIVE = ["XLK", "XLP", "XLU", "XLV"]
JP_CYCLICAL  = ["1618.T", "1629.T", "1631.T"]
JP_DEFENSIVE = ["1617.T", "1621.T", "1627.T", "1630.T"]

L      = 60     # 推定ウィンドウ（営業日）
K      = 3      # 抽出ファクター数
LAMBDA = 0.9    # 正則化強度
Q      = 0.3    # ロング・ショート分位点（上位/下位30%）

# 事前固有値推定期間
CFULL_START = "2010-01-01"
CFULL_END   = "2014-12-31"

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# =====================================================================
# データ取得
# =====================================================================

def fetch_recent_prices(tickers: list, lookback_days: int = 120) -> pd.DataFrame:
    """直近 lookback_days 日分の終値・始値を取得"""
    end   = datetime.today()
    start = end - timedelta(days=lookback_days * 2)  # 休場日を考慮して余裕を持つ
    raw = yf.download(
        tickers,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    return raw


def fetch_historical_for_prior(tickers: list) -> pd.DataFrame:
    """事前部分空間推定用の長期データを取得（キャッシュあり）"""
    cache_path = os.path.join(DATA_DIR, "cache_prior.parquet")
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path)

    print("  事前推定用データをダウンロード中...")
    raw = yf.download(
        tickers,
        start=CFULL_START,
        end=CFULL_END,
        auto_adjust=True,
        progress=False,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes.to_parquet(cache_path)
    return closes


# =====================================================================
# 事前部分空間の構築（backtest.py と同じロジック）
# =====================================================================

def build_prior_subspace(all_tickers: list) -> np.ndarray:
    N  = len(all_tickers)
    NU = len(US_TICKERS)
    NJ = len(JP_TICKERS)

    v1 = np.ones(N) / np.sqrt(N)

    v2_raw = np.zeros(N)
    v2_raw[:NU] =  1.0 / np.sqrt(NU)
    v2_raw[NU:] = -1.0 / np.sqrt(NJ)
    v2 = v2_raw - np.dot(v2_raw, v1) * v1
    v2 /= np.linalg.norm(v2)

    sign = np.zeros(N)
    for i, t in enumerate(all_tickers):
        if t in US_CYCLICAL or t in JP_CYCLICAL:
            sign[i] = +1.0
        elif t in US_DEFENSIVE or t in JP_DEFENSIVE:
            sign[i] = -1.0
    v3_raw = sign - np.dot(sign, v1) * v1
    v3_raw = v3_raw - np.dot(v3_raw, v2) * v2
    norm3 = np.linalg.norm(v3_raw)
    v3 = v3_raw / norm3 if norm3 > 1e-10 else np.zeros(N)

    return np.column_stack([v1, v2, v3])


def build_prior_covariance(V0: np.ndarray, cc_full: pd.DataFrame) -> np.ndarray:
    df = cc_full.dropna(thresh=max(1, cc_full.shape[1] // 2))
    Z  = df.values.astype(float)
    col_mean = np.nanmean(Z, axis=0)
    col_std  = np.nanstd(Z, axis=0) + 1e-12
    Z_std    = (Z - col_mean) / col_std

    N = Z_std.shape[1]
    C_full = np.eye(N)
    for i in range(N):
        for j in range(i + 1, N):
            mask = ~(np.isnan(Z_std[:, i]) | np.isnan(Z_std[:, j]))
            if mask.sum() > 10:
                c = np.corrcoef(Z_std[mask, i], Z_std[mask, j])[0, 1]
                C_full[i, j] = C_full[j, i] = c if np.isfinite(c) else 0.0

    D0     = np.diag(V0.T @ C_full @ V0)
    C0_raw = V0 @ np.diag(D0) @ V0.T
    diag   = np.where(np.diag(C0_raw) > 1e-12, np.diag(C0_raw), 1e-12)
    inv_sq = np.diag(1.0 / np.sqrt(diag))
    C0     = inv_sq @ C0_raw @ inv_sq
    np.fill_diagonal(C0, 1.0)
    return C0


# =====================================================================
# シグナル計算（コア）
# =====================================================================

def compute_pca_sub_signal(
    window_cc: np.ndarray,
    C0: np.ndarray,
    z_us_today: np.ndarray,
    lam: float = LAMBDA,
    k: int = K,
) -> np.ndarray:
    """
    部分空間正則化PCA シグナル
    window_cc : (L, N) 標準化済みClose-to-Closeリターン行列
    C0        : (N, N) 事前エクスポージャー行列
    z_us_today: (NU,) 米国当日標準化リターン
    戻り値     : (NJ,) 日本業種へのシグナルスコア
    """
    NU = len(US_TICKERS)

    # ウィンドウ内相関行列
    C_t = np.corrcoef(window_cc.T)
    C_t = np.nan_to_num(C_t, nan=0.0)
    np.fill_diagonal(C_t, 1.0)

    # 正則化
    C_reg = (1 - lam) * C_t + lam * C0

    # 上位K固有ベクトル
    vals, vecs = eigh(C_reg)
    idx  = np.argsort(vals)[::-1]
    V_K  = vecs[:, idx[:k]]          # (N, K)
    V_U  = V_K[:NU, :]               # (NU, K)
    V_J  = V_K[NU:, :]               # (NJ, K)

    # ファクタースコア → 日本側シグナル
    f_t    = V_U.T @ z_us_today      # (K,)
    signal = V_J @ f_t               # (NJ,)
    return signal


def standardize(window: np.ndarray, today: np.ndarray) -> np.ndarray:
    """ウィンドウの統計量で today を標準化"""
    mu    = np.nanmean(window, axis=0)
    sigma = np.nanstd(window, axis=0) + 1e-12
    return np.nan_to_num((today - mu) / sigma, nan=0.0)


# =====================================================================
# メイン: シグナル生成
# =====================================================================

def generate_signal(target_date: str = None) -> pd.DataFrame:
    """
    指定日（または最新営業日）のシグナルを計算する。

    target_date: "YYYY-MM-DD" 形式。None なら最新営業日を使用。
    戻り値: シグナルスコアと売買方向を含む DataFrame
    """
    all_tickers = US_TICKERS + JP_TICKERS
    NU = len(US_TICKERS)
    NJ = len(JP_TICKERS)

    # ---- データ取得 ----
    print("データ取得中...")
    raw = fetch_recent_prices(all_tickers, lookback_days=L + 20)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    opens  = raw["Open"]  if isinstance(raw.columns, pd.MultiIndex) else raw

    # Close-to-Close リターン（全銘柄）
    cc = closes.pct_change()

    # 対象日の決定
    available_dates = cc.dropna(how="all").index
    if target_date:
        ts = pd.Timestamp(target_date)
        # 指定日以前の最新日
        mask = available_dates <= ts
        if mask.sum() == 0:
            raise ValueError(f"指定日 {target_date} 以前のデータが見つかりません")
        signal_date = available_dates[mask][-1]
    else:
        signal_date = available_dates[-1]

    print(f"シグナル計算日（米国終値基準）: {signal_date.date()}")
    print(f"  → 翌営業日の日本業種ETFに投資")

    # ---- 推定ウィンドウ ----
    date_loc = cc.index.get_loc(signal_date)
    if date_loc < L:
        raise ValueError(f"ウィンドウ長 {L} 日分のデータが不足しています（{date_loc}日分しかありません）")

    window_cc_df = cc.iloc[date_loc - L : date_loc][all_tickers]
    window_cc_df = window_cc_df.ffill().bfill()

    if window_cc_df.isnull().sum().sum() > 0:
        print(f"  警告: ウィンドウ内にNaNが残存 → 0で補完")
        window_cc_df = window_cc_df.fillna(0.0)

    window_arr = window_cc_df.values.astype(float)

    # 標準化
    mu    = np.nanmean(window_arr, axis=0)
    sigma = np.nanstd(window_arr, axis=0) + 1e-12
    Z_std = (window_arr - mu) / sigma

    # ---- 事前部分空間 ----
    print("事前部分空間を構築中...")
    V0 = build_prior_subspace(all_tickers)

    hist_closes = fetch_historical_for_prior(all_tickers)
    if isinstance(hist_closes.columns, pd.MultiIndex):
        hist_closes = hist_closes["Close"] if "Close" in hist_closes.columns.get_level_values(0) else hist_closes.droplevel(0, axis=1)
    hist_closes = hist_closes[all_tickers] if all(t in hist_closes.columns for t in all_tickers) else hist_closes.reindex(columns=all_tickers)
    cc_full = hist_closes.pct_change().dropna(how="all")
    C0 = build_prior_covariance(V0, cc_full)

    # ---- 米国当日標準化リターン ----
    us_today_raw = cc.iloc[date_loc][US_TICKERS].values.astype(float)
    us_today_raw = np.nan_to_num(us_today_raw, nan=0.0)
    z_us         = standardize(window_arr[:, :NU], us_today_raw)

    # ---- シグナル計算 ----
    signal = compute_pca_sub_signal(Z_std, C0, z_us)

    # ---- ポートフォリオ構築 ----
    n_long  = max(1, round(NJ * Q))
    n_short = max(1, round(NJ * Q))
    rank    = np.argsort(signal)

    positions = np.zeros(NJ)
    positions[rank[-n_long:]]  = +1.0 / n_long
    positions[rank[:n_short]]  = -1.0 / n_short

    # ---- 結果DataFrame ----
    df_signal = pd.DataFrame({
        "Ticker":    JP_TICKERS,
        "名称":      [JP_NAMES[t] for t in JP_TICKERS],
        "シグナルスコア": signal,
        "スコア順位":    pd.Series(signal).rank(ascending=False).astype(int).values,
        "ポジション":   positions,
        "方向":       ["★ LONG " if p > 0 else ("▼ SHORT" if p < 0 else "  -   ") for p in positions],
        "ウェイト(%)":  [f"{p*100:+.1f}" for p in positions],
    })
    df_signal = df_signal.sort_values("シグナルスコア", ascending=False).reset_index(drop=True)

    return df_signal, signal_date, z_us, cc.iloc[date_loc][US_TICKERS]


# =====================================================================
# 表示・保存
# =====================================================================

def print_signal_report(df_signal: pd.DataFrame, signal_date, z_us: np.ndarray, us_ret: pd.Series):
    """見やすい形式でシグナルを表示"""

    print()
    print("=" * 65)
    print(f"  日米業種リードラグ 投資シグナル")
    print(f"  米国終値確定日  : {signal_date.date()}")
    print(f"  翌日執行（日本）: 翌営業日 寄付きBUY → 引けSELL")
    print("=" * 65)

    # 米国業種リターン
    print("\n【米国業種 当日リターン（シグナル入力）】")
    print(f"  {'Ticker':<6}  {'名称':<30}  {'リターン(%)':>10}  {'標準化z':>8}")
    print(f"  {'-'*6}  {'-'*30}  {'-'*10}  {'-'*8}")
    for i, t in enumerate(US_TICKERS):
        ret_val = us_ret[t] if t in us_ret.index else np.nan
        z_val   = z_us[i]
        bar = "▲" if ret_val > 0 else "▼"
        print(f"  {t:<6}  {US_NAMES.get(t, t):<30}  {bar}{ret_val*100:>8.2f}%  {z_val:>+8.2f}")

    # ロングポジション
    longs = df_signal[df_signal["ポジション"] > 0].copy()
    print(f"\n【LONG（買い）: 上位 {len(longs)} 業種】")
    print(f"  {'順位':<4}  {'Ticker':<8}  {'名称':<16}  {'スコア':>8}  {'ウェイト':>8}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*16}  {'-'*8}  {'-'*8}")
    for _, row in longs.iterrows():
        print(f"  {row['スコア順位']:<4}  {row['Ticker']:<8}  {row['名称']:<16}  {row['シグナルスコア']:>+8.4f}  {row['ウェイト(%)']}%")

    # ショートポジション
    shorts = df_signal[df_signal["ポジション"] < 0].copy().sort_values("シグナルスコア")
    print(f"\n【SHORT（売り）: 下位 {len(shorts)} 業種】")
    print(f"  {'順位':<4}  {'Ticker':<8}  {'名称':<16}  {'スコア':>8}  {'ウェイト':>8}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*16}  {'-'*8}  {'-'*8}")
    for _, row in shorts.iterrows():
        print(f"  {row['スコア順位']:<4}  {row['Ticker']:<8}  {row['名称']:<16}  {row['シグナルスコア']:>+8.4f}  {row['ウェイト(%)']}%")

    # ニュートラル
    neutral_count = (df_signal["ポジション"] == 0).sum()
    print(f"\n  ニュートラル（ポジションなし）: {neutral_count} 業種")

    print("\n【注意事項】")
    print("  ・執行タイミング：日本市場 翌営業日 寄付き（成行）")
    print("  ・決済タイミング：同日 引け（成行）")
    print("  ・1日保有のデイトレード戦略")
    print("  ・取引コスト（スプレッド・税金）は考慮していません")
    print("=" * 65)


def save_signal(df_signal: pd.DataFrame, signal_date):
    """CSVに保存"""
    date_str  = signal_date.strftime("%Y%m%d")
    save_path = os.path.join(DATA_DIR, f"signal_{date_str}.csv")
    df_signal.to_csv(save_path, index=False, encoding="utf-8-sig")
    print(f"\n  シグナルを保存: {save_path}")
    return save_path


# =====================================================================
# エントリーポイント
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="日米業種リードラグ投資シグナル計算")
    parser.add_argument(
        "--date", type=str, default=None,
        help="シグナル計算日（YYYY-MM-DD）。省略時は最新営業日を使用。"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="CSVへの保存をスキップ"
    )
    args = parser.parse_args()

    try:
        df_signal, signal_date, z_us, us_ret = generate_signal(target_date=args.date)
        print_signal_report(df_signal, signal_date, z_us, us_ret)
        if not args.no_save:
            save_signal(df_signal, signal_date)
    except Exception as e:
        print(f"\nエラー: {e}")
        raise


if __name__ == "__main__":
    main()
