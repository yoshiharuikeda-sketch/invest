"""
Fama-French アルファ検定
日米業種リードラグ投資戦略の超過収益が
既知のリスクファクターで説明できるかを統計的に検証する

使用するファクター:
  - Fama-French 3ファクター（日本）: Mkt-RF, SMB, HML
  - Carhart 4ファクター（日本）: 上記 + WML（モメンタム）
データソース: Kenneth French Data Library（pandas_datareader経由）
"""

import warnings
warnings.filterwarnings("ignore")

import os
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import statsmodels.api as sm
import pandas_datareader.data as web

matplotlib.rcParams["font.family"] = "Hiragino Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES = ["MOM", "PCA_PLAIN", "PCA_SUB", "DOUBLE"]
TRADING_DAYS = 252


# =====================================================================
# ファクターデータの取得
# =====================================================================

def fetch_japan_factors(start: str, end: str) -> pd.DataFrame:
    """
    Ken French Data Library から日本のFF3 + WMLを取得し結合する
    単位は % → 小数に変換して返す
    """
    cache = os.path.join(DATA_DIR, "cache_ff_japan.parquet")
    if os.path.exists(cache):
        print("  FFファクターキャッシュ読み込み")
        return pd.read_parquet(cache)

    print("  FFファクターダウンロード中...")
    ff3 = web.DataReader("Japan_3_Factors_Daily",  "famafrench", start=start, end=end)[0]
    mom = web.DataReader("Japan_Mom_Factor_Daily",  "famafrench", start=start, end=end)[0]

    factors = ff3.join(mom, how="left")
    # PeriodIndex → DatetimeIndex に変換
    if hasattr(factors.index, "to_timestamp"):
        factors.index = factors.index.to_timestamp()
    else:
        factors.index = pd.to_datetime(factors.index)
    factors.index.name = "Date"

    # % → 小数
    factors = factors / 100.0

    # 超過リターン用: RF（無リスク金利）は別列で保持
    factors = factors.rename(columns={"Mkt-RF": "MKT"})

    factors.to_parquet(cache)
    print(f"  期間: {factors.index[0].date()} 〜 {factors.index[-1].date()}")
    return factors


# =====================================================================
# OLS回帰（Newey-West標準誤差）
# =====================================================================

def run_factor_regression(
    ret: pd.Series,
    factors: pd.DataFrame,
    model: str = "FF3",
    lags: int = 5
) -> dict:
    """
    ret     : 戦略の日次リターン（小数）
    factors : FF3/Carhart4のファクター列（小数）
    model   : "FF3" または "Carhart4"
    lags    : Newey-Westのラグ数
    """
    if model == "FF3":
        cols = ["MKT", "SMB", "HML"]
    else:  # Carhart4
        cols = ["MKT", "SMB", "HML", "WML"]

    # 日次超過リターン（戦略リターン - 無リスク金利）
    df = pd.concat([ret, factors[cols + ["RF"]]], axis=1).dropna()
    df.columns = ["R"] + cols + ["RF"]
    df["excess_R"] = df["R"] - df["RF"]

    X = sm.add_constant(df[cols])
    y = df["excess_R"]

    ols = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})

    # アルファを年率換算
    alpha_daily = ols.params["const"]
    alpha_annual = alpha_daily * TRADING_DAYS * 100   # %/年

    t_alpha = ols.tvalues["const"]
    p_alpha = ols.pvalues["const"]

    stars = ""
    if p_alpha < 0.01:  stars = "***"
    elif p_alpha < 0.05: stars = "**"
    elif p_alpha < 0.10: stars = "*"

    result = {
        "model":        model,
        "alpha_ann_%":  round(alpha_annual, 2),
        "t_alpha":      round(t_alpha, 2),
        "stars":        stars,
        "adj_r2":       round(ols.rsquared_adj, 4),
        "n_obs":        int(ols.nobs),
    }

    # 各ファクターの係数・t値
    for col in cols:
        result[f"b_{col}"]    = round(ols.params[col], 4)
        result[f"t_{col}"]    = round(ols.tvalues[col], 2)
        result[f"p_{col}"]    = round(ols.pvalues[col], 4)

    result["_ols"] = ols   # 詳細表示用
    return result


# =====================================================================
# ローリングアルファ（時系列安定性の確認）
# =====================================================================

def rolling_alpha(
    ret: pd.Series,
    factors: pd.DataFrame,
    window: int = 252,
    model: str = "FF3"
) -> pd.Series:
    """252日ローリングウィンドウでアルファを推定し年率換算した系列を返す"""
    if model == "FF3":
        cols = ["MKT", "SMB", "HML"]
    else:
        cols = ["MKT", "SMB", "HML", "WML"]

    df = pd.concat([ret, factors[cols + ["RF"]]], axis=1).dropna()
    df.columns = ["R"] + cols + ["RF"]
    df["excess_R"] = df["R"] - df["RF"]

    alphas = []
    dates  = []

    for i in range(window, len(df)):
        sub   = df.iloc[i - window : i]
        X     = sm.add_constant(sub[cols])
        y     = sub["excess_R"]
        try:
            res = sm.OLS(y, X).fit()
            alphas.append(res.params["const"] * TRADING_DAYS * 100)
        except Exception:
            alphas.append(np.nan)
        dates.append(df.index[i])

    return pd.Series(alphas, index=dates, name=f"rolling_alpha_{model}")


