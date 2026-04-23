"""
投資戦略 監視エージェント (monitor_agent.py)
==========================================
各ログファイルをチェックし、結果をGmailで自分自身に通知する。

【使い方】
  python monitor_agent.py           # 本日のログをチェック＆メール通知
  python monitor_agent.py --dry     # メール送信せず結果だけ表示
  python monitor_agent.py --date 2026-04-13  # 特定日を確認

【タスクスケジューラ登録済みスケジュール】
  09:05  monitor (朝の確認: ログイン・シグナル・寄付き発注)
  15:32  monitor (夕の確認: 引成決済)
"""

import argparse
import re
import base64
import logging
import sys
import io
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from pathlib import Path

# Windows コンソールの文字化け対策
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# =====================================================================
# 設定
# =====================================================================

DIR = Path(__file__).parent

# Gmail API（送受信両方のスコープ）
# ※ kabu_autologin.py と別トークンファイルを使い干渉を避ける
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = DIR / "credentials.json"
TOKEN_FILE       = DIR / "token_monitor.json"

# ログファイル
LOG_AUTOLOGIN = DIR / "log_autologin.txt"
LOG_SIGNAL    = DIR / "log_signal.txt"
LOG_ORDER     = DIR / "log_order.txt"
LOG_FILE      = DIR / "log_monitor.txt"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger()


# =====================================================================
# Gmail API
# =====================================================================

def get_gmail_service():
    """Gmail APIサービスを取得（初回のみブラウザ認証）"""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def get_my_email(service) -> str:
    """自分のGmailアドレスを取得"""
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def send_email(service, to: str, subject: str, body: str):
    """メール送信"""
    message = MIMEText(body, "plain", "utf-8")
    message["to"]      = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info(f"通知送信: {subject} → {to}")


# =====================================================================
# ログパーサー
# =====================================================================

def read_timestamped_lines(log_path: Path, target_date: date) -> list[str]:
    """[YYYY-MM-DD ...] 形式のタイムスタンプ付きログから指定日の行を抽出"""
    if not log_path.exists():
        return []
    date_str = target_date.strftime("%Y-%m-%d")
    lines = []
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if f"[{date_str}" in line:
                lines.append(line.strip())
    return lines


def read_last_session(log_path: Path) -> list[str]:
    """タイムスタンプなしログの最終実行セクション（=== 区切り以降）を返す"""
    if not log_path.exists():
        return []
    with open(log_path, encoding="utf-8", errors="replace") as f:
        all_lines = [l.rstrip() for l in f]

    # 最後の "===" セパレーター以降を「最終セッション」とする
    last_sep = -1
    for i, line in enumerate(all_lines):
        if re.match(r"=+", line):
            last_sep = i
    if last_sep == -1:
        return all_lines  # セパレーターなしなら全行
    return all_lines[last_sep:]


def was_modified_today(log_path: Path, target_date: date) -> bool:
    """ファイルが target_date に更新されたか確認"""
    if not log_path.exists():
        return False
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime).date()
    return mtime == target_date


# =====================================================================
# 各ログの解析
# =====================================================================

def check_autologin(target_date: date) -> dict:
    """
    log_autologin.txt を解析してログイン状況を返す。
    タイムスタンプ付きなので日付フィルタで今日の分だけ見る。
    """
    lines = read_timestamped_lines(LOG_AUTOLOGIN, target_date)
    result = {
        "executed": bool(lines),
        "success":  False,
        "already_logged_in": False,
        "errors":   [],
    }
    for line in lines:
        if "API認証成功" in line:
            result["success"] = True
        if "既にログイン済み" in line:
            result["success"] = True
            result["already_logged_in"] = True
        if any(k in line for k in ["エラー", "失敗", "タイムアウト"]):
            result["errors"].append(line)
    return result


def check_signal(target_date: date) -> dict:
    """
    log_signal.txt（タイムスタンプなし）とCSVファイルの存在で成否を判断。
    """
    lines   = read_last_session(LOG_SIGNAL)
    updated = was_modified_today(LOG_SIGNAL, target_date)

    # 最終セッションからシグナル保存パスを抽出
    saved_file = None
    for line in lines:
        m = re.search(r"シグナルを保存.*?(signal_\d{8}\.csv)", line)
        if m:
            saved_file = m.group(1)

    # CSVファイルの実在確認
    csv_exists = False
    if saved_file and (DIR / saved_file).exists():
        csv_exists = True

    # LONG/SHORT銘柄数
    long_names  = []
    short_names = []
    in_long, in_short = False, False
    for line in lines:
        if "LONG（買い）" in line:
            in_long, in_short = True, False
        elif "SHORT（売り）" in line:
            in_long, in_short = False, True
        elif re.match(r"=+", line):
            in_long = in_short = False
        elif in_long and re.search(r"\d{4}\.T", line):
            m = re.search(r"\d{4}\.T\s+(\S+)", line)
            if m:
                long_names.append(m.group(1))
        elif in_short and re.search(r"\d{4}\.T", line):
            m = re.search(r"\d{4}\.T\s+(\S+)", line)
            if m:
                short_names.append(m.group(1))

    errors = [l for l in lines if "Error" in l or "エラー" in l]

    return {
        "executed": updated,
        "success":  updated and csv_exists,
        "saved_file": saved_file,
        "csv_exists": csv_exists,
        "long_names":  long_names,
        "short_names": short_names,
        "errors": errors,
    }


