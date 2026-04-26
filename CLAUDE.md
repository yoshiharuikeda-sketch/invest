# 自動売買シスチE��  EClaude Code プロジェクト設宁E
## プロジェクト概要E
**戦略**: 日米業種リードラグ投賁E��略  
前日の米国セクターETF�E�EPDR XL系�E��Eリターンから、当日の日本セクターETF�E�東証1617、E633�E��Eシグナルを生成してトレード、E
**証券会社**: 三菱UFJ eスマ�Eト証券�E�旧auカブコム�E�E 
**API**: kabuスチE�Eション® REST API (localhost:18080)  
**運用モーチE*: 現在 DRY RUN�E�E--execute` なし！EↁE来週以陁E本番予宁E
---

## チE��レクトリ構�E

```
G:\My Drive\Claude Code\Invest\
├── CLAUDE.md              # こ�Eファイル
├── .env_windows           # 環墁E��数 (KABU_API_PASSWORD, PORTFOLIO_VALUE)
├── config.py              # パス設定！Eac/Windows両対応！E━E├── daily_signal.py        # シグナル計算（米国前日 ↁE日本当日�E�E├── kabu_order.py          # 発注モジュール�E�ERY RUN / 本番�E�E├── kabu_autologin.py      # kabuStation自動ログイン�E�EUI自動化�E�E├── monitor_agent.py       # ログ監要EↁEGmail通知
━E├── run_daily.bat          # 中央チE��スパッチャ (login/signal/open/close/shutdown/monitor)
├── invest_login.bat       # タスクスケジューラ用ラチE��ー
├── invest_signal.bat
├── invest_open.bat
├── invest_close.bat
├── invest_shutdown.bat
├── invest_monitor.bat
━E├── task_invest_login.xml  # タスクスケジューラ XML定義�E�E本�E�E├── task_invest_signal.xml
├── task_invest_open.xml
├── task_invest_close.xml
├── task_invest_shutdown.xml
━E├── invest_import_tasks.bat   # タスク再登録�E�要管琁E��E��限！E├── invest_import_tasks.ps1
━E├── log_autologin.txt      # kabu_autologin.py / monitor_agent.py のログ
├── log_signal.txt         # daily_signal.py のログ
└── log_order.txt          # kabu_order.py のログ
```

---

## 日次スケジュール�E�タスクスケジューラ�E�E
| 時刻  | タスク名！Eask Scheduler�E�E| 処琁E�E容                     |
|-------|---------------------------|------------------------------|
| 08:45 | invest_login              | kabuStation起勁E+ 2FA + API認証�E�EBS非表示起動！E|
| 08:50 | invest_signal             | daily_signal.py ↁEsignal_YYYYMMDD.csv |
| 09:00 | invest_open               | kabu_order.py�E�ERY RUN 発注�E�E|
| 09:05 | —（手勁Eor 別途！E         | monitor_agent.py ↁEGmail�E�朝通知�E�E|
| 09:10 | invest_morning_shutdown   | kabuStation終亁EↁEPC自然スリープへ |
| 〜スリープ、E| | |
| 15:10 | invest_afternoon_login    | kabuStation再起勁E+ 2FA + API認証 |
| 15:25 | invest_close              | kabu_order.py --close�E�ERY RUN 決済！E|
| 15:30 | invest_shutdown           | kabuStation終亁E��EBS非表示起動！E|
| 15:32 | —（手勁Eor 別途！E         | monitor_agent.py ↁEGmail�E�夕通知�E�E|

**タスク登録ファイル**: C:\Users\tropi\invest_import_tasks.ps1�E�管琁E��E��限で実行！E
---

## 手動実行コマンチE
```bat
# シグナル確誁Erun_daily.bat signal

# DRY RUN 発注チE��チErun_daily.bat dry

# 本番発注�E�要E--execute フラグ変更�E�Erun_daily.bat open

# ログ確誁Etype log_autologin.txt
type log_signal.txt
type log_order.txt

# 今日のシグナルCSV�E�※ファイル名�E米国市場の日仁E= 日本の前営業日�E�E# 侁E 日本04-22の取弁EↁEsignal_20260421.csv�E�前日の米国04-21チE�Eタ�E�Etype signal_YYYYMMDD.csv

# 損益計算（�E日�E�Epython -X utf8 calc_pnl.py

