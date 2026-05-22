# 自動売買システム — Claude Code プロジェクト設定

## プロジェクト概要

**戦略**: 日米業種リードラグ投資戦略  
前日の米国セクターETF（SPDR XL系）のリターンから、当日の日本セクターETF（東証1617〜1633）のシグナルを生成してトレード。

**証券会社**: 三菱UFJ eスマート証券（旧auカブコム）  
**API**: kabuステーション® REST API (localhost:18080)  
**運用モード**: 本番稼働中（`--execute` あり、2026-05-19より実発注開始）

---

## ディレクトリ構成

```
G:\My Drive\Claude Code\Invest\
├── CLAUDE.md              # このファイル
├── .env_windows           # 環境変数 (KABU_API_PASSWORD, PORTFOLIO_VALUE, KABU_ACCOUNT_NUMBER)
├── config.py              # パス設定（Mac/Windows両対応）
│
├── daily_signal.py        # シグナル計算（米国前日 → 日本当日）
├── kabu_order.py          # 発注モジュール（DRY RUN / 本番）
├── kabu_autologin.py      # kabuStation自動ログイン（GUI自動化）
├── monitor_agent.py       # ログ監視 → Gmail通知
├── report_agent.py        # 損益レポート生成 → Gmail通知
├── calc_pnl.py            # 損益計算（CSVに出力）
├── trim_logs.py           # ログファイル古い行の削除
│
├── run_daily.bat          # 中央ディスパッチャ (login/signal/open/close/shutdown/monitor/report)
├── invest_login.bat       # タスクスケジューラ用ラッパー
├── invest_signal.bat
├── invest_open.bat
├── invest_close.bat
├── invest_shutdown.bat
├── invest_monitor.bat
├── invest_report.bat
│
├── task_invest_login.xml     # タスクスケジューラ XML定義（6本）
├── task_invest_signal.xml
├── task_invest_open.xml
├── task_invest_close.xml
├── task_invest_shutdown.xml
├── task_invest_report.xml
├── task_names.txt            # タスク名（日本語）の定義ファイル
│
├── invest_import_tasks.bat   # タスク再登録（要管理者権限）
├── invest_import_tasks.ps1   # タスク登録スクリプト本体（task_names.txt + XML参照）
├── invest_sync_tasks.bat     # invest_import_tasks.ps1 を C:\Users\tropi\ へコピー
│
├── invest_login_hidden.vbs   # VBS非表示起動（タスクスケジューラ用）
├── invest_shutdown_hidden.vbs
├── invest_test_autologin.ps1 # 手動テスト用（スリープ不要）
│
├── log_autologin.txt      # kabu_autologin.py のログ
├── log_signal.txt         # daily_signal.py のログ
├── log_order.txt          # kabu_order.py のログ
├── log_report.txt         # report_agent.py のログ
├── pnl_history.csv        # calc_pnl.py の出力（日次損益サマリー）
└── pnl_detail_history.csv # calc_pnl.py の出力（銘柄別明細）
```

---

## 日次スケジュール（タスクスケジューラ）

| 時刻  | タスク名（Task Scheduler） | 処理内容                     |
|-------|---------------------------|------------------------------|
| **08:47** | 投資戦略_自動ログイン  | kabuStation起動 + 2FA + API認証（VBS非表示起動） |
| 08:50 | 投資戦略_シグナル計算      | daily_signal.py → signal_YYYYMMDD.csv |
| 09:00 | 投資戦略_寄付き発注        | kabu_order.py --execute（本番発注） |
| 〜kabuStation起動したまま待機〜 | | |
| 15:25 | 投資戦略_引成決済          | kabu_order.py --execute --close（本番決済） |
| 15:30 | 投資戦略_自動終了          | kabuStation終了（VBS非表示起動） |
| 15:35 | 投資戦略_損益レポート      | report_agent.py → Gmail通知 |

**タスク登録手順**:
1. `invest_sync_tasks.bat` を実行（ps1ファイルを `C:\Users\tropi\` にコピー）
2. `invest_import_tasks.bat` を**管理者権限**で実行（タスク登録）

---

## 自動ログインテスト

```powershell
# スリープ不要の手動テスト（ログイン動作確認用）
powershell.exe -ExecutionPolicy Bypass -File "G:\My Drive\Claude Code\Invest\invest_test_autologin.ps1"
```

スリープ復帰テストは `invest-test-login` スキルを使用（例: `/invest-test-login 20:30`）。

---

## 手動実行コマンド

```bat
# シグナル確認
run_daily.bat signal

# DRY RUN 発注テスト
run_daily.bat dry

# 本番発注
run_daily.bat open

# ログ確認
type log_autologin.txt
type log_signal.txt
type log_order.txt

# 損益レポート
run_daily.bat report

# 損益計算（全日）
python -X utf8 calc_pnl.py

# 損益計算（特定日: 米国市場日付で指定）
python -X utf8 calc_pnl.py 20260421

# ログトリム
python -X utf8 trim_logs.py
```

---

## タスクスケジューラの再登録

**必ず管理者権限で実行すること**（管理者権限なしでは Set-ScheduledTask が失敗する）

```bat
# 1. Gドライブ → C:\Users\tropi\ にコピー
invest_sync_tasks.bat