# =====================================================================
# 可視化
# =====================================================================

def plot_factor_exposure(results_ff3: dict, results_c4: dict, save_path: str):
    """各ファクターへのエクスポージャー比較（FF3 / Carhart4）"""
    strategies = STRATEGIES
    factor_cols_ff3 = ["MKT", "SMB", "HML"]
    factor_cols_c4  = ["MKT", "SMB", "HML", "WML"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, results, cols, title in [
        (axes[0], results_ff3, factor_cols_ff3, "Fama-French 3ファクター"),
        (axes[1], results_c4,  factor_cols_c4,  "Carhart 4ファクター"),
    ]:
        x   = np.arange(len(strategies))
        w   = 0.8 / len(cols)
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

        for k, col in enumerate(cols):
            betas = [results[s][f"b_{col}"] for s in strategies]
            bars  = ax.bar(x + k * w - 0.4 + w / 2, betas,
                           width=w * 0.85, label=col, color=colors[k], alpha=0.8)

        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(strategies)
        ax.set_title(title, fontsize=12)
        ax.set_ylabel("係数（β）")
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)

    plt.suptitle("ファクターエクスポージャー（β係数）", fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_rolling_alpha(df_ret: pd.DataFrame, factors: pd.DataFrame, save_path: str):
    """PCA_SUBのローリングアルファ推移"""
    fig, ax = plt.subplots(figsize=(12, 5))

    for model, color, ls in [
        ("FF3",      "#1f77b4", "-"),
        ("Carhart4", "#ff7f0e", "--"),
    ]:
        ra = rolling_alpha(df_ret["PCA_SUB"], factors, window=252, model=model)
        ax.plot(ra.index, ra.values, label=f"ローリングα ({model})", color=color, ls=ls, lw=2)

    ax.axhline(0, color="black", lw=0.8)
    ax.fill_between(ra.index, ra.values, 0, alpha=0.08, color="#1f77b4")
    ax.set_title("PCA SUBのローリングアルファ推移（252日ウィンドウ、年率%）", fontsize=13)
    ax.set_xlabel("日付")
    ax.set_ylabel("アルファ（%/年）")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_alpha_summary(results_ff3: dict, results_c4: dict, save_path: str):
    """全戦略のアルファ比較（FF3 / Carhart4 並べて表示）"""
    fig, ax = plt.subplots(figsize=(10, 5))

    strategies = STRATEGIES
    x = np.arange(len(strategies))
    w = 0.35
    colors_ff3 = ["#1f77b4"] * len(strategies)
    colors_c4  = ["#ff7f0e"] * len(strategies)

    alphas_ff3 = [results_ff3[s]["alpha_ann_%"] for s in strategies]
    alphas_c4  = [results_c4[s]["alpha_ann_%"]  for s in strategies]
    stars_ff3  = [results_ff3[s]["stars"]        for s in strategies]
    stars_c4   = [results_c4[s]["stars"]         for s in strategies]

    bars1 = ax.bar(x - w / 2, alphas_ff3, width=w, label="FF3アルファ",
                   color=colors_ff3, alpha=0.8, edgecolor="white")
    bars2 = ax.bar(x + w / 2, alphas_c4,  width=w, label="Carhart4アルファ",
                   color=colors_c4,  alpha=0.8, edgecolor="white")

    # t値とスターを表示
    for bar, alpha, star in zip(bars1, alphas_ff3, stars_ff3):
        h = bar.get_height()
        ypos = h + 0.5 if h >= 0 else h - 2.5
        ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                f"{alpha:.1f}%{star}", ha="center", va="bottom", fontsize=9, color="#1f77b4")
    for bar, alpha, star in zip(bars2, alphas_c4, stars_c4):
        h = bar.get_height()
        ypos = h + 0.5 if h >= 0 else h - 2.5
        ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                f"{alpha:.1f}%{star}", ha="center", va="bottom", fontsize=9, color="#ff7f0e")

    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("年率アルファ (%)")
    ax.set_title("ファクター調整後アルファ（***:1% **:5% *:10% 有意）", fontsize=13)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


# =====================================================================
# 結果表の整形・表示
# =====================================================================

