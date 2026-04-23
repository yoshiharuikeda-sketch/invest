@echo off
REM ============================================================
REM 日米業種リードラグ投資戦略 - Windows自動実行スクリプト
REM 使い方:
REM   朝の発注  → run_windows.bat open
REM   夕の決済  → run_windows.bat close
REM   確認のみ  → run_windows.bat dry
REM ============================================================

REM === 設定 ===
REM Google Driveのパス（Windowsでのマウント先。G:ドライブが一般的）
SET GDRIVE_ROOT=G:\My Drive
SET PROJECT_DIR=%GDRIVE_ROOT%\投資戦略\
SET PYTHON=python
SET KABU_API_PASSWORD=ここにAPIパスワードを入力
SET PORTFOLIO_VALUE=1000000

REM === 環境変数にパスワードを設定 ===
SET KABU_API_PASSWORD=%KABU_API_PASSWORD%

IF "%1"=="open" GOTO OPEN_ORDER
IF "%1"=="close" GOTO CLOSE_ORDER
IF "%1"=="dry" GOTO DRY_RUN
IF "%1"=="test" GOTO TEST

REM === デフォルト: DRY RUN ===
:DRY_RUN
echo [%DATE% %TIME%] DRY RUN モードで発注確認中...
%PYTHON% "%PROJECT_DIR%kabu_order.py" --value %PORTFOLIO_VALUE%
GOTO END

REM === 寄付き発注 ===
:OPEN_ORDER
echo [%DATE% %TIME%] 寄付き発注を実行中...
%PYTHON% "%PROJECT_DIR%kabu_order.py" --execute --value %PORTFOLIO_VALUE%
GOTO END

REM === 引成決済 ===
:CLOSE_ORDER
echo [%DATE% %TIME%] 引成決済を実行中...
%PYTHON% "%PROJECT_DIR%kabu_order.py" --execute --close --value %PORTFOLIO_VALUE%
GOTO END

REM === 接続テスト ===
:TEST
echo [%DATE% %TIME%] 接続テスト中...
%PYTHON% "%PROJECT_DIR%kabu_order.py" --test
GOTO END

:END
echo.
echo 完了しました。
pause
