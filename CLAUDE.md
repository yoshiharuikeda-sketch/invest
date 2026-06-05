# 自動売買システム — Claude Code プロジェクト設定

## プロジェクト概要

**戦略**: 日米業種リードラグ投資戦略  
前日の米国セクターETF（SPDR XL系）のリターンから、当日の日本セクターETF（東証1617〜1633）のシグナルを生成してトレード。

**証券会社**: 三菱UFJ eスマート証券（旧auカブコム）  
**API**: kabuステーション® REST API (localhost:18080)  
**運用モード**: 本番稼働中（`--execute` あり、2026-05-19より実発注開始）  
**運用規模**: PORTFOLIO_VALUE=300,000円（戦略有効性確認中のため縮小運用中）

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
├── fetch_fills.py         # 約定照会＋板情報（15:32実行 → fills_YYYYMMDD.csv）
├── monitor_agent.py       # ログ監視 → Gmail通知
├── report_agent.py        # 損益レポート生成 → Gmail通知 + Excel蓄積
├── calc_pnl.py            # 損益計算（実約定データ優先、yfinanceフォールバック）
├── trim_logs.py           # ログファイル古い行の削除
│
├── run_daily.bat          # 中央ディスパッチャ (login/signal/open/close/fills/shutdown/monitor/report)
├── invest_login.bat       # タスクスケジューラ用ラッパー
├── invest_signal.bat
├── invest_open.bat
├── invest_close.bat
├── invest_fills.bat       # 約定照会ラッパー
├── invest_shutdown.bat
├── invest_monitor.bat
├── invest_report.bat
│
├── task_invest_login.xml     # タスクスケジューラ XML定義（7本、UTF-8）
├── task_invest_signal.xml
├── task_invest_open.xml
├── task_invest_close.xml
├── task_invest_fills.xml     # 約定照会タスク（15:32, WakeToRun=true）
├── task_invest_shutdown.xml  # 自動終了タスク（15:40, WakeToRun=true）
├── task_invest_report.xml    # 損益レポートタスク（15:35, WakeToRun=true）
├── task_names.txt            # タスク名（日本語）の定義ファイル
│
├── invest_import_tasks.bat   # タスク再登録
├── invest_import_tasks.ps1   # タスク登録スクリプト本体
├── invest_sync_tasks.bat     # ps1・task_names.txt・全XMLを C:\Users\tropi\ へコピー
│
├── invest_login_hidden.vbs   # VBS非表示起動（タスクスケジューラ用）
├── invest_shutdown_hidden.vbs
├── invest_test_autologin.ps1 # 手動テスト用（スリープ不要）
│
├── log_autologin.txt      # kabu_autologin.py のログ
├── log_signal.txt         # daily_signal.py のログ
├── log_order.txt          # kabu_order.py のログ
├── log_fills.txt          # fetch_fills.py のログ
├── log_report.txt         # report_agent.py のログ
├── fills_YYYYMMDD.csv     # fetch_fills.py の出力（実約定価格・数量・板始値・板終値）
├── pnl_history.csv        # report_agent.py の出力（日次損益サマリー）
├── pnl_detail_history.csv # report_agent.py の出力（銘柄別明細）
└── trade_history.xlsx     # report_agent.py の出力（2シート構成・書式付き）
```

---

## 日次スケジュール（タスクスケジューラ）

| 時刻  | タスク名 | 処理内容 | WakeToRun | StartWhenAvail |
|-------|---------|---------|:----:|:----:|
| 08:45 | `invest_login`（英語名・補助） | 自動ログイン（1回目） | true | - |
| **08:47** | 投資戦略_自動ログイン | kabuStation起動 + 2FA + API認証（VBS非表示起動）| true | - |
| 08:50 | 投資戦略_シグナル計算 | daily_signal.py → signal_YYYYMMDD.csv | - | - |
| 09:00 | 投資戦略_寄付き発注 | kabu_order.py --execute（本番発注） | - | - |
| 09:05 | `invest_monitor_morning`（英語名・補助） | monitor_agent.py（ログ監視→Gmail） | - | - |
| **09:10** | `invest_morning_shutdown`（英語名・補助） | kabuStation終了（昼間アイドル中の常駐解放） | - | - |
| 〜昼間は kabuStation 停止〜 | | | | |
| **15:20** | `invest_afternoon_login`（英語名・補助） | 引け前に再ログイン（決済用の新セッション確保）。2026-06-06に15:10→15:20へ前倒し（金曜型Code:10016対策） | true | - |
| 15:25 | 投資戦略_引成決済 | kabu_order.py --execute --close（本番決済） | - | - |
| **15:32** | 投資戦略_約定照会 | fetch_fills.py → fills_YYYYMMDD.csv（実約定価格＋板情報） | **true** | - |
| 15:32 | `invest_monitor_evening`（英語名・補助） | monitor_agent.py（ログ監視→Gmail） | - | - |
| **15:35** | 投資戦略_損益レポート | report_agent.py → Gmail通知 + Excel更新 | **true** | - |
| **15:40** | 投資戦略_自動終了 | kabuStation終了（VBS非表示起動） | true | **true** |

**WakeToRun=true** 設定により PC スリープ中でも自動的に復帰してタスク実行される。

### 補助タスク（英語名）の役割と注意

正規の日本語名7タスクとは別に、英語名の補助タスクが5本ある（`invest_import_tasks.ps1` の管理対象外＝手動登録。変更には管理者権限が必要）。

- **`invest_morning_shutdown`（09:10）+ `invest_afternoon_login`（15:20）**: 寄付き後〜引け前の長いアイドル中に kabuStation のログインセッションが失効するのを避けるため、いったん終了して引け前に再ログインする設計。
  - **金曜型 Code:10016 対策（2026-06-06）**: 2026-06-05に再ログイン(15:10)後も15:25決済が `Code:10016`（取引ログインセッション失効）で全件失敗。①APIトークン（読み取り用）は再取得できても、②発注に必要な取引ログインセッションが15分弱で失効していたのが原因（木曜は同タイミングで成功＝常に致命的ではないがセッションが早く死ぬ日がある）。対策として再ログインを **15:10→15:20** に前倒しし、決済までの経過を約14分→約4分に短縮。`task_invest_afternoon_login.xml` 参照。
  - **残課題**: 15:20でも失効する可能性は残る。より確実にするには、(a) 15:10のパスキー処理がUIA確実方式でなくフォールバック（固定座標）に落ちる場合があるので確実方式に固定する、(b) kabu_order.py の決済で `Code:10016` 検知時に再ログイン→リトライ、(c) 決済失敗時に即時Gmail通知して当日中に手動返済できるようにする、等。
- **`invest_monitor_morning`（09:05）/ `invest_monitor_evening`（15:32）**: monitor_agent.py によるログ監視→Gmail通知。
- **`invest_login`（08:45）**: 自動ログインの1回目（08:47の日本語名タスクと二段構え）。

### 【重要】自動終了タスク（15:40）の堅牢化（2026-06-06）

15:40の `投資戦略_自動終了` が定刻に不発で、金曜にkabuStationが週末持ち越しになる事象が発生（土曜は翌朝のログインタスクが無く残骸が始末されないため表面化）。真因はスリープ中の復帰起動失敗＋取りこぼし時の追っかけ実行なし。対策として `task_invest_shutdown.xml` を以下に変更:

- `StartWhenAvailable`: false → **true**（定刻に動けなくても次回PC起床時に必ず実行）
- `DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries`: true → **false**（UPS誤認時の保険。本機はデスクトップ常時AC電源）
- `WakeToRun`: true 維持

**タスク変更には管理者権限が必要**（Claude Code/通常セッションからは `Access is denied 0x80070005`）。再登録は管理者PowerShellで:
```
powershell -ExecutionPolicy Bypass -File "C:\Users\tropi\invest_fix_shutdown_task.ps1"
```
テストタスク掃除も同様に管理者で: `invest_cleanup_test_tasks.ps1`

**タスク登録手順**（管理者権限不要 — Claude Codeから直接実行可能）:
1. `invest_sync_tasks.bat` を実行（ps1・task_names.txt・全XMLを `C:\Users\tropi\` にコピー）
2. `powershell -ExecutionPolicy Bypass -File C:\Users\tropi\invest_import_tasks.ps1` を実行

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
type log_fills.txt

# 約定照会（kabuStation起動中のみ）
run_daily.bat fills

# 損益レポート（メール送信 + Excel更新）
run_daily.bat report

# 損益計算（全日）
python -X utf8 calc_pnl.py

# 損益計算（特定日: 米国市場日付で指定）
python -X utf8 calc_pnl.py 20260421

# pnl_detail_history.csv を全期間 --save で再保存（修正反映用）
python -X utf8 calc_pnl.py --save

# ログトリム
python -X utf8 trim_logs.py
```

