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
├── .env_windows           # 環境変数 (KABU_API_PASSWORD, PORTFOLIO_VALUE)
├── config.py              # パス設定（Mac/Windows両対応）
│
├── daily_signal.py        # シグナル計算（米国前日 → 日本当日）
├── kabu_order.py          # 発注モジュール（DRY RUN / 本番）
├── kabu_autologin.py      # kabuStation自動ログイン（GUI自動化）
├── monitor_agent.py       # ログ監視 → Gmail通知
│
├── run_daily.bat          # 中央ディスパッチャ (login/signal/open/close/shutdown/monitor)
├── invest_login.bat       # タスクスケジューラ用ラッパー
├── invest_signal.bat
├── invest_open.bat
├── invest_close.bat
├── invest_shutdown.bat
├── invest_monitor.bat
│
├── task_invest_login.xml  # タスクスケジューラ XML定義（5本）
├── task_invest_signal.xml
├── task_invest_open.xml
├── task_invest_close.xml
├── task_invest_shutdown.xml
│
├── invest_import_tasks.bat   # タスク再登録（要管理者権限）
├── invest_import_tasks.ps1
│
├── log_autologin.txt      # kabu_autologin.py / monitor_agent.py のログ
├── log_signal.txt         # daily_signal.py のログ
└── log_order.txt          # kabu_order.py のログ
```

---

## 日次スケジュール（タスクスケジューラ）

| 時刻  | タスク名（Task Scheduler） | 処理内容                     |
|-------|---------------------------|------------------------------|
| **08:47** | invest_login          | kabuStation起動 + 2FA + API認証（VBS非表示起動） |
| 08:50 | invest_signal             | daily_signal.py → signal_YYYYMMDD.csv |
| 09:00 | invest_open               | kabu_order.py（DRY RUN 発注） |
| 09:05 | —（手動 or 別途）          | monitor_agent.py → Gmail（朝通知） |
| 09:10 | invest_morning_shutdown   | kabuStation終了 → PC自然スリープへ |
| 〜スリープ〜 | | |
| 15:10 | invest_afternoon_login    | kabuStation再起動 + 2FA + API認証 |
| 15:25 | invest_close              | kabu_order.py --close（DRY RUN 決済） |
| 15:30 | invest_shutdown           | kabuStation終了（VBS非表示起動） |
| 15:32 | —（手動 or 別途）          | monitor_agent.py → Gmail（夕通知） |

**タスク登録ファイル**: C:\Users\tropi\invest_import_tasks.ps1（管理者権限で実行）

---

## 自動ログインテスト

```powershell
# スリープ不要の手動テスト（ログイン動作確認用）
powershell.exe -ExecutionPolicy Bypass -File "G:\My Drive\Claude Code\Invest\invest_test_autologin.ps1"
```

---

## 手動実行コマンド

```bat
# シグナル確認
run_daily.bat signal

# DRY RUN 発注テスト
run_daily.bat dry

# 本番発注（要 --execute フラグ変更）
run_daily.bat open

# ログ確認
type log_autologin.txt
type log_signal.txt
type log_order.txt

# 今日のシグナルCSV（※ファイル名は米国市場の日付 = 日本の前営業日）
# 例: 日本04-22の取引 → signal_20260421.csv（前日の米国04-21データ）
type signal_YYYYMMDD.csv

# 損益計算（全日）
python -X utf8 calc_pnl.py

# 損益計算（特定日: 米国市場日付で指定）
python -X utf8 calc_pnl.py 20260421
```

---

## タスクスケジューラの再登録

**必ず管理者権限で実行すること**（管理者権限なしでは Set-ScheduledTask が失敗する）

```bat
# 管理者コマンドプロンプトで
invest_import_tasks.bat
```

XML修正時の注意: XMLファイルはUTF-16エンコーディング。PowerShellで編集する場合は  
`[System.IO.File]::ReadAllText(..., [Text.Encoding]::Unicode)` を使うこと。

---

## 重要な既知事項・注意点

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
kabuStationのログイン仕様変更に伴い `kabu_autologin.py` を更新済み（2026-04-28〜05-01）。

**ログインステップ順序（重要）:**
1. Gmail API初期化
2. ログイン済み確認（スキップ判定）
3. kabuStation未起動なら起動
4. ログインダイアログ待機（最大90秒）
5. 口座番号をWM_CHARで入力 → Enter×2（これで2FAメール送信される）
6. GmailからOTPコード取得（最大30秒）、未着の場合はスキップ
7. 2FAフォーム表示待機（3秒）
8. OTPをWM_CHARで入力 → Enter
9. パスキー選択画面読み込み待機（5秒）
10. ウィンドウ最大化 → UIA経由で「パスキーなしで続行」リンクをクリック（2FAあり/スキップ問わず同じ処理）
11. API認証確認（最大120秒）

**重要な実装ルール:**
- 口座番号・2FAコード入力時はフォーカス操作（WM_ACTIVATE / WM_SETFOCUS）を**送らない**（カーソルが外れる原因）
- 口座番号・2FAコード入力時はDOM起点クリック（WM_LBUTTONDOWN）も**送らない**（同上）
- 口座番号・OTP入力ともにカーソルは起動時から正しい位置にある
- パスキー選択画面ではDOM起点クリックは使用可能（入力フィールドではないため）
- パスキー選択ウィンドウは独立した新ウィンドウではなく既存CEFウィンドウ内に表示される

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
