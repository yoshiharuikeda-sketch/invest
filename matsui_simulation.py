"""
松井証券 コスト込みシミュレーション
====================================
松井証券のコスト構造:
  【手数料】ボックスレート（1日の約定代金合計で決まる）
    - 〜50万円/日  : 0円（無料）
    - 〜100万円/日 : 1,100円
    - 〜200万円/日 : 2,200円
    - 〜300万円/日 : 3,300円
    - 以降100万円ごとに1,100円加算

  【スプレッド】TOPIX-17業種ETFは流動性が低いため別途スプレッドコスト発生
    - 1617.T〜1633.T : 推定片道スプレッド 30〜100bp（銘柄・日によって変動）
    - 楽観シナリオ: 30bp / 中央シナリオ: 60bp / 悲観シナリオ: 100bp

  【API】
    - REST APIで個人利用可（無料）
    - 日本株ETFの注文・照会に対応

注意: 手数料・スプレッドは2026年時点の推定値です。
      必ず松井証券公式サイトで最新情報をご確認ください。
"""

import warnings
warnings.filterwarnings("ignore")

import os
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

matplotlib.rcParams["font.family"] = "Hiragino Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

DATA_DIR     = os.path.dirname(os.path.abspath(__file__))
TRADING_DAYS = 252
NJ           = 17   # 日本業種ETF数
N_EACH       = round(NJ * 0.3)   # 5銘柄（ロング/ショート各）
W_EACH       = 1.0 / N_EACH
GROSS_EXP    = N_EACH * W_EACH * 2   # = 2.0

# =====================================================================
# 松井証券 コスト設定
# =====================================================================

# ボックスレート（1日の約定代金合計 → 手数料円）
BOX_RATE = [
    (500_000,    0),       # 〜50万円: 無料
    (1_000_000,  1_100),   # 〜100万円: 1,100円
    (2_000_000,  2_200),   # 〜200万円: 2,200円
    (3_000_000,  3_300),   # 〜300万円: 3,300円
]
BOX_RATE_PER_EXTRA = 1_100   # 300万円超: 100万円ごとに1,100円追加

# スプレッドシナリオ（片道 bp）
SPREAD_SCENARIOS = {
    "楽観（30bp）":  30,
    "中央（60bp）":  60,
    "悲観（100bp）": 100,
}


def box_rate_fee(daily_value_yen: float) -> float:
    """ボックスレートから手数料（円）を計算"""
    for threshold, fee in BOX_RATE:
        if daily_value_yen <= threshold:
            return float(fee)
    # 300万円超
    excess = daily_value_yen - 3_000_000
    extra_units = int(np.ceil(excess / 1_000_000))
    return 3_300.0 + extra_units * BOX_RATE_PER_EXTRA


def commission_bp(portfolio_value_yen: float) -> float:
    """
    ポートフォリオ規模から手数料を bp で換算
    毎日10銘柄（ロング5+ショート5）を売買する想定
    daily_value = portfolio_value × グロスエクスポージャー
    """
    daily_value = portfolio_value_yen * GROSS_EXP
    fee_yen = box_rate_fee(daily_value)
    # 往復（買い+売り）で2倍
    rt_fee_yen = fee_yen * 2
    rt_fee_bp  = rt_fee_yen / daily_value * 10000
    return rt_fee_bp


# =====================================================================
# パフォーマンス指標
# =====================================================================

def annual_return(r: pd.Series) -> float:
    return r.mean() * TRADING_DAYS * 100

def annual_risk(r: pd.Series) -> float:
    return r.std() * np.sqrt(TRADING_DAYS) * 100

def risk_return(r: pd.Series) -> float:
    ar = annual_return(r); risk = annual_risk(r)
    return ar / risk if risk > 0 else np.nan

def max_drawdown(r: pd.Series) -> float:
    cum = (1 + r).cumprod()
    return ((cum / cum.cummax()) - 1).min() * 100

def perf(r: pd.Series) -> dict:
    return {
        "AR(%)":   round(annual_return(r), 2),
        "RISK(%)": round(annual_risk(r), 2),
        "R/R":     round(risk_return(r), 2),
        "MDD(%)":  round(max_drawdown(r), 2),
    }


# =====================================================================
# 1. ポートフォリオ規模別 コスト分析
# =====================================================================

