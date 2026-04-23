@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
SET PYTHONIOENCODING=utf-8

REM ============================================================
REM 日米業種リードラグ投資戦略
REM Windows 一括セットアップスクリプト
REM ============================================================

SET PROJECT_DIR=%~dp0
SET LOG_FILE=%PROJECT_DIR%setup_log.txt
SET CONFIG_FILE=%PROJECT_DIR%.env_windows

echo.
echo ============================================================
echo   日米業種リードラグ投資戦略 セットアップ
echo ============================================================
echo.
echo セットアップログ: %LOG_FILE%
echo.

echo [%DATE% %TIME%] セットアップ開始 > "%LOG_FILE%"

REM ============================================================
REM STEP 1: Python確認
REM ============================================================
echo [STEP 1/5] Python の確認...
echo.

python --version > nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo   [NG] Python が見つかりません。
    echo.
    echo   以下の手順でインストールしてください:
    echo   1. python.org/downloads を開く
    echo   2. Download Python 3.x.x をクリック
    echo   3. インストール時に "Add Python to PATH" にチェック
    echo.
    echo   インストール後、このスクリプトを再実行してください。
    pause
    exit /b 1
)

FOR /F "tokens=*" %%i IN ('python --version') DO SET PYTHON_VER=%%i
echo   [OK] %PYTHON_VER% を検出しました
echo [%DATE% %TIME%] %PYTHON_VER% 確認OK >> "%LOG_FILE%"

REM ============================================================
REM STEP 2: 必要ライブラリのインストール
REM ============================================================
echo.
echo [STEP 2/5] 必要ライブラリのインストール...
echo   （初回は数分かかる場合があります）
echo.

python -m pip install --upgrade pip --quiet
echo   pip をアップデートしました

SET PACKAGES=numpy pandas scipy yfinance requests pyarrow matplotlib
FOR %%p IN (%PACKAGES%) DO (
    echo   インストール中: %%p
    python -m pip install %%p --quiet >> "%LOG_FILE%" 2>&1
    IF !ERRORLEVEL! NEQ 0 (
        echo   [!!] %%p のインストールに失敗しました
        echo [%DATE% %TIME%] %%p インストール失敗 >> "%LOG_FILE%"
    ) ELSE (
        echo   [OK] %%p
    )
)

echo.
echo   ライブラリのインストール完了
echo [%DATE% %TIME%] ライブラリインストール完了 >> "%LOG_FILE%"

REM ============================================================
REM STEP 3: APIパスワードの設定
REM ============================================================
echo.
echo [STEP 3/5] kabuステーション(R) APIパスワードの設定...
echo.

IF EXIST "%CONFIG_FILE%" (
    FOR /F "tokens=2 delims==" %%i IN ('findstr "KABU_API_PASSWORD" "%CONFIG_FILE%"') DO SET EXISTING_PW=%%i
    IF NOT "!EXISTING_PW!"=="" (
        echo   既存のパスワード設定が見つかりました。
        SET /P OVERWRITE="   上書きしますか？ (y/N): "
        IF /I NOT "!OVERWRITE!"=="y" GOTO SKIP_PASSWORD
    )
)

echo   kabuステーション(R) のAPIパスワードを入力してください。
echo   （システム設定 > APIタブ > 本番用パスワード）
echo.
SET /P API_PASSWORD="   APIパスワード: "

IF "!API_PASSWORD!"=="" (
    echo   [!!] パスワードが入力されませんでした。
    SET API_PASSWORD=PLEASE_SET_YOUR_PASSWORD
)

echo KABU_API_PASSWORD=!API_PASSWORD! > "%CONFIG_FILE%"
echo PORTFOLIO_VALUE=1000000 >> "%CONFIG_FILE%"
echo   [OK] パスワードを保存しました: %CONFIG_FILE%
echo [%DATE% %TIME%] APIパスワード設定完了 >> "%LOG_FILE%"

:SKIP_PASSWORD

echo.
echo   運用資産額を設定してください（デフォルト: 1,000,000円）
SET /P PORTFOLIO_INPUT="   運用資産額（円）[Enter でスキップ]: "
IF NOT "!PORTFOLIO_INPUT!"=="" (
    powershell -Command "(Get-Content '%CONFIG_FILE%') -replace 'PORTFOLIO_VALUE=.*', 'PORTFOLIO_VALUE=!PORTFOLIO_INPUT!' | Set-Content '%CONFIG_FILE%'"
    echo   [OK] 運用資産額: !PORTFOLIO_INPUT! 円
)

REM ============================================================
REM STEP 4: 接続テスト
REM ============================================================
echo.
echo [STEP 4/5] 接続テスト...
echo.
echo   ※ kabuステーション(R) が起動していない場合は n でスキップ
echo.
SET /P DO_TEST="   接続テストを実行しますか？ (Y/n): "
IF /I "!DO_TEST!"=="n" (
    echo   スキップしました
    GOTO SKIP_TEST
)

FOR /F "usebackq tokens=1,* delims==" %%i IN ("%CONFIG_FILE%") DO SET "%%i=%%j"
python "%PROJECT_DIR%kabu_order.py" --test
echo [%DATE% %TIME%] 接続テスト実行 >> "%LOG_FILE%"
echo.
pause

:SKIP_TEST