---

## タスクスケジューラの再登録

Claude Codeから直接実行可能（管理者権限不要、ただしSIDが一致していること）。

```bat
# 1. Gドライブ → C:\Users\tropi\ にコピー（ps1・task_names.txt・全XML）
invest_sync_tasks.bat

# 2. タスク登録
powershell -ExecutionPolicy Bypass -File C:\Users\tropi\invest_import_tasks.ps1
```

**XMLファイルについて**:
- 全XMLファイルは**UTF-8エンコーディング**（BOMなし）
- SIDは `S-1-5-21-2752900438-3444082329-101990108-1001`（tropi ユーザー）
- `invest_import_tasks.ps1` は UTF-8 で読み込み、`encoding=` 宣言を除去してから登録する
- 既存タスクで日本語名と英語名が重複した場合は英語名タスクを削除すること（`invest_shutdown` 15:30 が 投資戦略_自動終了 15:40 と競合した実績あり）

---

## 損益計算とスリッページ

### データソース優先順位

```
1. fills_YYYYMMDD.csv が存在する → 実約定価格 × 実約定数量で計算（備考: "実約定"）
2. 決済約定がない銘柄              → 「決済未了」として損益=Noneで記録
3. 新規約定がない銘柄              → 「発注失敗」として損益=Noneで記録
4. fills_YYYYMMDD.csv がない      → yfinance の始値/終値で理論計算（備考: 空欄）
```