def portfolio_size_analysis(r_gross: pd.Series) -> pd.DataFrame:
    """
    ポートフォリオ規模（運用資産額）によってボックスレート手数料が変わる。
    規模別の実効コスト（手数料+スプレッド）と純リターンを試算。
    """
    sizes = [
        100_000,     # 10万円
        300_000,     # 30万円
        500_000,     # 50万円
        1_000_000,   # 100万円
        3_000_000,   # 300万円
        5_000_000,   # 500万円
        10_000_000,  # 1,000万円
        30_000_000,  # 3,000万円
    ]

    rows = []
    for pv in sizes:
        daily_value = pv * GROSS_EXP
        fee_yen     = box_rate_fee(daily_value)
        rt_fee_yen  = fee_yen * 2
        comm_bp     = rt_fee_yen / daily_value * 10000 if daily_value > 0 else 0

        annual_to   = GROSS_EXP * TRADING_DAYS   # 504

        for spread_name, spread_bp in SPREAD_SCENARIOS.items():
            total_rt_bp   = comm_bp + spread_bp * 2   # 往復コスト合計
            annual_cost   = annual_to * total_rt_bp / 10000 * 100   # %

            daily_cost = GROSS_EXP * (total_rt_bp / 10000)
            r_net = r_gross - daily_cost

            rows.append({
                "規模":          f"{pv/10000:.0f}万円",
                "スプレッド想定":  spread_name,
                "手数料(往復bp)":  round(comm_bp, 1),
                "スプレッド(往復bp)": spread_bp * 2,
                "合計往復コスト(bp)": round(total_rt_bp, 1),
                "年間コスト(%)":   round(annual_cost, 1),
                **perf(r_net),
            })

    return pd.DataFrame(rows)


# =====================================================================
# 2. リバランス頻度別シミュレーション（松井証券）
# =====================================================================

def resample_strategy(r_daily: pd.Series, freq: str) -> pd.Series:
    df = r_daily.to_frame("r")
    df["period"] = df.index.to_period(freq)
    period_rets = df.groupby("period").apply(lambda g: (1 + g["r"]).prod() - 1)
    period_rets.index = period_rets.index.to_timestamp()
    return period_rets


def rebalance_freq_analysis(r_gross: pd.Series, portfolio_value_yen: float = 3_000_000) -> pd.DataFrame:
    """
    リバランス頻度（日次・週次・月次）× スプレッドシナリオ別パフォーマンス
    """
    daily_value = portfolio_value_yen * GROSS_EXP
    fee_yen     = box_rate_fee(daily_value)
    comm_bp     = fee_yen * 2 / daily_value * 10000

    rows = []
    for freq_name, freq_code, trades_per_year in [
        ("日次", "D",  252),
        ("週次", "W",   52),
        ("月次", "M",   12),
    ]:
        r_base = r_gross if freq_code == "D" else resample_strategy(r_gross, freq_code)
        annual_to = GROSS_EXP * trades_per_year

        for spread_name, spread_bp in SPREAD_SCENARIOS.items():
            total_rt_bp = comm_bp + spread_bp * 2
            cost_per_period = annual_to * total_rt_bp / 10000 / len(r_base)
            r_net = r_base - cost_per_period

            rows.append({
                "頻度":          freq_name,
                "スプレッド":     spread_name,
                "年間TO(倍)":    round(annual_to),
                "年間コスト(%)":  round(annual_to * total_rt_bp / 10000 * 100, 1),
                **perf(r_net),
            })

    return pd.DataFrame(rows)


# =====================================================================
# 3. 損益分岐規模の計算
# =====================================================================

def breakeven_portfolio_size(r_gross: pd.Series) -> pd.DataFrame:
    """
    スプレッドシナリオ別に「損益分岐となるポートフォリオ規模」を求める
    純AR = グロスAR - 年間コスト = 0 となる規模
    """
    gross_ar  = annual_return(r_gross) / 100
    annual_to = GROSS_EXP * TRADING_DAYS

    rows = []
    # 規模を細かくスキャン
    for pv in np.logspace(4, 8, 200):   # 1万円〜1億円
        daily_value = pv * GROSS_EXP
        fee_yen     = box_rate_fee(daily_value)
        comm_bp     = fee_yen * 2 / daily_value * 10000 if daily_value > 0 else 0

        for spread_name, spread_bp in SPREAD_SCENARIOS.items():
            total_rt_bp = comm_bp + spread_bp * 2
            annual_cost = annual_to * total_rt_bp / 10000
            net_ar      = gross_ar - annual_cost
            rows.append({
                "規模(万円)":    round(pv / 10000, 1),
                "スプレッド":    spread_name,
                "年間コスト(%)": round(annual_cost * 100, 2),
                "純AR(%)":      round(net_ar * 100, 2),
            })

    return pd.DataFrame(rows)


# =====================================================================
# 可視化
# =====================================================================

