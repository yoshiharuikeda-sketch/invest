"""
report_agent.py - Daily P&L save + weekly/monthly report via Gmail

Usage:
  python report_agent.py              # save today, auto-detect weekly/monthly
  python report_agent.py --weekly     # force weekly report
  python report_agent.py --monthly    # force monthly report
  python report_agent.py --dry        # skip email, print summary only
"""

import argparse
import base64
import csv
import glob
import io
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────

DIR              = Path(__file__).parent
PNL_HISTORY_CSV  = DIR / "pnl_history.csv"
PNL_DETAIL_CSV   = DIR / "pnl_detail_history.csv"
LOG_FILE         = DIR / "log_report.txt"
TOKEN_FILE       = DIR / "token_monitor.json"
CREDENTIALS_FILE = DIR / "credentials.json"
SCOPES           = ["https://www.googleapis.com/auth/gmail.send"]
RECIPIENT        = "yoshiharu.ikeda@gmail.com"

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger()


# ─────────────────────────────────────────────
# Gmail
# ─────────────────────────────────────────────

def _get_gmail_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(f"Gmail token invalid: {TOKEN_FILE}")
    return build("gmail", "v1", credentials=creds)


def _send_email(service, subject: str, html: str, png_bytes: bytes | None = None):
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["To"]      = RECIPIENT

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    if png_bytes:
        img = MIMEImage(png_bytes, "png")
        img.add_header("Content-ID", "<chart>")
        img.add_header("Content-Disposition", "inline", filename="chart.png")
        msg.attach(img)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info(f"Gmail sent: {subject}")


# ─────────────────────────────────────────────
# P&L 計算
# ─────────────────────────────────────────────

def _find_latest_unrecorded() -> tuple[Path | None, datetime | None]:
    """pnl_history.csv に未記録の最新シグナルファイルを探す"""
    recorded = set()
    if PNL_HISTORY_CSV.exists():
        df = pd.read_csv(PNL_HISTORY_CSV, encoding="utf-8-sig")
        recorded = set(df["日付"].tolist())

    for path in sorted(DIR.glob("signal_????????.csv"), reverse=True):
        m = re.search(r"signal_(\d{8})\.csv", path.name)
        if not m:
            continue
        d = m.group(1)
        date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if date_fmt not in recorded:
            return path, datetime.strptime(d, "%Y%m%d")
    return None, None


def calc_and_save_today() -> dict | None:
    """最新の未記録シグナルからP&Lを計算して保存する"""
    sys.path.insert(0, str(DIR))
    from calc_pnl import (
        load_signal, fetch_ohlc, calc_day_pnl, load_fills,
        ORDER_TICKER_MAP, SHORT_SKIP_TICKERS, PORTFOLIO_VALUE,
    )

    csv_path, date = _find_latest_unrecorded()
    if csv_path is None:
        log.info("未記録シグナルなし（本日分は保存済みか休場）")
        return None

    signal_df = load_signal(str(csv_path))
    if signal_df.empty:
        log.info(f"{date.strftime('%Y-%m-%d')}: ポジションなし")
        return None

    skip = signal_df["Ticker"].isin(SHORT_SKIP_TICKERS) & (signal_df["ポジション"] < 0)
    signal_df = signal_df[~skip].copy()
    signal_df["Ticker"] = signal_df["Ticker"].map(
        lambda t: ORDER_TICKER_MAP.get(t, t)
    )

    import pandas as pd
    japan_date = pd.Timestamp(date) + pd.offsets.BDay(1)
    fills, fills_available = load_fills(japan_date)

    ohlc = fetch_ohlc(signal_df["Ticker"].tolist(), date)
    if ohlc.empty and not fills_available:
        log.warning(f"{date.strftime('%Y-%m-%d')}: 価格データ取得失敗")
        return None

    detail_df = calc_day_pnl(signal_df, ohlc, PORTFOLIO_VALUE,
                              fills=fills, fills_available=fills_available)
    total_pnl = float(detail_df["損益(円)"].sum(skipna=True))
    date_str  = date.strftime("%Y-%m-%d")

    summary = {
        "日付":       date_str,
        "合計損益(円)": round(total_pnl),
        "損益率(%)":  round(total_pnl / PORTFOLIO_VALUE * 100, 3),
        "勝敗":       "W" if total_pnl >= 0 else "L",
        "ポジション数": len(detail_df),
    }

    # ─ pnl_history.csv 保存 ─
    history = []
    if PNL_HISTORY_CSV.exists():
        with open(PNL_HISTORY_CSV, encoding="utf-8-sig") as f:
            history = [r for r in csv.DictReader(f) if r["日付"] != date_str]
    history.append(summary)
    history.sort(key=lambda r: r["日付"])
    _write_csv(PNL_HISTORY_CSV,
               ["日付", "合計損益(円)", "損益率(%)", "勝敗", "ポジション数"],
               history)

    # ─ pnl_detail_history.csv 保存 ─
    existing = pd.DataFrame()
    if PNL_DETAIL_CSV.exists():
        existing = pd.read_csv(PNL_DETAIL_CSV, encoding="utf-8-sig")
        existing = existing[existing["日付"] != date_str]
    detail_df = detail_df.copy()
    detail_df.insert(0, "日付", date_str)
    updated = pd.concat([existing, detail_df], ignore_index=True)
    updated.sort_values("日付", inplace=True)
    updated.to_csv(PNL_DETAIL_CSV, index=False, encoding="utf-8-sig")

    log.info(f"P&L保存: {date_str}  {total_pnl:+,.0f}円 ({summary['損益率(%)']}%)")
    return summary