# 損益計算（特定日: 米国市場日付で持E��！Epython -X utf8 calc_pnl.py 20260421
```

---

## タスクスケジューラの再登録

**忁E��管琁E��E��限で実行すること**�E�管琁E��E��限なしでは Set-ScheduledTask が失敗する！E
```bat
# 管琁E��E��マンド�Eロンプトで
invest_import_tasks.bat
```

XML修正時�E注愁E XMLファイルはUTF-16エンコーチE��ング。PowerShellで編雁E��る場合�E  
`[System.IO.File]::ReadAllText(..., [Text.Encoding]::Unicode)` を使ぁE��と、E
---

## 重要な既知事頁E�E注意点

### シグナルファイルの命名規則
- ファイル名�E**米国市場の日仁E*�E�日本の前営業日�E�で保存される
- 侁E 日本 04-22 の取引シグナル ↁE`signal_20260421.csv`�E�前日の米国 04-21 チE�Eタ�E�E- `calc_pnl.py` に渡す日付引数も米国市場日付で持E��すること
- 「今日のシグナルがなぁE��と思ったら前営業日のファイル名を確認すること

### ログファイルの競吁E- `kabu_autologin.py` / `monitor_agent.py` は `logging.basicConfig(filename=...)` で冁E��皁E��ファイルを開ぁE- `run_daily.bat` で `>> log_autologin.txt 2>&1` めE*追加してはぁE��なぁE*�E�同一ファイルを二重オープン ↁEPermissionError�E�E- `daily_signal.py` / `kabu_order.py` は標準�E力�Eみ ↁEbat側の `>> log_*.txt 2>&1` でリダイレクチE
### 管琁E��E��限とGドライチE- Windowsでは**管琁E��E��限で実行するとGドライブ！Eoogle Drive�E�がマップされなぁE*
- タスクスケジューラのタスク本体�EGドライブへアクセスしなぁE��ラチE��ーbatがsetlocalでパスを解決�E�E- 管琁E��E��マンド�EロンプトからGドライブ�Eファイルを直接実行する場合�E `net use G: \\...` が忁E��な場合あめE
### PowerShellのエンコーチE��ング
- PowerShell 5.x は CP932 で読むため、PS1ファイルに日本語を含めると parse error になめE- PS1ファイルは**英語�Eみ**で記述すること

### Python環墁E- Python実行ファイル: `C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- `run_daily.bat` 冒頭で `SET PATH=...` を�E示設定してぁE���E�タスクスケジューラ環墁E��はPATHが不完�Eなため�E�E
### kabuスチE�Eション® API
- REST: `http://localhost:18080/kabusapi/`
- WebSocket: `ws://localhost:18081/kabusapi/websocket`
- APIパスワーチE `.env_windows` の `KABU_API_PASSWORD`
- ポ�Eトフォリオ金顁E `.env_windows` の `PORTFOLIO_VALUE`�E�現在: 990,000冁E��E
### 発注モーチE- **チE��ォルト！ERY RUN�E�E*: `run_daily.bat open/close` ↁEシミュレーションのみ、実際の注斁E��ぁE- **本番**: `kabu_order.py` に `--execute` フラグを追加して初めて実発注
- 現在のスチE�Eタス: DRY RUN週�E�E026-04-14〜）�E 来週以降本番検訁E
---

## 環墁E��数�E�Eenv_windows�E�E
```
KABU_API_PASSWORD=<APIパスワーチE
PORTFOLIO_VALUE=990000
```

---

## セクターETF対応表�E�東証�E�E
| チE��チE��ー | セクター吁E      |
|------------|------------------|
| 1617.T     | 食品             |
| 1618.T     | エネルギー賁E��E  |
| 1619.T     | 建設・賁E��       |
| 1620.T     | 素材�E化学       |
| 1621.T     | 医薬品E          |
| 1622.T     | 自動車�E輸送橁E  |
| 1623.T     | 鉁E��・非鉄       |
| 1624.T     | 機械             |
| 1625.T     | 電機�E精寁E      |
| 1626.T     | 惁E��通信・サービス |
| 1627.T     | 電力�Eガス       |
| 1628.T     | 運輸・物流E      |
| 1629.T     | 啁E��・卸売       |
| 1630.T     | 小売             |
| 1631.T     | 銀衁E            |
| 1632.T     | 金融�E�除く銀行！E|
| 1633.T     | 不動産           |