def plot_portfolio_size_impact(df: pd.DataFrame, save_path: str):
    """規模別純年率リターン（スプレッドシナリオ別）"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    colors = {"楽観（30bp）": "#2ca02c", "中央（60bp）": "#ff7f0e", "悲観（100bp）": "#d62728"}
    markers = {"楽観（30bp）": "o", "中央（60bp）": "s", "悲観（100bp）": "^"}

    sizes_label = df["規模"].unique()
    x = np.arange(len(sizes_label))

    for ax, metric, ylabel in [
        (axes[0], "AR(%)",  "純年率リターン (%)"),
        (axes[1], "R/R",    "リスク・リターン比 (R/R)"),
    ]:
        w = 0.25
        for k, (sp_name, color) in enumerate(colors.items()):
            sub = df[df["スプレッド想定"] == sp_name]
            ax.bar(x + (k - 1) * w, sub[metric].values, width=w * 0.9,
                   label=sp_name, color=color, alpha=0.8)

        ax.axhline(0, color="black", lw=0.8)
        if metric == "R/R":
            ax.axhline(1.0, color="gray", lw=1.0, ls="--", alpha=0.7, label="R/R=1.0")
        ax.set_xticks(x)
        ax.set_xticklabels(sizes_label, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_title(f"規模別{ylabel}（日次リバランス）", fontsize=11)
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)

    plt.suptitle("松井証券 ポートフォリオ規模 × スプレッドシナリオ別パフォーマンス", fontsize=13)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_breakeven_curve(be_df: pd.DataFrame, save_path: str):
    """損益分岐曲線（規模 vs 純AR）"""
    fig, ax = plt.subplots(figsize=(10, 5))

    colors = {"楽観（30bp）": "#2ca02c", "中央（60bp）": "#ff7f0e", "悲観（100bp）": "#d62728"}

    for sp_name, color in colors.items():
        sub = be_df[be_df["スプレッド"] == sp_name].sort_values("規模(万円)")
        ax.plot(sub["規模(万円)"], sub["純AR(%)"], color=color, lw=2.5, label=sp_name)

        # 損益分岐点（純AR=0）を探す
        be_row = sub[sub["純AR(%)"] >= 0].head(1)
        if not be_row.empty:
            be_size = be_row["規模(万円)"].values[0]
            ax.axvline(be_size, color=color, lw=1.2, ls="--", alpha=0.6)
            ax.text(be_size * 1.05, -5, f"{be_size:.0f}万円", color=color,
                    fontsize=9, va="top")

    ax.axhline(0, color="black", lw=1.0, label="損益分岐（AR=0%）")
    ax.set_xscale("log")
    ax.set_xlabel("ポートフォリオ規模（万円）", fontsize=11)
    ax.set_ylabel("純年率リターン (%)", fontsize=11)
    ax.set_title("松井証券 損益分岐ポートフォリオ規模\n（日次リバランス・全替え想定）", fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, which="both")
    ax.set_xlim(1, 10_000)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_freq_heatmap(freq_df: pd.DataFrame, save_path: str):
    """リバランス頻度 × スプレッド の AR ヒートマップ"""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    for ax, metric, title in [
        (axes[0], "AR(%)",  "純年率リターン (%)"),
        (axes[1], "R/R",    "R/R"),
    ]:
        pivot = freq_df.pivot_table(values=metric, index="スプレッド", columns="頻度")[["日次","週次","月次"]]
        im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto",
                       vmin=pivot.values.min(), vmax=max(pivot.values.max(), 0.1))
        plt.colorbar(im, ax=ax)

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_yticks(range(len(pivot.index)))
        ax.set_xticklabels(pivot.columns)
        ax.set_yticklabels(pivot.index)
        ax.set_title(title, fontsize=11)

        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.values[i, j]
                ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                        fontsize=11, fontweight="bold",
                        color="white" if abs(val) > pivot.values.max() * 0.5 else "black")

    plt.suptitle("松井証券 リバランス頻度 × スプレッドシナリオ（300万円ポートフォリオ想定）",
                 fontsize=12)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_cumulative_scenarios(r_gross: pd.Series, save_path: str):
    """主要シナリオの累積リターン比較"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    portfolio_yen = 3_000_000
    daily_value   = portfolio_yen * GROSS_EXP
    fee_yen       = box_rate_fee(daily_value)
    comm_bp       = fee_yen * 2 / daily_value * 10000
    annual_to     = GROSS_EXP * TRADING_DAYS

    scenarios = []
    # 日次シナリオ
    for sp_name, sp_bp in SPREAD_SCENARIOS.items():
        total_rt_bp = comm_bp + sp_bp * 2
        daily_cost  = GROSS_EXP * total_rt_bp / 10000
        r_net       = r_gross - daily_cost
        scenarios.append((f"日次・{sp_name}", r_net, "-"))

    # 週次（中央スプレッド）
    r_weekly = resample_strategy(r_gross, "W")
    for sp_name, sp_bp in [("中央（60bp）", 60)]:
        total_rt_bp = comm_bp + sp_bp * 2
        weekly_to   = GROSS_EXP * 52
        cost_per_week = weekly_to * total_rt_bp / 10000 / len(r_weekly)
        r_net = r_weekly - cost_per_week
        scenarios.append((f"週次・{sp_name}", r_net, "--"))

    # コストなし参考
    scenarios.append(("コストなし（参考）", r_gross, ":"))

    colors = ["#2ca02c", "#ff7f0e", "#d62728", "#9467bd", "#1f77b4"]

    for ax, is_dd in [(ax1, False), (ax2, True)]:
        for (name, r_net, ls), color in zip(scenarios, colors):
            cum  = (1 + r_net).cumprod()
            ar   = annual_return(r_net)
            rr   = risk_return(r_net)
            if is_dd:
                dd = (cum / cum.cummax() - 1) * 100
                ax.plot(dd.index, dd.values, label=name, color=color, ls=ls, lw=2)
            else:
                label = f"{name}\n(AR={ar:.1f}%, R/R={rr:.2f})"
                ax.plot(cum.index, cum.values, label=label, color=color, ls=ls, lw=2)

        ax.axhline(1 if not is_dd else 0, color="gray", lw=0.5, ls=":")
        ax.set_xlabel("日付")
        ax.set_ylabel("累積資産（初期=1）" if not is_dd else "ドローダウン (%)")
        ax.set_title("累積リターン" if not is_dd else "ドローダウン推移", fontsize=11)
        ax.legend(loc="upper left" if not is_dd else "lower left", fontsize=7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.grid(True, alpha=0.3)

    plt.suptitle("松井証券 シナリオ別累積リターン（300万円ポートフォリオ）", fontsize=13)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


# =====================================================================
# メイン
# =====================================================================

def main():
    print("=" * 70)
    print("  松井証券 取引コスト込みシミュレーション")
    print("=" * 70)

    ret_path = os.path.join(DATA_DIR, "daily_returns.csv")
    if not os.path.exists(ret_path):
        raise FileNotFoundError("daily_returns.csv が見つかりません。先に backtest.py を実行してください。")
    df_ret = pd.read_csv(ret_path, index_col=0, parse_dates=True)
    df_ret.index = pd.to_datetime(df_ret.index).tz_localize(None)
    r_gross = df_ret["PCA_SUB"].dropna()
    print(f"\n  グロスデータ: {len(r_gross)}日  AR={annual_return(r_gross):.2f}%")

    # ---- 1. ボックスレート手数料の確認 ----
    print("\n=== 1. 松井証券 ボックスレート手数料（往復）===")
    print(f"  {'規模':>12}  {'1日約定代金':>14}  {'手数料/日(円)':>14}  {'往復手数料(bp)':>14}")
    print(f"  {'-'*12}  {'-'*14}  {'-'*14}  {'-'*14}")
    for pv in [100_000, 300_000, 500_000, 1_000_000, 3_000_000, 5_000_000, 10_000_000]:
        dv   = pv * GROSS_EXP
        fee  = box_rate_fee(dv)
        bp   = fee * 2 / dv * 10000
        print(f"  {pv/10000:>10.0f}万円  {dv/10000:>12.0f}万円  {fee:>14,.0f}円  {bp:>14.1f}bp")

    # ---- 2. 規模別パフォーマンス ----
    print("\n=== 2. ポートフォリオ規模別パフォーマンス（日次・全替え）===")
    size_df = portfolio_size_analysis(r_gross)
    pivot = size_df[size_df["スプレッド想定"] == "中央（60bp）"][
        ["規模", "手数料(往復bp)", "スプレッド(往復bp)", "合計往復コスト(bp)", "年間コスト(%)", "AR(%)", "R/R"]
    ].reset_index(drop=True)
    print(f"\n  ▼ 中央スプレッド（60bp）シナリオ:")
    print(pivot.to_string(index=False))
    size_df.to_csv(os.path.join(DATA_DIR, "matsui_size_analysis.csv"), index=False, encoding="utf-8-sig")

    # ---- 3. リバランス頻度比較（300万円）----
    print("\n=== 3. リバランス頻度 × スプレッドシナリオ（300万円）===")
    freq_df = rebalance_freq_analysis(r_gross, portfolio_value_yen=3_000_000)
    pivot_ar = freq_df.pivot_table(values="AR(%)", index="スプレッド", columns="頻度")[["日次","週次","月次"]]
    pivot_rr = freq_df.pivot_table(values="R/R",   index="スプレッド", columns="頻度")[["日次","週次","月次"]]
    print("\n  純年率リターン (%):")
    print(pivot_ar.to_string())
    print("\n  R/R:")
    print(pivot_rr.to_string())
    freq_df.to_csv(os.path.join(DATA_DIR, "matsui_freq_analysis.csv"), index=False, encoding="utf-8-sig")

    # ---- 4. 損益分岐規模 ----
    print("\n=== 4. 損益分岐ポートフォリオ規模 ===")
    be_df = breakeven_portfolio_size(r_gross)
    for sp_name in SPREAD_SCENARIOS:
        sub    = be_df[be_df["スプレッド"] == sp_name].sort_values("規模(万円)")
        be_row = sub[sub["純AR(%)"] >= 0].head(1)
        if not be_row.empty:
            print(f"  {sp_name}: 損益分岐 ≈ {be_row['規模(万円)'].values[0]:.0f}万円以上")
        else:
            print(f"  {sp_name}: いかなる規模でも黒字化困難")

    # ---- 可視化 ----
    print("\n=== 可視化 ===")
    plot_portfolio_size_impact(
        size_df, os.path.join(DATA_DIR, "matsui_size_impact.png"))
    plot_breakeven_curve(
        be_df,   os.path.join(DATA_DIR, "matsui_breakeven.png"))
    plot_freq_heatmap(
        freq_df, os.path.join(DATA_DIR, "matsui_freq_heatmap.png"))
    plot_cumulative_scenarios(
        r_gross, os.path.join(DATA_DIR, "matsui_cumulative.png"))

    # ---- 総括 ----
    print("\n" + "=" * 70)
    print("  【松井証券での実運用 総括】")
    print("=" * 70)

    # 中央スプレッド・日次での損益分岐規模を取得
    be_mid = be_df[be_df["スプレッド"] == "中央（60bp）"].sort_values("規模(万円)")
    be_size_mid = be_mid[be_mid["純AR(%)"] >= 0].head(1)["規模(万円)"].values
    be_size_str = f"{be_size_mid[0]:.0f}万円" if len(be_size_mid) > 0 else "困難"

    print(f"""
  【手数料の優位性】
  ・50万円/日の約定代金まで手数料無料 → 小規模ポートフォリオで有利
  ・ただし TOPIX-17 ETF のスプレッドが支配的なコスト

  【日次リバランス・中央スプレッド（60bp）の場合】
  ・損益分岐ポートフォリオ規模: 約 {be_size_str}
  ・それ未満では手数料が無料でもスプレッドで赤字

  【現実的な選択肢】
  ① 週次リバランス + 楽観スプレッド(30bp):
     → AR ≈ {freq_df[(freq_df['頻度']=='週次') & (freq_df['スプレッド']=='楽観（30bp）')]['AR(%)'].values[0]:.1f}%、R/R ≈ {freq_df[(freq_df['頻度']=='週次') & (freq_df['スプレッド']=='楽観（30bp）')]['R/R'].values[0]:.2f}

  ② 週次リバランス + 中央スプレッド(60bp):
     → AR ≈ {freq_df[(freq_df['頻度']=='週次') & (freq_df['スプレッド']=='中央（60bp）')]['AR(%)'].values[0]:.1f}%、R/R ≈ {freq_df[(freq_df['頻度']=='週次') & (freq_df['スプレッド']=='中央（60bp）')]['R/R'].values[0]:.2f}

  ③ 月次リバランス + 中央スプレッド(60bp):
     → AR ≈ {freq_df[(freq_df['頻度']=='月次') & (freq_df['スプレッド']=='中央（60bp）')]['AR(%)'].values[0]:.1f}%、R/R ≈ {freq_df[(freq_df['頻度']=='月次') & (freq_df['スプレッド']=='中央（60bp）')]['R/R'].values[0]:.2f}

  ▶ 推奨: 週次リバランス（月曜日のみ執行）+ スプレッドの狭い時間帯（後場）で発注
  ▶ 注意: スプレッドは実測値ではなく推定値です。
          実際の取引前に各ETFの板を確認することを強く推奨します。
""")

    print("=== 完了 ===")
    return size_df, freq_df, be_df


if __name__ == "__main__":
    size_df, freq_df, be_df = main()