### スリッページの基準価格

`fills_YYYYMMDD.csv` には kabuStation の `/board` から取得した東証始値（`MarketOpen`）・現在値（`MarketClose`=引け後≒終値）が記録される。

```
スリッページ = 実損益 - 理論損益（理論価格 × 実約定数量）

理論価格の優先順位:
1. kabuStation board の MarketOpen / MarketClose（最優先）
2. yfinance の Open / Close（フォールバック）
```

寄付き成行・引成は東証オークションで単一価格約定するため、kabuStation 価格基準でのスリッページは理論上ほぼ0になる。yfinance のデータノイズによる見かけのスリッページが除去された結果が記録される。

### 日付の対応関係

| ファイル | 命名規則 |
|----------|---------|
| signal_YYYYMMDD.csv | 米国市場日付（日本の前営業日） |
| fills_YYYYMMDD.csv  | 日本取引日（当日） |
| pnl_history.csv の「日付」列 | 米国市場日付 |
| trade_history.xlsx の「日付」列 | 米国市場日付 |

`calc_pnl.py` は yfinance で価格取得する際、シグナル日付 + 1営業日（日本取引日）を使用する。

### 重要な計算仕様

- 発注数量: `int(target_value / price / lot) * lot`（0口になる場合は発注しない）
- target_value: `PORTFOLIO_VALUE × abs(ポジション)` = 300,000 × 0.2 = 60,000円/銘柄
- 発注間隔: `time.sleep(0.5)` でAPI回数エラー(429)を防止
- 損益計算式: `pnl = np.sign(pos) × actual_qty × (close_fill - open_fill)`
  （旧バグ `pos × alloc × oc_ret` は2026-06-01 に修正済み、係数が約5倍ずれていた）

---

## 信用取引区分（MarginTradeType）

| 方向 | MarginTradeType | 内容 | 持ち越し時の動作 |
|------|----------------|------|--------------|
| **LONG** | 3（一般信用デイトレ） | 当日決済必須 | 翌朝強制決済 |
| **SHORT** | **1（制度信用）** | 6ヶ月以内 | **手動決済必要・貸株料発生** |

**SHORT を制度信用に変更した経緯（2026-06-03）:**

一般信用デイトレ（MarginTradeType=3）の売建在庫が頻繁に枯渇していた。

- 一般信用デイトレ売建は証券会社が自社で確保した限定的な株数を貸し出す仕組み
- 各銘柄ごとに「1日あたりの貸出可能数量」が決まっている
- 寄付き開始時点で他のトレーダーが先に売建すると当戦略では使用不可

