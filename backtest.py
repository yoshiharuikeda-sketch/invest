"""
日米業種リードラグ投資戦略 バックテスト実装
論文: 部分空間正則化付き主成分分析を用いた日米業種リードラグ投資戦略

戦略概要:
  - 米国業種ETFの当日終値リターンをシグナルとして
  - 翌営業日の日本業種ETFのOpen-to-Closeリターンを予測
  - 部分空間正則化PCAで共通ファクターを安定抽出
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib

matplotlib.rcParams["font.family"] = "Hiragino Sans"
matplotlib.rcParams["axes.unicode_minus"] = False
from scipy.linalg import eigh
import yfinance as yf
from datetime import datetime
import os

# =====================================================================
# 設定
# =====================================================================

# 米国業種ETF（シグナル生成用）
US_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "XLC"]

# 日本業種ETF（取引対象）
JP_TICKERS = [
    "1617.T", "1618.T", "1619.T", "1620.T", "1621.T", "1622.T",
    "1623.T", "1624.T", "1625.T", "1626.T", "1627.T", "1628.T",
    "1629.T", "1630.T", "1631.T", "1632.T", "1633.T"
]

# シクリカル・ディフェンシブ分類（論文準拠）
US_CYCLICAL    = ["XLB", "XLE", "XLF", "XLRE"]
US_DEFENSIVE   = ["XLK", "XLP", "XLU", "XLV"]
JP_CYCLICAL    = ["1618.T", "1625.T", "1629.T", "1631.T"]
JP_DEFENSIVE   = ["1617.T", "1621.T", "1627.T", "1630.T"]

# ハイパーパラメータ（論文準拠）
L      = 60     # 推定ウィンドウ（営業日）
K      = 3      # 抽出ファクター数
K0     = 3      # 事前部分空間の次元
LAMBDA = 0.9    # 正則化強度
Q      = 0.3    # ロング・ショート分位点

# バックテスト期間
START_DATE       = "2010-01-01"
END_DATE         = "2025-12-31"
CFULL_END_DATE   = "2014-12-31"   # 事前固有値推定に使う期間の終端

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# =====================================================================
# データ取得
# =====================================================================

def fetch_data(tickers: list[str], start: str, end: str, cache_path: str) -> pd.DataFrame:
    """yfinanceでOHLCデータを取得（キャッシュ付き）"""
    if os.path.exists(cache_path):
        print(f"  キャッシュ読み込み: {cache_path}")
        return pd.read_parquet(cache_path)

    print(f"  ダウンロード中: {len(tickers)}銘柄 ...")
    raw = yf.download(
        tickers, start=start, end=end,
        auto_adjust=True, progress=False
    )
    df = raw.stack(level=1, future_stack=True).rename_axis(["Date", "Ticker"])
    df = df.reset_index()
    df.to_parquet(cache_path, index=False)
    return df


def build_price_series(df: pd.DataFrame, tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open・Close価格の横持ちDataFrameを返す"""
    opens  = df.pivot(index="Date", columns="Ticker", values="Open")[tickers]
    closes = df.pivot(index="Date", columns="Ticker", values="Close")[tickers]
    return opens.sort_index(), closes.sort_index()


def load_all_data():
    """米国・日本ETFデータを読み込みリターン系列を構築"""
    print("=== データ取得 ===")

    us_df = fetch_data(
        US_TICKERS, START_DATE, END_DATE,
        os.path.join(DATA_DIR, "cache_us.parquet")
    )
    jp_df = fetch_data(
        JP_TICKERS, START_DATE, END_DATE,
        os.path.join(DATA_DIR, "cache_jp.parquet")
    )

    us_open,  us_close = build_price_series(us_df, US_TICKERS)
    jp_open,  jp_close = build_price_series(jp_df, JP_TICKERS)

    # 共通営業日のみ使用
    common_dates = us_close.index.intersection(jp_close.index)
    us_close = us_close.loc[common_dates]
    jp_close = jp_close.loc[common_dates]
    jp_open  = jp_open.loc[common_dates]

    # Close-to-Close リターン（全銘柄; PCA推定用）
    us_cc = us_close.pct_change()
    jp_cc = jp_close.pct_change()

    # Open-to-Close リターン（日本; 戦略評価用）
    jp_oc = (jp_close - jp_open) / jp_open

    print(f"  共通営業日数: {len(common_dates)}")
    print(f"  期間: {common_dates[0].date()} 〜 {common_dates[-1].date()}")

    return us_cc, jp_cc, jp_oc, common_dates