def _write_csv(path: Path, fieldnames: list, rows: list):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ─────────────────────────────────────────────
# 履歴読み込み
# ─────────────────────────────────────────────

def _load_history(start: str, end: str) -> pd.DataFrame:
    if not PNL_HISTORY_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(PNL_HISTORY_CSV, encoding="utf-8-sig")
    return df[(df["日付"] >= start) & (df["日付"] <= end)].copy()


def _load_detail(start: str, end: str) -> pd.DataFrame:
    if not PNL_DETAIL_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(PNL_DETAIL_CSV, encoding="utf-8-sig")
    return df[(df["日付"] >= start) & (df["日付"] <= end)].copy()


# ─────────────────────────────────────────────
# チャート生成
# ─────────────────────────────────────────────

def _generate_chart(df: pd.DataFrame, title: str) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import platform
    if platform.system() == "Windows":
        plt.rcParams["font.family"] = "MS Gothic"

    df = df.copy()
    df["日付_dt"]    = pd.to_datetime(df["日付"])
    df["合計損益(円)"] = df["合計損益(円)"].astype(float)
    df["累積損益(円)"] = df["合計損益(円)"].cumsum()

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.suptitle(title, fontsize=13, fontweight="bold")

    # 上段: 累積損益ライン
    c = df["累積損益(円)"]
    ax1.plot(df["日付_dt"], c, color="#2196F3", linewidth=2, marker="o", markersize=4)
    ax1.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax1.fill_between(df["日付_dt"], c, 0, where=c >= 0, alpha=0.15, color="#4CAF50")
    ax1.fill_between(df["日付_dt"], c, 0, where=c < 0,  alpha=0.15, color="#F44336")
    ax1.set_ylabel("累積損益（円）")
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:+,.0f}")
    )
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax1.grid(True, alpha=0.3)

    # 下段: 日次損益バー
    colors = ["#4CAF50" if v >= 0 else "#F44336" for v in df["合計損益(円)"]]
    ax2.bar(df["日付_dt"], df["合計損益(円)"], color=colors, alpha=0.8)
    ax2.axhline(0, color="gray", linewidth=0.8)
    ax2.set_ylabel("日次損益（円）")
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:+,.0f}")
    )
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax2.grid(True, alpha=0.3, axis="y")

    fig.autofmt_xdate()
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


# ─────────────────────────────────────────────
# HTML レポート生成
# ─────────────────────────────────────────────

def _th(t):
    return f'<th style="background:#1565C0;color:#fff;padding:6px 10px">{t}</th>'

def _td(t, align="center", color=""):
    s = f"padding:5px 10px;border-bottom:1px solid #ddd;text-align:{align}"
    if color:
        s += f";color:{color}"
    return f'<td style="{s}">{t}</td>'

def _color(v):
    return "#4CAF50" if float(v) >= 0 else "#F44336"