def check_orders(target_date: date) -> dict:
    """
    log_order.txt（タイムスタンプなし）を解析して発注状況を返す。
    """
    updated = was_modified_today(LOG_ORDER, target_date)
    lines   = read_last_session(LOG_ORDER)

    result = {
        "executed":    updated,
        "dry_run":     True,
        "exec_time":   None,
        "token_ok":    False,
        "order_count": 0,
        "success_count": 0,
        "orders":      [],   # 個別発注行
        "errors":      [],
    }

    for line in lines:
        # 実発注 or DRY RUN
        if "[実発注]" in line:
            result["dry_run"] = False
        if "[DRY RUN]" in line:
            result["dry_run"] = True

        # 実行時刻
        m = re.search(r"実行時刻:\s+(\S+ \S+)", line)
        if m:
            result["exec_time"] = m.group(1)

        # トークン取得成功
        if "トークン取得成功" in line:
            result["token_ok"] = True

        # 個別発注行（銘柄コードで始まる行）
        if re.search(r"\[\d{4}\]", line):
            result["orders"].append(line.strip())
            result["order_count"] += 1
            if "DRY_RUN" in line or "発注成功" in line:
                result["success_count"] += 1

        # エラー
        if any(k in line for k in ["❌", "発注エラー", "トークン取得失敗"]):
            result["errors"].append(line.strip())

    return result


# =====================================================================
# レポート生成
# =====================================================================

def build_report(target_date: date) -> tuple[str, str, bool]:
    """
    全ログを解析してメール件名・本文・要注意フラグを返す。
    """
    now_str  = datetime.now().strftime("%H:%M")
    date_str = target_date.strftime("%Y年%m月%d日")

    al = check_autologin(target_date)
    sg = check_signal(target_date)
    od = check_orders(target_date)

    # 要注意判定
    has_error = (
        (al["executed"] and not al["success"]) or
        (sg["executed"] and not sg["success"]) or
        (od["executed"] and not od["token_ok"]) or
        bool(al["errors"]) or
        bool(sg["errors"]) or
        bool(od["errors"])
    )

    status  = "⚠️ 要確認" if has_error else "✅ 正常"
    subject = f"[投資戦略] {status}  {date_str} {now_str}"

    L = []
    L += [
        f"投資戦略 自動実行レポート",
        f"確認日時: {date_str}  {now_str}",
        "=" * 52,
        "",
    ]

    # ---- 1. ログイン ----
    L.append("【1. kabuステーション 自動ログイン】")
    if not al["executed"]:
        L.append("  － 未実行（ログなし）")
    elif al["success"]:
        tag = "（既にログイン済み）" if al["already_logged_in"] else ""
        L.append(f"  ✅ 成功{tag}")
    else:
        L.append("  ❌ 失敗")
        for e in al["errors"]:
            L.append(f"     {e}")

    # ---- 2. シグナル ----
    L += ["", "【2. シグナル計算】"]
    if not sg["executed"]:
        L.append("  － 未実行（ログなし or 未更新）")
    elif sg["success"]:
        L.append(f"  ✅ 完了  →  {sg['saved_file']}")
        if sg["long_names"]:
            L.append(f"  LONG : {', '.join(sg['long_names'])}")
        if sg["short_names"]:
            L.append(f"  SHORT: {', '.join(sg['short_names'])}")
    else:
        L.append("  ❌ 失敗（CSVが見つかりません）")
        for e in sg["errors"]:
            L.append(f"     {e}")

    # ---- 3. 発注 ----
    L += ["", "【3. 発注】"]
    if not od["executed"]:
        L.append("  － 未実行（ログなし or 未更新）")
    else:
        mode = "DRY RUN（模擬）" if od["dry_run"] else "⚡ 実発注"
        L.append(f"  モード   : {mode}")
        if od["exec_time"]:
            L.append(f"  実行時刻 : {od['exec_time']}")
        L.append(f"  API認証  : {'✅ OK' if od['token_ok'] else '❌ NG'}")
        L.append(f"  発注件数 : {od['order_count']}件  成功 {od['success_count']}件")
        if od["orders"]:
            L.append("  発注内容 :")
            for o in od["orders"][:10]:   # 最大10件
                L.append(f"    {o}")
            if len(od["orders"]) > 10:
                L.append(f"    ...他 {len(od['orders'])-10} 件")
        if od["errors"]:
            L.append("  ❌ エラー:")
            for e in od["errors"]:
                L.append(f"     {e}")

    # ---- フッター ----
    if has_error:
        L += [
            "",
            "=" * 52,
            "⚠️  上記の問題を確認してください。",
            f"ログ場所: {DIR}",
        ]
    else:
        L += ["", "=" * 52, "問題なし。本日の自動取引は正常です。"]

    return subject, "\n".join(L), has_error


# =====================================================================
# メイン
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="投資戦略 監視エージェント")
    parser.add_argument("--date", type=str,       default=None,
                        help="確認日 YYYY-MM-DD（省略時: 本日）")
    parser.add_argument("--dry",  action="store_true",
                        help="メール送信せずコンソールに出力のみ")
    args = parser.parse_args()

    target_date = (
        date.fromisoformat(args.date) if args.date else date.today()
    )

    log.info(f"監視チェック開始: {target_date}")

    subject, body, has_error = build_report(target_date)

    # コンソール出力
    print(subject)
    print()
    print(body)

    if args.dry:
        log.info("--dry モード: メール送信スキップ")
        print("\n[--dry モード: メール送信なし]")
        return

    # Gmail 通知
    try:
        service  = get_gmail_service()
        my_email = get_my_email(service)
        send_email(service, my_email, subject, body)
        print(f"\n📧 通知メール送信: {my_email}")
    except Exception as e:
        log.error(f"メール送信失敗: {e}")
        print(f"\n❌ メール送信失敗: {e}")

    log.info(f"監視チェック完了: {'要確認あり' if has_error else '正常'}")


if __name__ == "__main__":
    main()
