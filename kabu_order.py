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
ORDER_TYPE        = 1    # 1: 成行, 2: 指値
FRONT_ORDER_TYPE  = 10   # 10: 成行（寄付）, 16: 引成（後場）
CASH_MARGIN       = 2    # 1: 現物, 2: 信用新規, 3: 信用返済
MARGIN_TRADE_TYPE       = 3    # 1: 制度信用, 2: 一般信用（長期）, 3: 一般信用（デイトレ）
MARGIN_TRADE_TYPE_SHORT = 1    # SHORTはデイトレ在庫が枯渇しやすいため制度信用を使用
SIDE_BUY          = "2"  # 買い
SIDE_SELL         = "1"  # 売り

# TOPIX-17 ETF 銘柄コード（証券コード）
JP_TICKER_TO_CODE = {
    "1617.T": "1617", "1618.T": "1618", "1619.T": "1619",
    "1620.T": "1620", "1621.T": "1621", "1622.T": "1622",
    "1623.T": "1623", "1624.T": "1624",
    "1626.T": "1626", "1627.T": "1627", "1628.T": "1628",
    "1629.T": "8058",   # 商社・卸売 → 三菱商事（デイトレ売建対応）
    "1630.T": "1630", "1631.T": "1631",
    "1632.T": "1632",
    "1633.T": "1343",   # 不動産 → NEXT FUNDS 東証REIT指数ETF（デイトレ売建対応）
}

# 一般信用デイトレ売建非対応のためSHORTをスキップする銘柄
SHORT_SKIP_TICKERS = {"1617.T", "1620.T", "1623.T", "1629.T"}  # 1629.T→8058(三菱商事)は売建規制対象

# 非ETF代替銘柄の単元株数（ETF=1口単位のため1でない銘柄のみ記載）
LOT_SIZE = {
    "8058": 100,   # 三菱商事（単元株100株）
    "1343": 10,    # NEXT FUNDS 東証REIT指数ETF（売買単位10口）
}