def build_report_html(label: str, df_hist: pd.DataFrame,
                      df_detail: pd.DataFrame) -> str:
    df = df_hist.copy()
    df["合計損益(円)"] = df["合計損益(円)"].astype(float)
    df["損益率(%)"]   = df["損益率(%)"].astype(float)

    total   = df["合計損益(円)"].sum()
    avg     = df["合計損益(円)"].mean()
    wins    = int((df["合計損益(円)"] > 0).sum())
    losses  = int((df["合計損益(円)"] <= 0).sum())
    wr      = wins / len(df) * 100 if len(df) else 0
    cum     = df["合計損益(円)"].cumsum()
    dd      = float((cum - cum.cummax()).min())

    tbl = 'style="border-collapse:collapse;width:100%;font-size:13px"'

    # サマリー
    summary_html = f"""
<table {tbl}>
  <tr>{_th("期間合計損益")}{_th("勝率")}{_th("平均日次損益")}{_th("最大DD")}{_th("取引日数")}</tr>
  <tr>
    {_td(f"<b>{total:+,.0f}円</b>", color=_color(total))}
    {_td(f"{wins}勝{losses}敗 ({wr:.0f}%)")}
    {_td(f"{avg:+,.0f}円", color=_color(avg))}
    {_td(f"{dd:,.0f}円", color="#F44336")}
    {_td(f"{len(df)}日")}
  </tr>
</table>"""

    # 日次損益
    rows = ""
    for _, r in df.iterrows():
        pnl  = float(r['合計損益(円)'])
        rate = float(r['損益率(%)'])
        rows += (
            f"<tr>{_td(r['日付'])}"
            f"{_td(f'{pnl:+,.0f}円', color=_color(pnl))}"
            f"{_td(f'{rate:+.3f}%', color=_color(rate))}"
            f"{_td(r['勝敗'])}"
            f"{_td(r['ポジション数'])}</tr>"
        )
    daily_html = f"""
<table {tbl}>
  <tr>{_th("日付")}{_th("損益(円)")}{_th("損益率(%)")}{_th("勝敗")}{_th("ポジション数")}</tr>
  {rows}
</table>"""

    # 銘柄別損益
    sector_html = ""
    if not df_detail.empty and "損益(円)" in df_detail.columns:
        sector = (
            df_detail.groupby("名称")["損益(円)"]
            .sum().sort_values().reset_index()
        )
        s_rows = ""
        for _, r in sector.iterrows():
            pnl = float(r['損益(円)'])
            s_rows += (
                f"<tr>{_td(r['名称'], align='left')}"
                f"{_td(f'{pnl:+,.0f}円', color=_color(pnl))}</tr>"
            )
        sector_html = f"""
<h3>銘柄別損益</h3>
<table {tbl}>
  <tr>{_th("銘柄名")}{_th("損益(円)")}</tr>
  {s_rows}
</table>"""

    return f"""<html><body style="font-family:sans-serif;max-width:820px;margin:auto;padding:20px">
<h2 style="color:#1565C0">{label}</h2>
<h3>サマリー</h3>{summary_html}
<h3>累積損益チャート</h3>
<img src="cid:chart" style="max-width:100%">
<h3>日次損益一覧</h3>{daily_html}
{sector_html}
<p style="color:gray;font-size:11px;margin-top:20px">自動送信 — 日米業種リードラグ投資戦略</p>
</body></html>"""


# ─────────────────────────────────────────────
# 週末・月末判定
# ─────────────────────────────────────────────

def _is_friday(dt: datetime) -> bool:
    return dt.weekday() == 4


def _is_last_trading_day_of_month(dt: datetime) -> bool:
    nxt = dt + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt.month != dt.month


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly",  action="store_true")
    parser.add_argument("--monthly", action="store_true")
    parser.add_argument("--dry",     action="store_true")
    args = parser.parse_args()

    jst   = timezone(timedelta(hours=9))
    today = datetime.now(jst).replace(tzinfo=None)
    today_str = today.strftime("%Y-%m-%d")
    log.info(f"=== report_agent 開始: {today_str} ===")

    # ── 日次P&L保存 ──
    summary = calc_and_save_today()
    if summary:
        print(f"[P&L] {summary['日付']}  {summary['合計損益(円)']:+,}円"
              f"  ({summary['損益率(%)']}%)  {summary['勝敗']}")

    do_weekly  = args.weekly  or _is_friday(today)
    do_monthly = args.monthly or _is_last_trading_day_of_month(today)

    if not do_weekly and not do_monthly:
        log.info("週次・月次レポート対象日ではありません")
        return

    service = None
    if not args.dry:
        try:
            service = _get_gmail_service()
        except Exception as e:
            log.error(f"Gmail初期化失敗: {e}")
            return

    def _send_report(label: str, subject: str, start: str, end: str):
        df_hist   = _load_history(start, end)
        df_detail = _load_detail(start, end)
        if df_hist.empty:
            log.warning(f"{label}: 対象データなし")
            return
        html  = build_report_html(label, df_hist, df_detail)
        chart = _generate_chart(df_hist, label)
        total = df_hist["合計損益(円)"].astype(float).sum()
        print(f"[{label}] 合計: {total:+,.0f}円  ({len(df_hist)}日)")
        if args.dry:
            log.info(f"[DRY] {subject} — {total:+,.0f}円")
            return
        _send_email(service, subject, html, chart)

    # ── 週次レポート ──
    if do_weekly:
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        _send_report(
            label   = f"週次レポート {week_start} 〜 {today_str}",
            subject = f"【週次】投資レポート {today_str}",
            start   = week_start,
            end     = today_str,
        )

    # ── 月次レポート ──
    if do_monthly:
        month_start = today.strftime("%Y-%m-01")
        _send_report(
            label   = f"月次レポート {today.strftime('%Y年%m月')}",
            subject = f"【月次】投資レポート {today.strftime('%Y-%m')}",
            start   = month_start,
            end     = today_str,
        )

    log.info("report_agent 完了")


if __name__ == "__main__":
    main()