# =====================================================================
# 事前部分空間の構築
# =====================================================================

def build_prior_subspace(all_tickers: list[str]) -> np.ndarray:
    """
    V0 ∈ R^{N × K0}: 経済的に意味のある3つの直交ファクターベクトル
      v1: グローバル（均等ウェイト）
      v2: 国スプレッド（米国+ / 日本-）
      v3: シクリカル・ディフェンシブ
    """
    N  = len(all_tickers)
    NU = len(US_TICKERS)
    NJ = len(JP_TICKERS)

    # --- v1: グローバルファクター ---
    v1 = np.ones(N) / np.sqrt(N)

    # --- v2: 国スプレッドファクター ---
    v2_raw = np.zeros(N)
    v2_raw[:NU] =  1.0 / np.sqrt(NU)
    v2_raw[NU:] = -1.0 / np.sqrt(NJ)
    v2 = v2_raw - np.dot(v2_raw, v1) * v1
    v2 /= np.linalg.norm(v2)

    # --- v3: シクリカル・ディフェンシブファクター ---
    sign = np.zeros(N)
    for i, t in enumerate(all_tickers):
        if t in US_CYCLICAL or t in JP_CYCLICAL:
            sign[i] = +1.0
        elif t in US_DEFENSIVE or t in JP_DEFENSIVE:
            sign[i] = -1.0
    v3_raw = sign.copy()
    v3_raw = v3_raw - np.dot(v3_raw, v1) * v1
    v3_raw = v3_raw - np.dot(v3_raw, v2) * v2
    norm3 = np.linalg.norm(v3_raw)
    if norm3 < 1e-10:
        v3 = np.zeros(N)
        v3[0] = 1.0
    else:
        v3 = v3_raw / norm3

    V0 = np.column_stack([v1, v2, v3])   # (N, K0)
    return V0