REM ============================================================
REM STEP 5: タスクスケジューラへの登録
REM ============================================================
echo.
echo [STEP 5/5] タスクスケジューラへの登録...
echo.
echo   以下のスケジュールで自動実行を登録します:
echo     08:41  kabuステーション自動ログイン (kabu_autologin.py)
echo     08:50  シグナル計算 (daily_signal.py)
echo     09:00  寄付き発注  (kabu_order.py)
echo     15:25  引成決済    (kabu_order.py --close)
echo     15:30  kabuステーション終了 (kabu_autologin.py --mode shutdown)
echo     平日(月〜金)のみ実行
echo.
SET /P DO_SCHEDULE="   タスクスケジューラに登録しますか？ (Y/n): "
IF /I "!DO_SCHEDULE!"=="n" GOTO SKIP_SCHEDULE

REM run_daily.bat を生成
SET RUNNER=%PROJECT_DIR%run_daily.bat
echo @echo off > "%RUNNER%"
echo chcp 65001 ^> nul >> "%RUNNER%"
echo setlocal >> "%RUNNER%"
echo SET PYTHONIOENCODING=utf-8 >> "%RUNNER%"
echo FOR /F "usebackq tokens=1,* delims==" %%%%i IN ("%CONFIG_FILE%") DO SET "%%%%i=%%%%j" >> "%RUNNER%"
echo IF "%%1"=="login"    python "%PROJECT_DIR%kabu_autologin.py" ^>^> "%PROJECT_DIR%log_autologin.txt" 2^>^&1 >> "%RUNNER%"
echo IF "%%1"=="shutdown" python "%PROJECT_DIR%kabu_autologin.py" --mode shutdown ^>^> "%PROJECT_DIR%log_autologin.txt" 2^>^&1 >> "%RUNNER%"
echo IF "%%1"=="signal" python "%PROJECT_DIR%daily_signal.py" ^>^> "%PROJECT_DIR%log_signal.txt" 2^>^&1 >> "%RUNNER%"
echo IF "%%1"=="open"   python "%PROJECT_DIR%kabu_order.py" --execute --value %%PORTFOLIO_VALUE%% ^>^> "%PROJECT_DIR%log_order.txt" 2^>^&1 >> "%RUNNER%"
echo IF "%%1"=="close"  python "%PROJECT_DIR%kabu_order.py" --execute --close --value %%PORTFOLIO_VALUE%% ^>^> "%PROJECT_DIR%log_order.txt" 2^>^&1 >> "%RUNNER%"
echo IF "%%1"=="dry"    python "%PROJECT_DIR%kabu_order.py" --value %%PORTFOLIO_VALUE%% >> "%RUNNER%"

echo   [OK] run_daily.bat を作成しました

REM 8.3短縮パスを取得（スペース含むパスでもSCHTASKSが動作する）
FOR %%F IN ("%RUNNER%") DO SET RUNNER_SHORT=%%~sF
echo   実行パス: %RUNNER_SHORT%

REM 既存タスクの削除
SCHTASKS /DELETE /TN "投資戦略_自動ログイン" /F > nul 2>&1
SCHTASKS /DELETE /TN "投資戦略_シグナル計算" /F > nul 2>&1
SCHTASKS /DELETE /TN "投資戦略_寄付き発注" /F > nul 2>&1
SCHTASKS /DELETE /TN "投資戦略_引成決済" /F > nul 2>&1
SCHTASKS /DELETE /TN "投資戦略_自動終了" /F > nul 2>&1

REM タスク登録
SCHTASKS /CREATE /TN "投資戦略_自動ログイン" /TR "%RUNNER_SHORT% login" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:41 /F
IF %ERRORLEVEL% EQU 0 (
    echo   [OK] 08:41 自動ログイン を登録しました
) ELSE (
    echo   [!!] 自動ログインの登録に失敗
    echo        管理者として実行してみてください
)

SCHTASKS /CREATE /TN "投資戦略_シグナル計算" /TR "%RUNNER_SHORT% signal" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:50 /F
IF %ERRORLEVEL% EQU 0 (
    echo   [OK] 08:50 シグナル計算 を登録しました
) ELSE (
    echo   [!!] シグナル計算の登録に失敗
)

SCHTASKS /CREATE /TN "投資戦略_寄付き発注" /TR "%RUNNER_SHORT% open" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:00 /F
IF %ERRORLEVEL% EQU 0 (
    echo   [OK] 09:00 寄付き発注 を登録しました
) ELSE (
    echo   [!!] 寄付き発注の登録に失敗
)

SCHTASKS /CREATE /TN "投資戦略_引成決済" /TR "%RUNNER_SHORT% close" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:25 /F
IF %ERRORLEVEL% EQU 0 (
    echo   [OK] 15:25 引成決済 を登録しました
) ELSE (
    echo   [!!] 引成決済の登録に失敗
)

SCHTASKS /CREATE /TN "投資戦略_自動終了" /TR "%RUNNER_SHORT% shutdown" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:30 /F
IF %ERRORLEVEL% EQU 0 (
    echo   [OK] 15:30 自動終了 を登録しました
) ELSE (
    echo   [!!] 自動終了の登録に失敗
)

echo.
echo   登録済みタスク一覧:
SCHTASKS /QUERY /FO TABLE /NH | findstr "投資戦略"
echo [%DATE% %TIME%] タスクスケジューラ登録完了 >> "%LOG_FILE%"

:SKIP_SCHEDULE

REM ============================================================
REM セットアップ完了
REM ============================================================
echo.
echo ============================================================
echo   [OK] セットアップ完了！
echo ============================================================
echo.
echo   動作確認（DRY RUN）:
echo     run_daily.bat dry
echo.
echo   ログ確認:
echo     log_signal.txt  - シグナル計算ログ
echo     log_order.txt   - 発注ログ
echo.
echo [%DATE% %TIME%] セットアップ完了 >> "%LOG_FILE%"
pause
