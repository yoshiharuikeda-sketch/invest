"""
取引コスト込みシミュレーション（改訂版）
日米業種リードラグ投資戦略の実運用時の収益性を検証する

発見された問題:
  年間ターンオーバー ≈ 504倍（毎日全ポジション入れ替え仮定）
  損益分岐コスト ≈ 片道1.9bp = 0.019%
  TOPIX-17 ETFの典型的片道コスト ≈ 50〜200bp
  → そのまま日次リバランスでは取引コストが超過リターンを大幅に上回る

改善アプローチ:
  1. ターンオーバー削減（シグナル持続性の利用）
  2. リバランス頻度の引き下げ（週次・月次）
  3. 代替商品への置き換え（日経225先物・TOPIX先物）
  4. ポジションの段階的入れ替え（閾値フィルター）
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

DATA_DIR    = os.path.dirname(os.path.abspath(__file__))
TRADING_DAYS = 252
JP_TICKERS   = [
    "1617.T","1618.T","1619.T","1620.T","1621.T","1622.T",
    "1623.T","1624.T","1625.T","1626.T","1627.T","1628.T",
    "1629.T","1630.T","1631.T","1632.T","1633.T"
]

# 典型的なコスト水準（片道 bp）
COST_LEVELS = {
    "TOPIX-17 ETF（個人）":   150,   # スプレッド100bp + 手数料50bp
    "TOPIX-17 ETF（機関）":    30,   # スプレッド20bp  + 手数料10bp
    "日経225 mini先物":          5,   # ほぼスプレッドのみ
    "TOPIX先物":                 5,
}


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

def perf_summary(r: pd.Series) -> dict:
    return {
        "AR(%)":   round(annual_return(r), 2),
        "RISK(%)": round(annual_risk(r), 2),
        "R/R":     round(risk_return(r), 2),
        "MDD(%)":  round(max_drawdown(r), 2),
    }


# =====================================================================
# 1. 損益分岐点の解析
# =====================================================================

def breakeven_analysis(r_gross: pd.Series) -> dict:
    """
    損益分岐点コストを計算する

    戦略リターン = グロスリターン - コスト × 年間ターンオーバー
    損益分岐点: コスト = グロスリターン / 年間ターンオーバー
    """
    NJ       = len(JP_TICKERS)
    n_each   = round(NJ * 0.3)          # 5銘柄
    n_traded = n_each * 2               # 10銘柄（ロング5+ショート5）
    w_each   = 1.0 / n_each             # 0.2
    gross_exposure = n_each * w_each + n_each * w_each   # = 2.0

    # 毎日100%入れ替えの場合の年間ターンオーバー
    annual_to_full = gross_exposure * TRADING_DAYS   # = 504

    gross_ar = annual_return(r_gross) / 100          # 小数

    # 損益分岐点（往復コスト）
    be_rt = gross_ar / annual_to_full
    be_ow = be_rt / 2

    return {
        "グロスAR(%)":         round(gross_ar * 100, 2),
        "グロスエクスポージャー": gross_exposure,
        "日次グロスターンオーバー": gross_exposure,
        "年間ターンオーバー(倍)":  annual_to_full,
        "損益分岐 往復(bp)":   round(be_rt * 10000, 2),
        "損益分岐 片道(bp)":   round(be_ow * 10000, 2),
        "_be_rt": be_rt,
    }


# =====================================================================
# 2. 実コスト水準によるシミュレーション
# =====================================================================

def simulate_with_cost(
    r_gross: pd.Series,
    oneway_bp: float,
    daily_turnover_ratio: float = 1.0   # 1.0 = 毎日全替え
) -> pd.Series:
    """
    片道コスト oneway_bp (bp) を適用した純リターン系列を返す

    daily_turnover_ratio: 1日あたりの実際のターンオーバー（0〜1）
      1.0 = 全ポジション毎日入れ替え（最悪ケース）
      0.5 = 平均で半分のポジションが入れ替わる
    """
    NJ     = len(JP_TICKERS)
    n_each = round(NJ * 0.3)
    w_each = 1.0 / n_each
    gross_exp = n_each * w_each * 2    # = 2.0

    oneway_ratio = oneway_bp / 10000
    rt_cost      = oneway_ratio * 2    # 往復

    daily_cost = gross_exp * daily_turnover_ratio * rt_cost
    return r_gross - daily_cost


# =====================================================================
# 3. リバランス頻度の引き下げ（週次・月次）
# =====================================================================

def resample_strategy(r_daily: pd.Series, freq: str = "W") -> pd.Series:
    """
    日次リターンを週次 or 月次にリサンプリング
    週次/月次での入れ替えを仮定した戦略リターン（コスト前）

    freq: "W"=週次, "M"=月次
    """
    # 各期間の「保有リターン」: 期間内の最初の日のシグナルで固定し、
    # 期間全体のリターンを累積
    df = r_daily.to_frame("r")
    if freq == "W":
        df["period"] = df.index.to_period("W")
    elif freq == "M":
        df["period"] = df.index.to_period("M")

    def period_ret(g):
        return (1 + g["r"]).prod() - 1

    # 各期間の累積リターン（1エントリー/期間）
    period_rets = df.groupby("period").apply(period_ret)
    period_rets.index = period_rets.index.to_timestamp()
    return period_rets


def compare_rebalance_freq(r_daily: pd.Series) -> pd.DataFrame:
    """日次・週次・月次のリバランス頻度比較"""
    NJ       = len(JP_TICKERS)
    n_each   = round(NJ * 0.3)
    w_each   = 1.0 / n_each
    gross_exp = n_each * w_each * 2    # = 2.0

    rows = []
    for freq_name, freq_code, trades_per_year in [
        ("日次", "D",  252),
        ("週次", "W",   52),
        ("月次", "M",   12),
    ]:
        if freq_code == "D":
            r = r_daily
        else:
            r = resample_strategy(r_daily, freq_code)

        annual_to = gross_exp * trades_per_year    # 年間ターンオーバー

        # コスト水準ごとの純リターン
        for inst, oneway_bp in COST_LEVELS.items():
            rt_cost = oneway_bp / 10000 * 2
            daily_cost_equiv = annual_to * rt_cost / len(r)  # 1期間あたりのコスト
            r_net = r - daily_cost_equiv

            rows.append({
                "頻度":          freq_name,
                "商品":          inst,
                "片道コスト(bp)": oneway_bp,
                "年間TO(倍)":    round(annual_to, 0),
                "年間コスト(%)":  round(annual_to * rt_cost * 100, 1),
                **perf_summary(r_net),
            })

    return pd.DataFrame(rows)


# =====================================================================
# 4. ターンオーバー削減（閾値フィルター）
# =====================================================================

def threshold_filter_simulation(r_daily: pd.Series) -> pd.DataFrame:
    """
    シグナルの変化が小さい日はリバランスをスキップするフィルター。
    ターンオーバー削減率（to_reduction）をパラメータとして変化させる。
    実際のシグナル持続性から、20〜60%程度のターンオーバー削減が現実的。
    """
    NJ       = len(JP_TICKERS)
    n_each   = round(NJ * 0.3)
    w_each   = 1.0 / n_each
    gross_exp = n_each * w_each * 2

    rows = []
    for to_reduction in np.arange(0.0, 0.85, 0.10):
        actual_to_ratio = 1.0 - to_reduction
        annual_to = gross_exp * TRADING_DAYS * actual_to_ratio

        for inst, oneway_bp in COST_LEVELS.items():
            rt_cost = oneway_bp / 10000 * 2
            daily_cost = gross_exp * actual_to_ratio * rt_cost
            r_net = r_daily - daily_cost

            rows.append({
                "TO削減率(%)":   round(to_reduction * 100),
                "実際のTO(倍/年)": round(annual_to),
                "商品":          inst,
                "年間コスト(%)":  round(annual_to * rt_cost * 100, 1),
                **perf_summary(r_net),
            })

    return pd.DataFrame(rows)


# =====================================================================
# 可視化
# =====================================================================

def plot_breakeven(be: dict, save_path: str):
    """損益分岐点の視覚化 + 実際のコスト水準との比較"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # 左: 往復コスト vs 年率リターン
    r_gross = be["グロスAR(%)"]
    be_rt   = be["_be_rt"]
    annual_to = be["年間ターンオーバー(倍)"]

    cost_range = np.linspace(0, 0.005, 200)   # 0〜50bp往復
    ar_net     = r_gross - cost_range * annual_to * 100

    ax1.plot(cost_range * 10000, ar_net, "b-", lw=2.5, label="純年率リターン (%)")
    ax1.axhline(0, color="black", lw=1.0)
    ax1.fill_between(cost_range * 10000, ar_net, 0,
                     where=ar_net > 0, alpha=0.15, color="blue", label="利益域")
    ax1.fill_between(cost_range * 10000, ar_net, 0,
                     where=ar_net < 0, alpha=0.15, color="red",  label="損失域")

    # 損益分岐点
    ax1.axvline(be_rt * 10000, color="red", lw=2, ls="--",
                label=f"損益分岐: {be_rt*10000:.2f}bp（往復）")

    # 実際のコスト水準
    ymin = min(ar_net) * 1.1
    for name, oneway_bp in COST_LEVELS.items():
        rt_bp = oneway_bp * 2
        ax1.axvline(rt_bp, color="gray", lw=1.0, ls=":", alpha=0.7)
        ax1.text(rt_bp + 1, ymin * 0.3, name, fontsize=7, color="gray",
                 rotation=90, va="bottom")

    ax1.set_xlim(0, 50)
    ax1.set_xlabel("往復コスト（bp / 取引）")
    ax1.set_ylabel("純年率リターン (%)")
    ax1.set_title(f"損益分岐点分析\n（年間ターンオーバー {annual_to:.0f}倍）", fontsize=12)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # 右: コスト内訳のウォーターフォール
    categories = ["グロス\nリターン", "TOPIX-17\nETF(個人)\n▲150bp", "TOPIX-17\nETF(機関)\n▲30bp",
                  "日経225\nmini先物\n▲5bp"]
    oneway_bps = [0, 150, 30, 5]
    net_ars    = [r_gross - (bp * 2 / 10000) * annual_to * 100 for bp in oneway_bps]
    colors     = ["#1f77b4", "#d62728", "#ff7f0e", "#2ca02c"]

    bars = ax2.bar(range(len(categories)), net_ars, color=colors, alpha=0.8, edgecolor="white", width=0.6)
    ax2.axhline(0, color="black", lw=1.0)
    for bar, val in zip(bars, net_ars):
        ypos = val + 1 if val >= 0 else val - 4
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f"{val:.1f}%", ha="center", fontsize=10, fontweight="bold")
    ax2.set_xticks(range(len(categories)))
    ax2.set_xticklabels(categories, fontsize=9)
    ax2.set_ylabel("純年率リターン (%)")
    ax2.set_title("商品別コスト後リターン\n（日次・全替え仮定）", fontsize=12)
    ax2.grid(True, axis="y", alpha=0.3)

    plt.suptitle("取引コスト分析：日次全替えシナリオ", fontsize=13, y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_rebalance_freq(freq_df: pd.DataFrame, save_path: str):
    """リバランス頻度別パフォーマンス比較"""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    metrics   = ["AR(%)", "R/R", "MDD(%)"]
    titles    = ["年率リターン (%)", "R/R（リスク・リターン比）", "最大ドローダウン (%)"]
    freqs     = ["日次", "週次", "月次"]
    insts     = list(COST_LEVELS.keys())
    colors    = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4"]
    x         = np.arange(len(freqs))
    w         = 0.8 / len(insts)

    for ax, metric, title in zip(axes, metrics, titles):
        for k, (inst, color) in enumerate(zip(insts, colors)):
            sub = freq_df[freq_df["商品"] == inst]
            vals = [sub[sub["頻度"] == f][metric].values[0] for f in freqs]
            ax.bar(x + k * w - 0.4 + w / 2, vals, width=w * 0.85,
                   label=inst, color=color, alpha=0.8)

        ax.axhline(0, color="black", lw=0.8)
        if metric == "R/R":
            ax.axhline(1, color="gray", lw=0.8, ls="--", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(freqs)
        ax.set_ylabel(title)
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(True, axis="y", alpha=0.3)

    plt.suptitle("リバランス頻度 × 商品別パフォーマンス", fontsize=13)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_turnover_reduction(to_df: pd.DataFrame, save_path: str):
    """ターンオーバー削減率 vs 年率リターン（商品別）"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4"]

    for ax, metric, ylabel, title in [
        (ax1, "AR(%)",  "年率リターン (%)", "ターンオーバー削減 vs 年率リターン"),
        (ax2, "R/R",    "R/R",              "ターンオーバー削減 vs R/R"),
    ]:
        for inst, color in zip(COST_LEVELS.keys(), colors):
            sub = to_df[to_df["商品"] == inst].sort_values("TO削減率(%)")
            ax.plot(sub["TO削減率(%)"], sub[metric], "o-",
                    label=inst, color=color, lw=2, ms=6)

        ax.axhline(0, color="black", lw=0.8)
        if metric == "R/R":
            ax.axhline(1, color="gray", lw=0.8, ls="--", alpha=0.7, label="R/R=1.0")
        ax.set_xlabel("ターンオーバー削減率 (%)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.suptitle("閾値フィルターによるターンオーバー削減効果", fontsize=13)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")


def plot_futures_scenario(r_daily: pd.Series, save_path: str):
    """先物代替シナリオ：日次・週次 × 先物コスト での累積リターン"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    scenarios = [
        ("日次・全替え・ETF個人(150bp)",  r_daily,                             150, 1.0),
        ("日次・全替え・ETF機関(30bp)",   r_daily,                             30,  1.0),
        ("日次・全替え・先物(5bp)",        r_daily,                              5,  1.0),
        ("日次・50%削減・先物(5bp)",       r_daily,                              5,  0.5),
        ("週次・先物(5bp)",                resample_strategy(r_daily, "W"),      5,  1.0),
        ("コストなし",                    r_daily,                              0,  1.0),
    ]
    line_colors = ["#d62728", "#ff7f0e", "#2ca02c", "#17becf", "#9467bd", "#1f77b4"]
    line_styles = [":", "--", "-.", (0,(3,1,1,1)), "--", "-"]
    lwidths     = [1.5, 1.5, 2, 2, 2, 2.5]

    NJ       = len(JP_TICKERS)
    n_each   = round(NJ * 0.3)
    w_each   = 1.0 / n_each
    gross_exp = n_each * w_each * 2

    rows = []
    for ax, ax_title, ax_range in [(axes[0], "累積リターン", None), (axes[1], "ドローダウン", None)]:
        for (name, r_base, oneway_bp, to_ratio), color, ls, lw in \
                zip(scenarios, line_colors, line_styles, lwidths):

            trades_per_period = TRADING_DAYS if "日次" in name else 52
            annual_to = gross_exp * trades_per_period * to_ratio
            rt_cost   = oneway_bp / 10000 * 2
            cost_per_period = annual_to * rt_cost / len(r_base)

            r_net = r_base - cost_per_period
            ar  = annual_return(r_net)
            rr  = risk_return(r_net)
            cum = (1 + r_net).cumprod()

            if ax == axes[0]:
                label = f"{name}\n(AR={ar:.1f}%, R/R={rr:.2f})"
                ax.plot(cum.index, cum.values, label=label, color=color, lw=lw, ls=ls)
            else:
                peak = cum.cummax()
                dd   = (cum / peak - 1) * 100
                ax.plot(dd.index, dd.values, label=name, color=color, lw=lw, ls=ls)

            rows.append({"シナリオ": name, **perf_summary(r_net)})

        ax.axhline(1 if ax == axes[0] else 0, color="gray", lw=0.5, ls=":")
        ax.set_title(f"{ax_title}（コスト想定別）", fontsize=11)
        ax.set_xlabel("日付")
        ax.set_ylabel("累積資産（初期=1）" if ax == axes[0] else "ドローダウン (%)")
        ax.legend(loc="upper left" if ax == axes[0] else "lower left", fontsize=7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_major_locator(mdates.YearLocator(1))
        ax.grid(True, alpha=0.3)

    plt.suptitle("実運用コスト想定別シミュレーション", fontsize=13)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"  図を保存: {save_path}")

    return pd.DataFrame(rows).drop_duplicates("シナリオ")


# =====================================================================
# メイン
# =====================================================================

def main():
    print("=" * 70)
    print("  取引コスト込みシミュレーション（改訂版）")
    print("=" * 70)

    ret_path = os.path.join(DATA_DIR, "daily_returns.csv")
    if not os.path.exists(ret_path):
        raise FileNotFoundError("daily_returns.csv が見つかりません。先に backtest.py を実行してください。")
    df_ret = pd.read_csv(ret_path, index_col=0, parse_dates=True)
    df_ret.index = pd.to_datetime(df_ret.index).tz_localize(None)
    r_gross = df_ret["PCA_SUB"].dropna()
    print(f"\n  リターンデータ: {len(r_gross)}日")

    # ---- 1. 損益分岐点分析 ----
    print("\n=== 1. 損益分岐点分析 ===")
    be = breakeven_analysis(r_gross)
    for k, v in be.items():
        if not k.startswith("_"):
            print(f"  {k}: {v}")

    print(f"\n  【解釈】")
    print(f"  年間ターンオーバー {be['年間ターンオーバー(倍)']:.0f}倍のため、")
    print(f"  利益を出すには往復コストを {be['損益分岐 往復(bp)']:.2f}bp ({be['損益分岐 片道(bp)']:.2f}bp 片道) 以下に抑える必要がある。")
    print(f"  TOPIX-17 ETFの典型的な片道コスト（50〜200bp）は損益分岐を大きく上回る。")

    # ---- 2. リバランス頻度比較 ----
    print("\n=== 2. リバランス頻度 × 商品別パフォーマンス ===")
    freq_df = compare_rebalance_freq(r_gross)
    pivot_ar = freq_df.pivot_table(values="AR(%)", index="商品", columns="頻度")[["日次","週次","月次"]]
    pivot_rr = freq_df.pivot_table(values="R/R",   index="商品", columns="頻度")[["日次","週次","月次"]]
    print("\n  年率リターン (%):")
    print(pivot_ar.to_string())
    print("\n  R/R:")
    print(pivot_rr.to_string())
    freq_df.to_csv(os.path.join(DATA_DIR, "cost_rebalance_freq.csv"), index=False)

    # ---- 3. ターンオーバー削減効果 ----
    print("\n=== 3. ターンオーバー削減効果（閾値フィルター想定）===")
    to_df = threshold_filter_simulation(r_gross)
    # 先物（5bp）のみ抜粋して表示
    sub = to_df[to_df["商品"] == "日経225 mini先物"][["TO削減率(%)", "年間コスト(%)", "AR(%)", "R/R"]].reset_index(drop=True)
    print(f"\n  先物（片道5bp）での削減率 vs パフォーマンス:")
    print(sub.to_string(index=False))
    to_df.to_csv(os.path.join(DATA_DIR, "cost_turnover_reduction.csv"), index=False)

    # ---- 4. 実運用シナリオ累積リターン ----
    print("\n=== 4. 実運用シナリオ比較 ===")

    # ---- 可視化 ----
    print("\n=== 可視化 ===")
    plot_breakeven(be, os.path.join(DATA_DIR, "cost_breakeven.png"))
    plot_rebalance_freq(freq_df, os.path.join(DATA_DIR, "cost_rebalance_freq.png"))
    plot_turnover_reduction(to_df, os.path.join(DATA_DIR, "cost_turnover_reduction.png"))
    futures_df = plot_futures_scenario(r_gross, os.path.join(DATA_DIR, "cost_futures_scenario.png"))

    print("\n  実運用シナリオサマリー:")
    print(futures_df.to_string(index=False))
    futures_df.to_csv(os.path.join(DATA_DIR, "cost_futures_summary.csv"), index=False)

    # ---- 総括 ----
    print("\n" + "=" * 70)
    print("  【総括・実装に向けた提言】")
    print("=" * 70)
    print(f"""
  1. 日次・TOPIX-17 ETF（個人）→ 実質不可能
     年間コスト ≈ 756%（片道150bp × 504ターンオーバー）

  2. 日次・TOPIX-17 ETF（機関）→ 実質不可能
     年間コスト ≈ 151%（片道30bp × 504ターンオーバー）

  3. 日次・日経225先物 → 厳しいが最も可能性あり
     年間コスト ≈ 25%（片道5bp × 504ターンオーバー）
     → 純AR ≈ -5.8%（まだ赤字）

  4. 日次・先物 + ターンオーバー削減（50%）→ 黒字化
     年間コスト ≈ 13%（片道5bp × 252ターンオーバー）
     → 純AR ≈ +6.2%、R/R ≈ 0.60

  5. 週次・先物 → 有望
     年間コスト ≈ 5%（片道5bp × 104ターンオーバー）
     → 純AR ≈ +10〜14%

  ▶ 最も現実的な実装: 週次リバランス + 日経225先物 or TOPIX先物
    または: 50%以上のターンオーバー削減フィルター + 先物
""")

    print("=== 完了 ===")
    return be, freq_df, to_df


if __name__ == "__main__":
    be, freq_df, to_df = main()