def build_prior_covariance(V0: np.ndarray, cc_full: pd.DataFrame) -> np.ndarray:
    """
    C0: 事前エクスポージャー行列
      1. 長期相関行列 Cfull から事前方向の固有値 D0 を推定
      2. C0_raw = V0 D0 V0^T を対角正規化して相関行列に変換
    """
    # 長期相関行列（列ごとに有効なデータのみ使って推定; NaN列はpairwise相関）
    df = cc_full.copy()
    # 全列NaNの行を除外しつつ、列ごとに使える行を最大化
    df = df.dropna(thresh=max(1, df.shape[1] // 2))  # 半数以上の列が有効な行のみ
    Z = df.values.astype(float)
    # 列ごとに平均・標準偏差で標準化（NaN無視）
    col_mean = np.nanmean(Z, axis=0)
    col_std  = np.nanstd(Z, axis=0) + 1e-12
    Z = (Z - col_mean) / col_std
    # pairwise相関行列（NaN対応）
    N = Z.shape[1]
    C_full = np.eye(N)
    for i in range(N):
        for j in range(i + 1, N):
            mask = ~(np.isnan(Z[:, i]) | np.isnan(Z[:, j]))
            if mask.sum() > 10:
                c = np.corrcoef(Z[mask, i], Z[mask, j])[0, 1]
                C_full[i, j] = C_full[j, i] = c if np.isfinite(c) else 0.0

    # 事前方向の固有値
    D0 = np.diag(V0.T @ C_full @ V0)   # (K0,)

    # ターゲット行列
    C0_raw = V0 @ np.diag(D0) @ V0.T

    # 対角正規化（相関行列へ）
    diag = np.diag(C0_raw)
    diag = np.where(diag > 1e-12, diag, 1e-12)
    D_half_inv = np.diag(1.0 / np.sqrt(diag))
    C0 = D_half_inv @ C0_raw @ D_half_inv

    # 対角を1に調整
    np.fill_diagonal(C0, 1.0)
    return C0


# =====================================================================
# 部分空間正則化PCA シグナル生成
# =====================================================================

def compute_signal_pca_sub(
    window_cc: pd.DataFrame,
    C0: np.ndarray,
    all_tickers: list[str],
    z_us_today: np.ndarray,
    lam: float = LAMBDA,
    k: int = K
) -> np.ndarray:
    """
    部分空間正則化PCA によるシグナル生成
    戻り値: signal ∈ R^{NJ}  （各日本業種へのシグナル）
    """
    NU = len(US_TICKERS)

    # 標準化リターン行列 (L × N)
    Z = window_cc.values.astype(float)
    mu    = np.nanmean(Z, axis=0)
    sigma = np.nanstd(Z, axis=0) + 1e-12
    Z_std = (Z - mu) / sigma
    Z_std = np.nan_to_num(Z_std, nan=0.0)  # NaN（上場前等）は0で補完

    # 相関行列
    C_t = np.corrcoef(Z_std.T)
    C_t = np.nan_to_num(C_t, nan=0.0)
    np.fill_diagonal(C_t, 1.0)

    # 正則化相関行列
    C_reg = (1 - lam) * C_t + lam * C0

    # 固有値分解（上位K個）
    vals, vecs = eigh(C_reg)
    idx  = np.argsort(vals)[::-1]
    V_K  = vecs[:, idx[:k]]       # (N, K)

    V_U = V_K[:NU, :]             # (NU, K)
    V_J = V_K[NU:, :]             # (NJ, K)

    # 米国当日ショックのファクタースコア
    f_t = V_U.T @ z_us_today      # (K,)

    # 日本側シグナル
    signal = V_J @ f_t            # (NJ,)
    return signal


def compute_signal_pca_plain(
    window_cc: pd.DataFrame,
    z_us_today: np.ndarray,
    k: int = K
) -> np.ndarray:
    """正則化なしPCA（ベースライン）"""
    NU = len(US_TICKERS)

    Z = window_cc.values.astype(float)
    mu    = np.nanmean(Z, axis=0)
    sigma = np.nanstd(Z, axis=0) + 1e-12
    Z_std = (Z - mu) / sigma
    Z_std = np.nan_to_num(Z_std, nan=0.0)

    C_t = np.corrcoef(Z_std.T)
    C_t = np.nan_to_num(C_t, nan=0.0)
    np.fill_diagonal(C_t, 1.0)
    vals, vecs = eigh(C_t)
    idx = np.argsort(vals)[::-1]
    V_K = vecs[:, idx[:k]]

    V_U = V_K[:NU, :]
    V_J = V_K[NU:, :]

    f_t     = V_U.T @ z_us_today
    signal  = V_J @ f_t
    return signal


def compute_signal_mom(window_jp_cc: pd.DataFrame) -> np.ndarray:
    """単純モメンタム（ベースライン）: 日本業種の平均リターン"""
    return window_jp_cc.mean(axis=0).values


def standardize_us_return(window_cc: pd.DataFrame, us_today: np.ndarray) -> np.ndarray:
    """米国当日リターンをウィンドウの平均・標準偏差で標準化"""
    NU = len(US_TICKERS)
    Z_us = window_cc.iloc[:, :NU].values.astype(float)
    mu    = np.nanmean(Z_us, axis=0)
    sigma = np.nanstd(Z_us, axis=0) + 1e-12
    z = (us_today - mu) / sigma
    return np.nan_to_num(z, nan=0.0)


# =====================================================================
# ポートフォリオ構築
# =====================================================================

def build_portfolio_weights(signal: np.ndarray, n_assets: int, q: float = Q) -> np.ndarray:
    """
    上位q分位をロング、下位q分位をショートする等ウェイトポートフォリオ
    ウェイトの絶対値の合計 = 2
    """
    n_long  = max(1, round(n_assets * q))
    n_short = max(1, round(n_assets * q))

    weights = np.zeros(n_assets)
    rank    = np.argsort(signal)

    weights[rank[-n_long:]]  = +1.0 / n_long
    weights[rank[:n_short]]  = -1.0 / n_short

    return weights


# =====================================================================
# バックテスト本体
# =====================================================================

def run_backtest(us_cc: pd.DataFrame, jp_cc: pd.DataFrame, jp_oc: pd.DataFrame) -> pd.DataFrame:
    """
    全戦略のバックテストを実行し、日次リターン系列を返す
    """
    all_tickers = US_TICKERS + JP_TICKERS
    NU = len(US_TICKERS)
    NJ = len(JP_TICKERS)

    # 結合Close-to-Closeリターン
    cc_all = pd.concat([us_cc, jp_cc], axis=1)[all_tickers].dropna(how="all")

    # --- 事前部分空間の構築 ---
    print("\n=== 事前部分空間の構築 ===")
    V0 = build_prior_subspace(all_tickers)

    # 事前固有値推定（2010〜2014年のデータ使用）
    # タイムゾーン対応: インデックスがtz-awareの場合も比較できるよう変換
    idx = cc_all.index
    if hasattr(idx, "tz") and idx.tz is not None:
        cutoff = pd.Timestamp(CFULL_END_DATE, tz=idx.tz)
    else:
        cutoff = pd.Timestamp(CFULL_END_DATE)
    cc_full = cc_all[cc_all.index <= cutoff].dropna(how="all")
    C0 = build_prior_covariance(V0, cc_full)
    print(f"  C0 shape: {C0.shape}  （固有値推定期間: {cc_full.index[0].date()} 〜 {cc_full.index[-1].date()}）")

    # --- バックテストループ ---
    print("\n=== バックテスト実行 ===")
    dates = cc_all.index[L:]      # ウィンドウ分だけスキップ

    results = {
        "MOM":       [],
        "PCA_PLAIN": [],
        "PCA_SUB":   [],
        "DOUBLE":    [],
    }
    ret_dates = []

    for i, date in enumerate(dates):
        if i % 500 == 0:
            print(f"  進捗: {i}/{len(dates)} ({date.date()})")

        # 推定ウィンドウ
        window_end   = cc_all.index.get_loc(date)
        window_start = window_end - L
        window_cc    = cc_all.iloc[window_start:window_end]

        # 欠損が多い日はスキップ
        if window_cc.isnull().mean().mean() > 0.3:
            continue

        # ウィンドウ内を前値補完
        window_cc = window_cc.ffill().bfill()
        if window_cc.isnull().any().any():
            continue

        # 翌日（date）の日本OC リターン
        if date not in jp_oc.index:
            continue
        jp_ret_today = jp_oc.loc[date]
        if jp_ret_today.isnull().all():
            continue

        # 米国当日CCリターン（前日 = window の最終行）
        us_today_raw = window_cc.iloc[-1, :NU].values

        # 標準化
        z_us = standardize_us_return(window_cc, us_today_raw)

        # ---- シグナル計算 ----
        signal_mom       = compute_signal_mom(window_cc.iloc[:, NU:])
        signal_pca_plain = compute_signal_pca_plain(window_cc, z_us, k=K)
        signal_pca_sub   = compute_signal_pca_sub(window_cc, C0, all_tickers, z_us, lam=LAMBDA, k=K)

        # ---- ポートフォリオウェイト ----
        w_mom       = build_portfolio_weights(signal_mom,       NJ)
        w_pca_plain = build_portfolio_weights(signal_pca_plain, NJ)
        w_pca_sub   = build_portfolio_weights(signal_pca_sub,   NJ)

        # DOUBLE: MOMとPCA_SUBのメディアン2×2ダブルソート
        med_mom = np.median(signal_mom)
        med_sub = np.median(signal_pca_sub)
        w_double = np.zeros(NJ)
        high_both = (signal_mom > med_mom) & (signal_pca_sub > med_sub)
        low_both  = (signal_mom < med_mom) & (signal_pca_sub < med_sub)
        if high_both.sum() > 0:
            w_double[high_both] = +1.0 / high_both.sum()
        if low_both.sum() > 0:
            w_double[low_both]  = -1.0 / low_both.sum()

        # ---- 戦略リターン（利用可能なリターンのみ使用）----
        r = jp_ret_today.values
        avail = ~np.isnan(r)

        def port_ret(w):
            if avail.sum() == 0:
                return np.nan
            # 利用可能銘柄でウェイトを再正規化
            w_a = w * avail
            pos = w_a > 0
            neg = w_a < 0
            if pos.sum() > 0:
                w_a[pos] /= w_a[pos].sum()
            if neg.sum() > 0:
                w_a[neg] /= (-w_a[neg].sum())
            return np.dot(w_a, np.nan_to_num(r))

        results["MOM"].append(port_ret(w_mom))
        results["PCA_PLAIN"].append(port_ret(w_pca_plain))
        results["PCA_SUB"].append(port_ret(w_pca_sub))
        results["DOUBLE"].append(port_ret(w_double))
        ret_dates.append(date)

    df_ret = pd.DataFrame(results, index=ret_dates)
    df_ret = df_ret.dropna(how="all")
    print(f"\n  バックテスト完了: {len(df_ret)}営業日")
    return df_ret


# =====================================================================
# パフォーマンス評価
# =====================================================================

TRADING_DAYS = 252

def annual_return(r: pd.Series) -> float:
    """年率リターン（論文式 27）"""
    return r.mean() * TRADING_DAYS * 100

def annual_risk(r: pd.Series) -> float:
    """年率リスク（論文式 28）"""
    return r.std() * np.sqrt(TRADING_DAYS) * 100

def risk_return(r: pd.Series) -> float:
    ar = annual_return(r)
    risk = annual_risk(r)
    return ar / risk if risk > 0 else np.nan

def max_drawdown(r: pd.Series) -> float:
    """最大ドローダウン（論文式 30）、%表示"""
    cumret = (1 + r).cumprod()
    peak   = cumret.cummax()
    dd     = (cumret / peak - 1)
    return dd.min() * 100

def summarize_performance(df_ret: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df_ret.columns:
        r = df_ret[col].dropna()
        rows.append({
            "Strategy": col,
            "AR (%)":   round(annual_return(r), 2),
            "RISK (%)": round(annual_risk(r), 2),
            "R/R":      round(risk_return(r), 2),
            "MDD (%)":  round(max_drawdown(r), 2),
        })
    return pd.DataFrame(rows).set_index("Strategy")


# =====================================================================
# 可視化
# =====================================================================

def plot_cumulative_returns(df_ret: pd.DataFrame, save_path: str):
    """累積リターンのプロット（論文 図2 相当）"""
    fig, ax = plt.subplots(figsize=(12, 6))

    styles = {
        "PCA_SUB":   {"color": "#1f77b4", "lw": 2.5, "ls": "-",  "label": "PCA SUB（提案手法）"},
        "DOUBLE":    {"color": "#ff7f0e", "lw": 2.0, "ls": "--", "label": "DOUBLE"},
        "PCA_PLAIN": {"color": "#2ca02c", "lw": 1.5, "ls": "-.", "label": "PCA PLAIN"},
        "MOM":       {"color": "#d62728", "lw": 1.5, "ls": ":",  "label": "MOM（モメンタム）"},
    }

    for col, st in styles.items():
        if col not in df_ret.columns:
            continue
        r = df_ret[col].dropna()
        cum = (1 + r).cumprod()
        ax.plot(cum.index, cum.values, label=st["label"],
                color=st["color"], lw=st["lw"], ls=st["ls"])

    ax.set_title("各戦略の累積リターン（日次リバランス・コスト控除前）", fontsize=14)
    ax.set_xlabel("日付")
    ax.set_ylabel("累積資産（初期=1）")
    ax.legend(loc="upper left", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_annual_returns(df_ret: pd.DataFrame, save_path: str):
    """年次リターンの棒グラフ"""
    df_ret["year"] = df_ret.index.year
    annual = df_ret.groupby("year").apply(lambda g: (1 + g.drop(columns="year")).prod() - 1)

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharey=False)
    strategies = ["MOM", "PCA_PLAIN", "PCA_SUB", "DOUBLE"]
    colors     = ["#d62728", "#2ca02c", "#1f77b4", "#ff7f0e"]

    for ax, col, color in zip(axes.flat, strategies, colors):
        if col not in annual.columns:
            continue
        s = annual[col].dropna() * 100
        bars = ax.bar(s.index, s.values,
                      color=[color if v >= 0 else "#aaaaaa" for v in s.values],
                      edgecolor="white", width=0.7)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_title(col, fontsize=12)
        ax.set_ylabel("年率リターン (%)")
        ax.set_xlabel("年")
        ax.grid(True, axis="y", alpha=0.3)

    plt.suptitle("年次リターン（戦略別）", fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_drawdown(df_ret: pd.DataFrame, save_path: str):
    """ドローダウン推移"""
    fig, ax = plt.subplots(figsize=(12, 5))

    styles = {
        "PCA_SUB":   {"color": "#1f77b4", "lw": 2.5, "ls": "-"},
        "DOUBLE":    {"color": "#ff7f0e", "lw": 2.0, "ls": "--"},
        "PCA_PLAIN": {"color": "#2ca02c", "lw": 1.5, "ls": "-."},
        "MOM":       {"color": "#d62728", "lw": 1.5, "ls": ":"},
    }

    for col, st in styles.items():
        if col not in df_ret.columns:
            continue
        r    = df_ret[col].dropna()
        cum  = (1 + r).cumprod()
        peak = cum.cummax()
        dd   = (cum / peak - 1) * 100
        ax.fill_between(dd.index, dd.values, 0, alpha=0.15, color=st["color"])
        ax.plot(dd.index, dd.values, label=col, **{k: v for k, v in st.items()})

    ax.set_title("ドローダウン推移", fontsize=14)
    ax.set_xlabel("日付")
    ax.set_ylabel("ドローダウン (%)")
    ax.legend(loc="lower left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


# =====================================================================
# 感度分析
# =====================================================================

def sensitivity_analysis(us_cc: pd.DataFrame, jp_cc: pd.DataFrame,
                          jp_oc: pd.DataFrame, C0: np.ndarray,
                          all_tickers: list[str]) -> pd.DataFrame:
    """λ と K のパラメータ感度分析"""
    print("\n=== 感度分析 ===")
    NU = len(US_TICKERS)
    NJ = len(JP_TICKERS)
    cc_all = pd.concat([us_cc, jp_cc], axis=1)[all_tickers].dropna(how="all")

    lambda_grid = [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]
    k_grid      = [1, 2, 3, 4, 5]

    rows = []
    for lam in lambda_grid:
        for k in k_grid:
            rets = []
            dates_used = cc_all.index[L:]
            for date in dates_used:
                window_end   = cc_all.index.get_loc(date)
                window_start = window_end - L
                window_cc    = cc_all.iloc[window_start:window_end]
                if window_cc.isnull().mean().mean() > 0.3:
                    continue
                window_cc = window_cc.ffill().bfill()
                if window_cc.isnull().any().any():
                    continue
                if date not in jp_oc.index:
                    continue
                jp_ret_today = jp_oc.loc[date]
                if jp_ret_today.isnull().all():
                    continue
                us_today_raw = window_cc.iloc[-1, :NU].values
                z_us         = standardize_us_return(window_cc, us_today_raw)
                signal       = compute_signal_pca_sub(window_cc, C0, all_tickers, z_us, lam=lam, k=k)
                r            = jp_ret_today.values
                avail        = ~np.isnan(r)
                if avail.sum() == 0:
                    continue
                w = build_portfolio_weights(signal, NJ)
                w_a = w * avail
                pos = w_a > 0; neg = w_a < 0
                if pos.sum() > 0: w_a[pos] /= w_a[pos].sum()
                if neg.sum() > 0: w_a[neg] /= (-w_a[neg].sum())
                rets.append(np.dot(w_a, np.nan_to_num(r)))

            r_series = pd.Series(rets)
            rows.append({
                "λ": lam, "K": k,
                "AR (%)": round(annual_return(r_series), 2),
                "R/R":    round(risk_return(r_series), 2),
                "MDD (%)":round(max_drawdown(r_series), 2),
            })
            print(f"  λ={lam:.1f}, K={k}: AR={rows[-1]['AR (%)']:.1f}%, R/R={rows[-1]['R/R']:.2f}")

    return pd.DataFrame(rows)


# =====================================================================
# メイン
# =====================================================================

def main():
    print("=" * 60)
    print("  日米業種リードラグ投資戦略 バックテスト")
    print("=" * 60)

    # ---- データ取得 ----
    us_cc, jp_cc, jp_oc, _ = load_all_data()

    # ---- バックテスト ----
    df_ret = run_backtest(us_cc, jp_cc, jp_oc)

    # ---- パフォーマンス集計 ----
    print("\n=== パフォーマンス集計 ===")
    perf = summarize_performance(df_ret)
    print(perf.to_string())
    perf.to_csv(os.path.join(DATA_DIR, "performance_summary.csv"))

    # ---- 可視化 ----
    print("\n=== 可視化 ===")
    plot_cumulative_returns(df_ret, os.path.join(DATA_DIR, "cumulative_returns.png"))
    plot_annual_returns(df_ret,     os.path.join(DATA_DIR, "annual_returns.png"))
    plot_drawdown(df_ret,           os.path.join(DATA_DIR, "drawdown.png"))

    # ---- 日次リターンをCSV保存 ----
    df_ret.to_csv(os.path.join(DATA_DIR, "daily_returns.csv"))
    print(f"\n  日次リターン保存: daily_returns.csv")

    # ---- 感度分析（実行に時間がかかるためコメントアウト可） ----
    # all_tickers = US_TICKERS + JP_TICKERS
    # cc_all = pd.concat([us_cc, jp_cc], axis=1)[all_tickers].dropna(how="all")
    # cc_full = cc_all[cc_all.index <= CFULL_END_DATE].dropna()
    # V0 = build_prior_subspace(all_tickers)
    # C0 = build_prior_covariance(V0, cc_full)
    # sens = sensitivity_analysis(us_cc, jp_cc, jp_oc, C0, all_tickers)
    # sens.to_csv(os.path.join(DATA_DIR, "sensitivity.csv"), index=False)

    print("\n=== 完了 ===")
    return df_ret, perf


if __name__ == "__main__":
    df_ret, perf = main()
