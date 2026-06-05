# -*- coding: utf-8 -*-
"""残っている信用建玉を「実保有のSide基準」で返済する単発スクリプト。

金曜の決済失敗（Code:10016）で持ち越した制度信用SHRT等を、月曜寄付きで
自動返済するために使う。シグナルのバケット振り分けを使わず、実際の建玉の
Side / MarginTradeType から返済方向を決めるため、シグナル反転銘柄の
取りこぼし（木曜型 Code:1009001）も起きない。

【安全策】当日新規の建玉を誤決済しないため、既定では ExecutionDay（約定日）が
本日より前の建玉のみを返済対象にする。ExecutionDay が取得できない場合は
寄付き前（08時台）のみ実行を許可する。--force で両ガードを無効化（手動緊急用）。

  python -X utf8 close_all_positions.py            # DRY RUN（発注しない）
  python -X utf8 close_all_positions.py --execute  # 実返済（前日以前の建玉のみ）
  python -X utf8 close_all_positions.py --execute --force  # 全建玉を即返済（手動緊急）
"""

import argparse
import io
import sys
import time
from datetime import datetime

# Windows コンソールの文字化け対策
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import kabu_order as ko

# 返済発注の注文種別: 10=成行（寄付） 寄付き前に出すと寄成として板に乗る
FRONT_ORDER_TYPE_MOO = 10


def _to_int(v) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser(description="残建玉の全返済（実保有Side基準）")
    ap.add_argument("--execute", action="store_true", help="実際に返済発注する（既定はDRY RUN）")
    ap.add_argument("--force", action="store_true",
                    help="ExecutionDay/寄付き前ガードを無効化し全建玉を即返済（手動緊急用）")
    args = ap.parse_args()
    dry = not args.execute

    print("=" * 65)
    print(f"  残建玉 全返済 {'(DRY RUN)' if dry else '(実返済)'}{' [FORCE]' if args.force else ''}")
    print(f"  実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # ---- トークン取得（401時は再取得）----
    token = None
    try:
        token = ko.get_token()
    except Exception:
        pass
    if not token:
        try:
            token = ko.get_token(force_refresh=True)
        except Exception as e:
            print(f"  ❌ トークン取得失敗: {e}")
            if not dry:
                ko._send_gmail("[投資戦略] ⚠️ 残建玉返済 トークン取得失敗",
                               f"kabuステーション未起動/未ログインの可能性。\n{e}\n手動で確認してください。")
            return

    # ---- 建玉取得 ----
    try:
        df = ko.get_positions(token)
    except Exception as e:
        print(f"  ❌ 建玉照会失敗: {e}")
        if not dry:
            ko._send_gmail("[投資戦略] ⚠️ 残建玉返済 建玉照会失敗", str(e))
        return

    if df.empty or "LeavesQty" not in df.columns:
        print("  建玉なし。返済不要。")
        return
    df = df[df["LeavesQty"].apply(lambda v: _to_int(v) > 0)].copy()
    if df.empty:
        print("  残建玉なし。返済不要。")
        return

    # ---- 当日新規の混入を防ぐフィルタ ----
    today_int = _to_int(datetime.now().strftime("%Y%m%d"))
    if not args.force:
        if "ExecutionDay" in df.columns:
            before = len(df)
            df = df[df["ExecutionDay"].apply(lambda v: 0 < _to_int(v) < today_int)].copy()
            print(f"  ExecutionDayフィルタ: 前日以前の建玉 {len(df)}件（全{before}件中、当日新規は除外）")
        else:
            # ExecutionDay が取れない → 寄付き前（08時台）のみ許可
            if datetime.now().hour != 8:
                print("  ⚠️ ExecutionDay不明 かつ 寄付き前(08時台)でないため中止（当日新規の誤決済防止）。")
                if not dry:
                    ko._send_gmail("[投資戦略] ⚠️ 残建玉返済 中止",
                                   "ExecutionDay不明かつ寄付き前でないため安全のため中止。手動返済してください。\n"
                                   "（確認: python -X utf8 check_positions.py）")
                return
            print("  ⚠️ ExecutionDay列なし → 寄付き前のため全建玉を対象に続行")

    if df.empty:
        print("  返済対象の建玉なし（当日新規のみ）。返済不要。")
        return

    # ---- 返済発注 ----
    print(f"\n  返済対象: {len(df)}件")
    order_results = []
    for _, p in df.iterrows():
        sym = str(p["Symbol"])
        held = str(p["Side"])                       # "2"=買建(LONG), "1"=売建(SHORT)
        qty = _to_int(p["LeavesQty"])
        mtt = _to_int(p.get("MarginTradeType", 1)) or 1
        close_side = ko.SIDE_SELL if held == ko.SIDE_BUY else ko.SIDE_BUY
        held_str = "買建(LONG)" if held == ko.SIDE_BUY else "売建(SHORT)"
        ret_str = "売り返済" if close_side == ko.SIDE_SELL else "買い返済"
        print(f"  [{sym}] {ko.JP_NAMES.get(sym + '.T', sym)} {held_str} {qty}口 → {ret_str} (MTT={mtt})")

        spec = dict(symbol=sym, side=close_side, qty=qty,
                    cash_margin=3, margin_trade_type=mtt,
                    front_order_type=FRONT_ORDER_TYPE_MOO,
                    close_position_order=0)
        res = ko.send_order(token, dry_run=dry, **spec)
        order_results.append({
            "Ticker": sym,
            "Side": "BUY" if close_side == ko.SIDE_BUY else "SELL",
            "Qty": qty, "Result": res, "spec": spec,
        })
        time.sleep(0.5)

    # ---- サマリー ----
    print("\n  --- サマリー ---")
    if dry:
        print("  DRY RUN: 実際の返済は行われていません（--execute で実行）")
        return

    # Code:10016（取引セッション失効）なら再ログインして未決済分をリトライ
    expired = [r for r in order_results if ko._is_session_expired(r["Result"])]
    if expired:
        print(f"  ⚠️ 取引セッション失効(Code:10016) {len(expired)}件 → 再ログインしてリトライ")
        if ko._force_relogin():
            try:
                token = ko.get_token(force_refresh=True)
            except Exception as e:
                print(f"  ⚠️ トークン再取得失敗: {e}")
            for r in expired:
                r["Result"] = ko.send_order(token, dry_run=False, **r["spec"])
                time.sleep(0.5)

    success = sum(1 for r in order_results
                  if isinstance(r["Result"], dict) and r["Result"].get("Result") == 0)
    print(f"  成功 {success}件 / 失敗 {len(order_results) - success}件")

    failed = [r for r in order_results if ko._is_order_failed(r["Result"])]
    if failed:
        ko._send_failure_alert(failed, open_order=False)
    else:
        ko._send_gmail("[投資戦略] ✅ 残建玉の返済完了",
                       f"残っていた建玉 {len(order_results)}件をすべて返済しました。\n"
                       f"時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