JP_NAMES = {
    "1617.T": "食品",           "1618.T": "エネルギー資源",
    "1619.T": "建設・資材",     "1620.T": "素材・化学",
    "1621.T": "医薬品",         "1622.T": "自動車・輸送機",
    "1623.T": "鉄鋼・非鉄",    "1624.T": "機械",
    "1626.T": "情報通信・サービス",
    "1627.T": "電力・ガス",     "1628.T": "運輸・物流",
    "1629.T": "商社・卸売",     "1630.T": "小売",
    "1631.T": "銀行",           "1632.T": "金融（除く銀行）",
    "1633.T": "不動産",
    # 代替銘柄の表示名（発注コードで参照される）
    "1343.T": "不動産代替（東証REIT）",
    "8058.T": "商社・卸売代替（三菱商事）",
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
    margin_trade_type: int = MARGIN_TRADE_TYPE,
    front_order_type: int = FRONT_ORDER_TYPE,
    close_position_order: Optional[int] = None,
    dry_run: bool = True,
) -> Optional[dict]:
    """
    注文発注
    symbol              : 証券コード（例: "1617"）
    side                : "2"=買い, "1"=売り
    qty                 : 株数（口数）
    order_type          : 1=成行, 2=指値
    price               : 指値価格（成行の場合は0）
    cash_margin         : 1=現物, 2=信用新規, 3=信用返済
    margin_trade_type   : 1=制度信用, 2=一般信用（長期）, 3=一般信用（デイトレ）
    front_order_type    : 10=成行寄付, 13=成行引成, 20=指値
    close_position_order: 返済順序（返済時のみ: 0〜7）
    dry_run             : True=発注せず内容確認のみ
    """
    direction = "買い" if side == SIDE_BUY else "売り（空売り）"
    print(f"    [{symbol}] {JP_NAMES.get(symbol+'.T', symbol)} "
          f"{direction} {qty}口 ({'成行' if order_type==1 else f'指値{price}円'})"
          f" {'[DRY RUN]' if dry_run else '[実発注]'}")

    if dry_run:
        return {"OrderId": "DRY_RUN", "Result": 0}

    headers = {"X-API-KEY": token, "Content-Type": "application/json"}
    deliv_type = 0 if cash_margin == 2 else 2  # 信用新規=0、信用返済=2
    body = {
        "Password":          API_PASSWORD,
        "Symbol":            symbol,
        "Exchange":          27,         # 東証+（通常時の新規発注は東証1不可）
        "SecurityType":      1,          # 株式・ETF
        "Side":              side,
        "CashMargin":        cash_margin,
        "MarginTradeType":   margin_trade_type,
        "DelivType":         deliv_type,
        "AccountType":       4,          # 特定口座
        "Qty":               qty,
        "FrontOrderType":    front_order_type,
        "Price":             price,
        "ExpireDay":         0,
    }
    if close_position_order is not None:
        body["ClosePositionOrder"] = close_position_order

    resp = requests.post(
        f"{KABU_API_BASE}/sendorder",
        headers=headers,
        json=body,
        timeout=10
    )

    if resp.status_code != 200:
        print(f"    ❌ 発注エラー: {resp.status_code} {resp.text}")
        code = None
        try:
            code = resp.json().get("Code")
        except Exception:
            pass
        # None ではなくエラー内容を含む dict を返す（Code:10016等の検知・リトライ用）
        return {"Result": -1, "Code": code, "Message": resp.text, "_status": resp.status_code}

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
    単元株単位に切り下げ（ETF=1口、個別株=LOT_SIZE参照）
    板情報取得失敗時は0を返してスキップ
    """
    code = JP_TICKER_TO_CODE.get(ticker)
    if not code:
        return 0

    try:
        board = get_board(token, code)
        price = board.get("CurrentPrice") or board.get("CalcPrice")
        if not price:
            return 0
    except Exception:
        return 0   # 板情報取得失敗（トークン期限切れ等）はスキップ

    lot = LOT_SIZE.get(code, 1)
    target_value = portfolio_value * abs(weight)
    qty = int(target_value / price / lot) * lot
    return qty


# =====================================================================
# 5.5 リカバリ・通知ヘルパー（取引セッション失効対策）
# =====================================================================

def _is_session_expired(result) -> bool:
    """注文結果が「取引ログインセッション失効」(Code:10016)かを判定"""
    return isinstance(result, dict) and result.get("Code") == 10016


def _is_order_failed(result) -> bool:
    """注文結果が失敗（成功=Result:0 以外）かを判定"""
    return not (isinstance(result, dict) and result.get("Result") == 0)


def _force_relogin() -> bool:
    """kabu_autologin を呼び出して kabuステーションへ強制再ログインする。
    GUI依存のため遅延importする（失敗しても発注フローは継続）。"""
    try:
        import kabu_autologin
        print("  🔄 kabuステーションへ強制再ログイン中（最大2〜3分）...")
        ok = kabu_autologin.do_login(force=True)
        print(f"  {'✅ 再ログイン成功' if ok else '❌ 再ログイン失敗'}")
        return ok
    except Exception as e:
        print(f"  ❌ 再ログイン呼び出し失敗: {e}")
        return False


def _send_gmail(subject: str, body: str) -> None:
    """monitor_agent と同じ token_monitor.json を使って自分宛にメール送信する。"""
    try:
        import base64
        from email.mime.text import MIMEText
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = os.path.join(DATA_DIR, "token_monitor.json")
        scopes = ["https://www.googleapis.com/auth/gmail.readonly",
                  "https://www.googleapis.com/auth/gmail.send"]
        if not os.path.exists(token_file):
            print("  ⚠️  token_monitor.json が無いためアラート送信をスキップ")
            return
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        if (not creds.valid) and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        service = build("gmail", "v1", credentials=creds)
        me = service.users().getProfile(userId="me").execute()["emailAddress"]
        msg = MIMEText(body, "plain", "utf-8")
        msg["to"] = me
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"  📧 アラート送信: {subject} → {me}")
    except Exception as e:
        print(f"  ⚠️  アラート送信失敗: {e}")


def _send_failure_alert(failed_results: list, open_order: bool) -> None:
    """実発注で失敗が残った注文を即時メール通知する（当日中の手動対応用）。"""
    phase = "寄付き発注" if open_order else "引成決済"
    lines = [
        f"{phase}で {len(failed_results)}件の発注失敗が発生しました（実発注モード）。",
        f"時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "失敗した注文:",
    ]
    for r in failed_results:
        res = r.get("Result")
        code = res.get("Code") if isinstance(res, dict) else None
        msg = res.get("Message") if isinstance(res, dict) else res
        lines.append(f"  [{r['Ticker']}] {r['Side']} {r['Qty']}口  Code={code}  {str(msg)[:120]}")
    if not open_order:
        lines += [
            "",
            "⚠️ 決済失敗のため建玉が持ち越される可能性があります。",
            "制度信用SHORTは自動決済されません。kabuステーション建玉画面で手動返済してください。",
            "（確認コマンド: python -X utf8 check_positions.py）",
        ]
    subject = f"[投資戦略] ⚠️ {phase}失敗 {len(failed_results)}件 要手動対応"
    _send_gmail(subject, "\n".join(lines))


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

    # ---- トークン取得 ----
    print("\n【1. 認証】")
    try:
        token = get_token()
    except Exception as e:
        print(f"  ❌ トークン取得失敗: {e}")
        return

    # ---- 残高確認（401時はトークン再取得して再試行） ----
    print("\n【2. 残高確認】")
    try:
        wallet = get_wallet(token)
        fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
        print(f"  現物買付余力: {fmt(wallet.get('StockAccountWallet', 'N/A'))}円")
        print(f"  信用新規余力: {fmt(wallet.get('MarginAccountWallet', 'N/A'))}円")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            print("  ⚠️  トークン期限切れを検出 → 再認証します")
            try:
                token = get_token(force_refresh=True)
                wallet = get_wallet(token)
                fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
                print(f"  現物買付余力: {fmt(wallet.get('StockAccountWallet', 'N/A'))}円")
                print(f"  信用新規余力: {fmt(wallet.get('MarginAccountWallet', 'N/A'))}円")
            except Exception as e2:
                print(f"  ⚠️  残高取得エラー（続行します）: {e2}")
        else:
            print(f"  ⚠️  残高取得エラー（続行します）: {e}")
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

    # ---- 実保有建玉の取得（決済時のみ）----
    # {(証券コード, Side): 残数量} Side="2"=買建, "1"=売建
    held_qty: dict = {}
    if not open_order:
        print("\n【3.5. 実保有建玉確認】")
        try:
            df_pos = get_positions(token)
            if not df_pos.empty:
                for _, pos in df_pos.iterrows():
                    sym  = str(pos.get("Symbol", ""))
                    side = str(pos.get("Side", ""))
                    qty  = int(pos.get("LeavesQty", 0))
                    if sym and qty > 0:
                        held_qty[(sym, side)] = held_qty.get((sym, side), 0) + qty
            if held_qty:
                for (sym, side), qty in held_qty.items():
                    side_str = "買建" if side == SIDE_BUY else "売建"
                    print(f"  [{sym}] {side_str} {qty}口")
            else:
                print("  保有建玉なし")
        except Exception as e:
            print(f"  ⚠️  建玉取得エラー（シグナルベースで決済します）: {e}")

    # ---- 発注内容の確認 ----
    front_type = 10 if open_order else 16   # 10=成行寄付, 16=引成（後場）
    order_label = "寄付き成行" if open_order else "引成成行"
    print(f"\n【4. 発注内容（{order_label}）】")

    if open_order:
        long_label   = "LONG（信用新規買い）"
        long_side    = SIDE_BUY
        long_cm      = 2
        long_cpord   = None
        short_label  = "SHORT（信用新規売り）"
        short_side   = SIDE_SELL
        short_cm     = 2
        short_cpord  = None
    else:
        long_label   = "LONG返済（信用返済売り）"
        long_side    = SIDE_SELL   # 買建玉の返済 = 売り
        long_cm      = 3
        long_cpord   = 0
        short_label  = "SHORT返済（信用返済買い）"
        short_side   = SIDE_BUY   # 売建玉の返済 = 買い
        short_cm     = 3
        short_cpord  = 0

    order_results = []

    # ロング
    print(f"\n  ▼ {long_label}")
    for _, row in longs.iterrows():
        ticker = row["Ticker"]
        code   = JP_TICKER_TO_CODE.get(ticker, "")
        if not code:
            continue
        if not open_order:
            # 決済時：実保有の買建玉数量を使用
            qty = held_qty.get((code, SIDE_BUY), 0)
            if qty == 0:
                print(f"    [{code}] {JP_NAMES.get(ticker, ticker)} スキップ（買建玉なし）")
                continue
        else:
            qty = calc_order_qty(ticker, row["ポジション"], portfolio_value, token)
            if qty == 0:
                continue
        spec = dict(
            symbol=code, side=long_side, qty=qty,
            cash_margin=long_cm,
            front_order_type=front_type,
            close_position_order=long_cpord,
        )
        result = send_order(token, dry_run=dry_run, **spec)
        order_results.append({
            "Ticker": ticker, "Side": "BUY" if long_side == SIDE_BUY else "SELL",
            "Qty": qty, "Result": result, "spec": spec,
        })
        time.sleep(0.5)

    # ショート
    print(f"\n  ▼ {short_label}")
    for _, row in shorts.iterrows():
        ticker = row["Ticker"]
        if ticker in SHORT_SKIP_TICKERS:
            print(f"    [{ticker}] {JP_NAMES.get(ticker, ticker)} SHORT スキップ（デイトレ売建非対応）")
            continue
        code   = JP_TICKER_TO_CODE.get(ticker, "")
        if not code:
            continue
        if not open_order:
            # 決済時：実保有の売建玉数量を使用
            qty = held_qty.get((code, SIDE_SELL), 0)
            if qty == 0:
                print(f"    [{code}] {JP_NAMES.get(ticker, ticker)} スキップ（売建玉なし）")
                continue
        else:
            qty = calc_order_qty(ticker, abs(row["ポジション"]), portfolio_value, token)
            if qty == 0:
                continue
        # SHORT新規・返済ともに制度信用（開建玉と同じ MarginTradeType で返済）
        short_mtt = MARGIN_TRADE_TYPE_SHORT
        spec = dict(
            symbol=code, side=short_side, qty=qty,
            cash_margin=short_cm,
            margin_trade_type=short_mtt,
            front_order_type=front_type,
            close_position_order=short_cpord,
        )
        result = send_order(token, dry_run=dry_run, **spec)
        order_results.append({
            "Ticker": ticker, "Side": "BUY" if short_side == SIDE_BUY else "SELL",
            "Qty": qty, "Result": result, "spec": spec,
        })
        time.sleep(0.5)

    # ---- 決済時：取引セッション失効(Code:10016)を検知したら再ログインしてリトライ ----
    if not open_order and not dry_run:
        expired = [r for r in order_results if _is_session_expired(r["Result"])]
        if expired:
            print(f"\n  ⚠️  取引ログインセッション失効(Code:10016)を {len(expired)}件 検出 → リカバリ開始")
            if _force_relogin():
                try:
                    token = get_token(force_refresh=True)
                except Exception as e:
                    print(f"  ⚠️  トークン再取得失敗: {e}")
                print("  🔁 未決済分を再発注します")
                for r in expired:
                    spec = r.get("spec")
                    if not spec:
                        continue
                    new_res = send_order(token, dry_run=False, **spec)
                    r["Result"] = new_res
                    time.sleep(0.5)
            else:
                print("  ❌ 再ログイン失敗 → 自動リカバリ不可。手動返済が必要です。")

    # ---- サマリー ----
    print(f"\n【5. 発注サマリー】")
    print(f"  発注数: {len(order_results)}件")
    if dry_run:
        print("  ⚠️  DRY RUN モード: 実際の発注は行われていません")
        print("  実発注するには --execute オプションを付けて実行してください")
    else:
        success = sum(1 for r in order_results
                      if isinstance(r["Result"], dict) and r["Result"].get("Result") == 0)
        print(f"  成功: {success}件 / 失敗: {len(order_results)-success}件")

        # ---- 失敗が残る場合は即時アラート（当日中の手動対応用）----
        failed = [r for r in order_results if _is_order_failed(r["Result"])]
        if failed:
            _send_failure_alert(failed, open_order)

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

    # kabuステーション起動確認
    print("\n【接続確認】")
    try:
        resp = requests.get(f"{KABU_API_BASE}/token", timeout=3)
        print(f"  ✅ kabuステーションAPI に接続できました（ポート18080）")
    except requests.exceptions.ConnectionError:
        print("  ❌ 接続失敗: kabuステーション® が起動していません")
        print("     → kabuステーション®（Windows版）を起動し、")
        print("       システム設定 > APIタブ でAPIを有効化してください")
        print()
        print("  ⚠️  注意: kabuステーションAPIはWindowsのみ対応です")
        print("     Macの場合は以下の代替手段をご検討ください:")
        print("     1. Windows PCまたは仮想環境（Parallels等）で実行")
        print("     2. Windows VPS（クラウド上のWindows Server）で実行")
        return False

    # トークン取得テスト
    print("\n【認証テスト】")
    if not API_PASSWORD:
        print("  ⚠️  APIパスワード未設定")
        print("     export KABU_API_PASSWORD='your_password' を実行してください")
        return False

    try:
        token = get_token()
        print(f"  ✅ 認証成功")
    except Exception as e:
        print(f"  ❌ 認証失敗: {e}")
        return False

    # 残高照会テスト
    print("\n【残高照会テスト】")
    try:
        wallet = get_wallet(token)
        fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
        print(f"  ✅ 残高照会成功")
        print(f"     現物買付余力: {fmt(wallet.get('StockAccountWallet', 'N/A'))}円")
        print(f"     信用新規余力: {fmt(wallet.get('MarginAccountWallet', 'N/A'))}円")
    except Exception as e:
        print(f"  ❌ 残高照会失敗: {e}")

    # 板情報テスト（1617.T）
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