エラー推移：
- 2026-06-01: Code:100263「数量が一般信用売建可能数量（在庫株数量）の上限を超えています」
- 2026-06-02: Code:4002013「パラメータ不正：MarginTradeType」（在庫0で銘柄全体がデイトレ売建停止状態）
- 2026-06-03: 同コードでSHORT 4銘柄全て失敗

修正後（2026-06-04）はSHORT発注がほぼ全成功。当日決済が成功すれば貸株料は発生しない。

**注意**: 決済失敗で持ち越した場合、LONG はデイトレ枠で翌朝自動決済されるが、**SHORT は制度信用なので手動決済が必要**。kabuStation の建玉画面で確認すること。

---

## Excel蓄積保存（trade_history.xlsx）

毎日 15:35 の損益レポート時に自動更新。

| シート | 内容 |
|-------|------|
| 日次サマリー | pnl_history.csv 相当（日付・損益・損益率・勝敗・ポジション数） |
| 銘柄別明細 | pnl_detail_history.csv 相当（日付・銘柄・方向・始値・終値・損益・スリッページ・備考） |

書式: ヘッダー青背景、損益/スリッページは±で緑/赤色分け、損益率は%表示、列幅自動調整、フリーズペイン設定。

依存: `openpyxl`（pip install 済み）

---

## 重要な既知事項・注意点

### 【重要】Claude Codeブランチ切り替えによるファイル上書きリスク
- Claude Codeは新セッションを開始するたびに新しいブランチを作成する
- ブランチ切り替え時にディスク上のファイルが古いバージョンに上書きされる可能性がある
- **対策**: スクリプト修正後は必ず `master` にマージして push すること
- 本番タスクが動く前日夜にブランチ操作を行った場合は、翌朝のログを必ず確認すること

### Gmail OAuth トークン
- `token_monitor.json` のリフレッシュトークンは Google OAuth アプリが「テスト」モードのため**約7日で失効**する
- 失効すると `invalid_grant: Bad Request` エラー → メール送信不可
- 対処: `credentials.json` を使って `InstalledAppFlow.run_local_server()` で再認証して `token_monitor.json` を上書き
- Google Cloud Console で OAuth アプリを「本番環境に公開」すれば失効しなくなる（要審査）

### シグナルファイルの命名規則
- ファイル名は**米国市場の日付**（日本の前営業日）で保存される
- 例: 日本 04-22 の取引シグナル → `signal_20260421.csv`（前日の米国 04-21 データ）
- `calc_pnl.py` に渡す日付引数も米国市場日付で指定すること
- `fills_YYYYMMDD.csv` のファイル名は**日本取引日**（当日日付）で保存される

### ログファイルの競合
- `kabu_autologin.py` / `monitor_agent.py` / `fetch_fills.py` は `logging.basicConfig(filename=...)` で内部的にファイルを開く
- `run_daily.bat` で `>> log_*.txt 2>&1` を**追加してはいけない**（同一ファイルを二重オープン → PermissionError）
- `daily_signal.py` / `kabu_order.py` は標準出力のみ → bat側の `>> log_*.txt 2>&1` でリダイレクト

### 管理者権限とGドライブ
- Windowsでは**管理者権限で実行するとGドライブ（Google Drive）がマップされない**
- タスクスケジューラのタスク本体はGドライブへアクセスしない（ラッパーbatがsetlocalでパスを解決）
- タスク登録（`invest_import_tasks.ps1`）はClaude Codeから直接実行可能（管理者権限不要）

### PowerShellのエンコーディング
- PowerShell 5.x は CP932 で読むため、PS1ファイルに日本語を含めると parse error になる
- PS1ファイルは**英語のみ**で記述すること

### Python環境
- Python実行ファイル: `C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- 主要パッケージ: pandas, numpy, requests, yfinance, openpyxl, pywinauto, google-auth, google-api-python-client
- `run_daily.bat` 冒頭で `SET PATH=...` を明示設定している（タスクスケジューラ環境ではPATHが不完全なため）

### kabuステーション® API
- REST: `http://localhost:18080/kabusapi/`
- WebSocket: `ws://localhost:18081/kabusapi/websocket`
- APIパスワード: `.env_windows` の `KABU_API_PASSWORD`
- ポートフォリオ金額: `.env_windows` の `PORTFOLIO_VALUE`（現在: **300,000円**、縮小運用中）
- 板情報エンドポイント: `/board/{symbol}@1`（1=東証）
- 注文照会エンドポイント: `/orders?product=2`（信用取引）