def format_regression_table(results: dict, model: str) -> pd.DataFrame:
    """回帰結果を論文スタイルの表に整形"""
    if model == "FF3":
        factor_cols = ["MKT", "SMB", "HML"]
    else:
        factor_cols = ["MKT", "SMB", "HML", "WML"]

    rows = []
    for s in STRATEGIES:
        r = results[s]
        row = {
            "戦略": s,
            "α (%/年)": f"{r['alpha_ann_%']:.2f}{r['stars']}",
            "t(α)": f"({r['t_alpha']:.2f})",
        }
        for col in factor_cols:
            row[col] = f"{r[f'b_{col}']:.3f}"
            row[f"t({col})"] = f"({r[f't_{col}']:.2f})"
        row["Adj.R²"] = f"{r['adj_r2']:.4f}"
        row["N"] = r["n_obs"]
        rows.append(row)

    return pd.DataFrame(rows).set_index("戦略")


def print_regression_summary(results_ff3: dict, results_c4: dict):
    """コンソールへの整形出力"""
    for model, results in [("FF3", results_ff3), ("Carhart4", results_c4)]:
        factor_cols = ["MKT", "SMB", "HML"] if model == "FF3" else ["MKT", "SMB", "HML", "WML"]
        print(f"\n{'='*65}")
        print(f"  {model} ファクター回帰結果（Newey-West t値）")
        print(f"{'='*65}")
        header = f"{'戦略':<12} {'α(%/年)':>10} {'t(α)':>8}"
        for c in factor_cols:
            header += f" {c:>8} {'t':>6}"
        header += f" {'Adj.R²':>8}"
        print(header)
        print("-" * 65)
        for s in STRATEGIES:
            r = results[s]
            line = f"{s:<12} {r['alpha_ann_%']:>8.2f}{r['stars']:<2} ({r['t_alpha']:>5.2f})"
            for c in factor_cols:
                line += f" {r[f'b_{c}']:>8.4f} ({r[f't_{c}']:>4.2f})"
            line += f" {r['adj_r2']:>8.4f}"
            print(line)
        print("-" * 65)
        print("  注: ***, **, * はそれぞれ1%, 5%, 10%水準で有意（Newey-West t値）")


# =====================================================================
# メイン
# =====================================================================

def main():
    print("=" * 65)
    print("  Fama-French アルファ検定")
    print("=" * 65)

    # ---- 戦略リターンの読み込み ----
    ret_path = os.path.join(DATA_DIR, "daily_returns.csv")
    if not os.path.exists(ret_path):
        raise FileNotFoundError(
            "daily_returns.csv が見つかりません。先に backtest.py を実行してください。"
        )
    df_ret = pd.read_csv(ret_path, index_col=0, parse_dates=True)
    print(f"\n  戦略リターン読み込み: {len(df_ret)}日, {df_ret.index[0].date()} 〜 {df_ret.index[-1].date()}")

    # ---- FFファクターデータの取得 ----
    print("\n=== FFファクターデータ取得 ===")
    start = df_ret.index[0].strftime("%Y-%m-%d")
    end   = df_ret.index[-1].strftime("%Y-%m-%d")
    factors = fetch_japan_factors(start, end)

    # インデックス型を合わせる（timezone除去）
    df_ret.index  = pd.to_datetime(df_ret.index).tz_localize(None)
    factors.index = pd.to_datetime(factors.index).tz_localize(None)

    # ---- 回帰分析 ----
    print("\n=== 回帰分析実行 ===")
    results_ff3 = {}
    results_c4  = {}

    for s in STRATEGIES:
        ret = df_ret[s].dropna()
        results_ff3[s] = run_factor_regression(ret, factors, model="FF3",      lags=5)
        results_c4[s]  = run_factor_regression(ret, factors, model="Carhart4", lags=5)
        print(f"  {s}: FF3α={results_ff3[s]['alpha_ann_%']:.2f}%{results_ff3[s]['stars']} "
              f"(t={results_ff3[s]['t_alpha']:.2f}), "
              f"C4α={results_c4[s]['alpha_ann_%']:.2f}%{results_c4[s]['stars']} "
              f"(t={results_c4[s]['t_alpha']:.2f})")

    # ---- テーブル表示 ----
    print_regression_summary(results_ff3, results_c4)

    # ---- CSV保存 ----
    table_ff3 = format_regression_table(results_ff3, "FF3")
    table_c4  = format_regression_table(results_c4,  "Carhart4")
    table_ff3.to_csv(os.path.join(DATA_DIR, "alpha_ff3.csv"))
    table_c4.to_csv(os.path.join(DATA_DIR,  "alpha_carhart4.csv"))
    print("\n  テーブル保存: alpha_ff3.csv, alpha_carhart4.csv")

    # ---- 可視化 ----
    print("\n=== 可視化 ===")
    plot_alpha_summary(
        results_ff3, results_c4,
        os.path.join(DATA_DIR, "alpha_summary.png")
    )
    plot_factor_exposure(
        results_ff3, results_c4,
        os.path.join(DATA_DIR, "factor_exposure.png")
    )
    plot_rolling_alpha(
        df_ret, factors,
        os.path.join(DATA_DIR, "rolling_alpha.png")
    )

    print("\n=== 完了 ===")
    return results_ff3, results_c4


if __name__ == "__main__":
    results_ff3, results_c4 = main()
