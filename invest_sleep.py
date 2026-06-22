"""PCをS3スリープさせる（ウェイクイベント有効＝WakeToRunで自動復帰可能）。

背景: `rundll32 powrprof.dll,SetSuspendState 0,1,0` は rundll32 の呼び出し規約のため
引数 0,1,0 が SetSuspendState の3引数に正しく渡らず、ゴミ値で第3引数
bWakeupEventsDisabled が立つことがある。実際 2026-06-22 に午前のスリープ(手動=正規)は
WakeToRunで復帰したのに、午後の rundll32 スリープは15:20の login_pm で復帰せず取引が
丸ごと不発になった（同一S3・違いはウェイク有効/無効のみ）。

ここでは Win32 API を正しい引数で直接呼ぶ:
    SetSuspendState(bHibernate=0, bForce=0, bWakeupEventsDisabled=0)
= 朝あなたが手動で寝かせた正規スリープと同等（ウェイクイベント有効）。
"""
import ctypes
import datetime
import os

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_autologin.txt")


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


log("invest_sleep: SetSuspendState(0,0,0) でS3スリープへ（ウェイクイベント有効）")
# BOOLEAN SetSuspendState(BOOLEAN bHibernate, BOOLEAN bForce, BOOLEAN bWakeupEventsDisabled)
ok = ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
# 復帰後にここへ戻る
log(f"invest_sleep: 復帰（SetSuspendState 戻り値={ok}）")