### 発注モード
- **現在のステータス: 本番稼働中**（2026-05-19より実発注開始）
- タスクスケジューラは `--execute` フラグ付きで自動実発注する
- `run_daily.bat dry` はデバッグ・動作確認専用（実際の注文は発生しない）

### kabuStation自動ログインフロー（2026-05 新仕様）
kabuStationのログイン仕様変更に伴い `kabu_autologin.py` を更新済み（2026-04-28〜05-22）。

**ログインステップ順序（重要）:**
1. Gmail API初期化
2. ログイン済み確認（スキップ判定）
3. kabuStation起動確認 → 起動中だがAPI使用不可（前回失敗の残骸）なら再起動してから起動
   - shutdown_kabustation() が False を返したら多重起動防止のため即 return False
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
PORTFOLIO_VALUE=300000
KABU_ACCOUNT_NUMBER=<口座番号（8桁）>
```

---

## セクターETF対応表（東証）

| ティッカー | セクター名       | 備考 |
|------------|-----------------|------|
| 1617.T     | 食品             | SHORT非対応（デイトレ売建不可） |
| 1618.T     | エネルギー資源   | |
| 1619.T     | 建設・資材       | |
| 1620.T     | 素材・化学       | SHORT非対応（デイトレ売建不可） |
| 1621.T     | 医薬品           | |
| 1622.T     | 自動車・輸送機   | |
| 1623.T     | 鉄鋼・非鉄       | SHORT非対応（デイトレ売建不可） |
| 1624.T     | 機械             | |
| 1625.T     | 電機・精密       | → 代替: 200A.T（日経半導体ETF） |
| 1626.T     | 情報通信・サービス | |
| 1627.T     | 電力・ガス       | |
| 1628.T     | 運輸・物流       | |
| 1629.T     | 商社・卸売       | → 代替: 8058.T（三菱商事） |
| 1630.T     | 小売             | |
| 1631.T     | 銀行             | |
| 1632.T     | 金融（除く銀行） | |
| 1633.T     | 不動産           | → 代替: 1343.T（東証REIT指数ETF） |

---

## 直近の主な修正履歴

| 日付 | 修正内容 |
|------|---------|
| 2026-05-29 | 決済時に実保有建玉を使用（get_positions） |
| 2026-05-29 | 引成FrontOrderType 13→16、LOT_SIZE 1343追加 |
| 2026-06-01 | 損益計算式バグ修正（`pos * alloc * oc_ret` → `np.sign(pos) * alloc * oc_ret`、約5倍ずれ） |
| 2026-06-01 | calc_order_qty の `max(qty, lot)` を削除（過大発注防止） |
| 2026-06-01 | API回数エラー回避のため `time.sleep(0.5)` 追加 |
| 2026-06-01 | fetch_fills.py 新規作成、実約定価格ベースのP&L計算 |
| 2026-06-01 | calc_pnl.py 日付オフセット修正（米国日付 + 1営業日 = 日本取引日） |
| 2026-06-01 | 自動終了タスクを 15:30 → 15:40 に変更（約定照会のため） |
| 2026-06-02 | report_agent.py f-string SyntaxError修正、日次通知メール追加 |
| 2026-06-02 | 旧英語名タスク削除（invest_shutdown 15:30 と新タスク 15:40 の競合解消） |
| 2026-06-03 | SHORT発注を制度信用（MarginTradeType=1）に変更（デイトレ在庫枯渇対策） |
| 2026-06-03 | Gmail OAuth トークン再認証 |
| 2026-06-04 | SHORT返済も制度信用に統一（建玉が選択されていませんエラー対策） |
| 2026-06-04 | task_invest_fills/report の WakeToRun=true（PCスリープ中も実行） |
| 2026-06-04 | shutdown_kabustation() 戻り値チェック追加（多重起動防止） |
| 2026-06-04 | スリッページ判定 NaN ガード追加 |
| 2026-06-04 | fetch_fills.py に板情報（MarketOpen/MarketClose）取得追加 |
| 2026-06-04 | スリッページ計算を kabuStation 価格優先・yfinance フォールバックに変更 |
| 2026-06-04 | trade_history.xlsx（2シート構成、書式付き）の蓄積保存追加 |
