@echo off
REM === DRY検証期間中（2026-06-08〜）: 板から始値/終値を取得し仮想損益をExcel蓄積。
REM     検証終了後は "report"（本番の実約定ベースレポート）に戻す ===
call "%~dp0run_daily.bat" paper