# 2. 管理者コマンドプロンプトで
invest_import_tasks.bat
```

XML修正時の注意: XMLファイルはUTF-16エンコーディング。PowerShellで編集する場合は  
`[System.IO.File]::ReadAllText(..., [Text.Encoding]::Unicode)` を使うこと。

---

## 重要な既知事項・注意点

### 【重要】Claude Codeブランチ切り替えによるファイル上書きリスク
- Claude Codeは新セッションを開始するたびに新しいブランチを作成する
- ブランチ切り替え時にディスク上のファイルが古いバージョンに上書きされる可能性がある
- **対策**: スクリプト修正後は必ず `master` にマージして push すること
- 本番タスクが動く前日夜にブランチ操作を行った場合は、翌朝のログを必ず確認すること

### シグナルファイルの命名規則
- ファイル名は**米国市場の日付**（日本の前営業日）で保存される
- 例: 日本 04-22 の取引シグナル → `signal_20260421.csv`（前日の米国 04-21 データ）
- `calc_pnl.py` に渡す日付引数も米国市場日付で指定すること
- 「今日のシグナルがない」と思ったら前営業日のファイル名を確認すること

### ログファイルの競合
- `kabu_autologin.py` / `monitor_agent.py` は `logging.basicConfig(filename=...)` で内部的にファイルを開く
- `run_daily.bat` で `>> log_autologin.txt 2>&1` を**追加してはいけない**（同一ファイルを二重オープン → PermissionError）
- `daily_signal.py` / `kabu_order.py` は標準出力のみ → bat側の `>> log_*.txt 2>&1` でリダイレクト

### 管理者権限とGドライブ
- Windowsでは**管理者権限で実行するとGドライブ（Google Drive）がマップされない**
- タスクスケジューラのタスク本体はGドライブへアクセスしない（ラッパーbatがsetlocalでパスを解決）
- 管理者コマンドプロンプトからGドライブのファイルを直接実行する場合は `net use G: \\...` が必要な場合あり

### PowerShellのエンコーディング
- PowerShell 5.x は CP932 で読むため、PS1ファイルに日本語を含めると parse error になる
- PS1ファイルは**英語のみ**で記述すること

### Python環境
- Python実行ファイル: `C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- `run_daily.bat` 冒頭で `SET PATH=...` を明示設定している（タスクスケジューラ環境ではPATHが不完全なため）

### kabuステーション® API
- REST: `http://localhost:18080/kabusapi/`
- WebSocket: `ws://localhost:18081/kabusapi/websocket`
- APIパスワード: `.env_windows` の `KABU_API_PASSWORD`
- ポートフォリオ金額: `.env_windows` の `PORTFOLIO_VALUE`（現在: 990,000円）

### 発注モード
- **DRY RUN**: `run_daily.bat dry` → シミュレーションのみ、実際の注文なし
- **本番（現在）**: `run_daily.bat open/close` → `--execute` フラグ付きで実発注
- 現在のステータス: 本番稼働中（2026-05-19より実発注開始）

### kabuStation自動ログインフロー（2026-05 新仕様）
kabuStationのログイン仕様変更に伴い `kabu_autologin.py` を更新済み（2026-04-28〜05-22）。

**ログインステップ順序（重要）:**
1. Gmail API初期化
2. ログイン済み確認（スキップ判定）
3. kabuStation未起動なら起動
4. ログインダイアログ待機（最大90秒）
5. 口座番号をWM_CHARで入力 → Enter×2（これで2FAメール送信される）
6. GmailからOTPコード取得（最大30秒）、未着の場合はスキップして次へ進む
7. OTP届いた場合: 2FAフォーム表示待機（3秒）→ OTPをWM_CHARで入力 → Enter
8. パスキー選択画面読み込み待機（8秒）
9. パスキー選択画面の処理（優先順位順）:
   - **第1優先**: pywinauto UIA で `title_re=".*パスキーなし.*"` を検索 → `invoke()` で直接選択
   - **第2優先**: pywinauto UIA で `Application().connect(handle=hwnd)` で接続 → 「パスキーを作成」にSetFocus → WM_SETFOCUS送信 → Tab×1 → Enter
   - **フォールバック**: スクリーンショットでオレンジボタン検出 → WM_MOUSEMOVEホバー → Tab×1 → Enter
10. API認証確認（最大120秒）

**重要な実装ルール:**
- 口座番号・2FAコード入力時はフォーカス操作（WM_ACTIVATE / WM_SETFOCUS）を**送らない**（カーソルが外れる原因）
- 口座番号・2FAコード入力時はDOM起点クリック（WM_LBUTTONDOWN）も**送らない**（同上）
- 口座番号・OTP入力ともにカーソルは起動時から正しい位置にある
- パスキー選択画面で「パスキーを作成」ボタンを**クリックしてはいけない**（パスキー作成フローに遷移する）
- 「パスキーなしで続行」はUIAの `invoke()` で選択可能（テキスト選択はできないがInvokePatternは公開されている）
- パスキー選択ウィンドウは独立した新ウィンドウではなく既存CEFウィンドウ内に表示される
- UIAのInvokeはモニターオフでも機能する（COM/IPC経由のため）。スクリーンロック中も `LogonType Interactive` タスクであれば機能する可能性が高い

---

## 環境変数（.env_windows）

```
KABU_API_PASSWORD=<APIパスワード>
PORTFOLIO_VALUE=990000
KABU_ACCOUNT_NUMBER=<口座番号（8桁）>
```

---

## セクターETF対応表（東証）

| ティッカー | セクター名       |
|------------|------------------|
| 1617.T     | 食品             |
| 1618.T     | エネルギー資源   |
| 1619.T     | 建設・資材       |
| 1620.T     | 素材・化学       |
| 1621.T     | 医薬品           |
| 1622.T     | 自動車・輸送機   |
| 1623.T     | 鉄鋼・非鉄       |
| 1624.T     | 機械             |
| 1625.T     | 電機・精密       |
| 1626.T     | 情報通信・サービス |
| 1627.T     | 電力・ガス       |
| 1628.T     | 運輸・物流       |
| 1629.T     | 商社・卸売       |
| 1630.T     | 小売             |
| 1631.T     | 銀行             |
| 1632.T     | 金融（除く銀行） |
| 1633.T     | 不動産           |
