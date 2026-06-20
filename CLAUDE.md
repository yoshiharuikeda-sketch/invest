# 自動売買システム — Claude Code プロジェクト設定

## プロジェクト概要

**戦略**: 日米業種リードラグ投資戦略  
前日の米国セクターETF（SPDR XL系）のリターンから、当日の日本セクターETF（東証1617〜1633）のシグナルを生成してトレード。

**証券会社**: 三菱UFJ eスマート証券（旧auカブコム）  
**API**: kabuステーション® REST API (localhost:18080)  
**運用モード**: 🧪 **DRY検証中（2026-06-08〜 約1か月）** — 実発注を止め、kabuステーション価格ベースの仮想損益を `paper_trade_history.xlsx` に蓄積して戦略を検証中。kabuステーションの起動・ログイン・板取得は通常どおり実施。検証終了後は下記「DRY検証モードの戻し方」で本番に復帰する。  
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
├── invest_setup_tasks.ps1    # 【唯一の正本】9タスクを全削除→再登録（英語のみ・要admin・C:から実行）
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
| 08:45 | `invest_login_am` | kabuStation起動 + 2FA + API認証 | true | - |
| 08:50 | `invest_signal` | daily_signal.py → signal_YYYYMMDD.csv | - | - |
| 09:00 | `invest_open` | kabu_order.py（発注。DRY中は dry_open） | - | - |
| **09:10** | `invest_shutdown_am` | kabuStation終了（昼間アイドル中の常駐解放） | true | **true** |
| **09:12** | `invest_sleep_am` | **PCをスリープ（昼間省電力）** SetSuspendState。15:20のlogin_pmがWakeToRunで起こす | - | - |
| 〜昼間は PC スリープ〜 | | | | |
| **15:20** | `invest_login_pm` | 引け前に再ログイン（決済用の新セッション確保）+ **キープアウェイク常駐(〜15:42)** | true | - |
| 15:25 | `invest_close` | kabu_order.py --close（決済。DRY中は dry_close） | true | - |
| **15:32** | `invest_fills` | fetch_fills.py → fills_YYYYMMDD.csv（実約定価格＋板情報） | true | - |
| **15:35** | `invest_report` | report_agent.py/paper_trade.py → Gmail通知 + Excel更新 | true | - |
| **15:40** | `invest_shutdown_pm` | kabuStation終了 | true | **true** |
| **15:45** | `invest_sleep_pm` | **PCをスリープ（夜間省電力）** SetSuspendState。翌朝08:45のlogin_amがWakeToRunで起こす | - | - |

**タスク構成は 2026-06-19 に簡素化**（旧：日本語名7＋英語補助5＋自動スリープ1の計13本）。トレード系9本は
**bat直接起動**（隠しVBS全廃＝Smart App Control/MOTWの `Code:800711CE` ブロックを根絶）、命名は `invest_*` に統一、
平日(月〜金)トリガー。**2026-06-20 に省電力スリープ2本（`invest_sleep_am` 09:12 / `invest_sleep_pm` 15:45）を追加し計11本**。
**唯一の正本は `invest_setup_tasks.ps1`**（下記「タスクスケジューラの再登録」）。
旧基盤（task_invest_*.xml / task_names.txt / invest_import_tasks.* / invest_sync_tasks.bat / *_hidden.vbs /
各種 invest_fix_*.ps1）は全削除した。

**省電力スリープの設計（2026-06-20）**: 取引の谷間でPCを寝かせて省電力化。`SetSuspendState 0,1,0`（第3引数0＝
ウェイクイベント有効なのでWakeToRunで起きられる）を使う。①`invest_sleep_am`(09:12)＝午前終了(09:10)後に寝て
昼間休止→15:20 login_pm が起こす。②`invest_sleep_pm`(15:45)＝午後終了(15:40)後・キープアウェイク解除(15:42)後に
寝て夜間休止→翌朝08:45 login_am が起こす。**注意**: 強制スリープなので、その時刻にPCを使用中でも寝る（旧
「投資戦略_自動スリープ」と同じ仕組みだが、時刻が取引と衝突しない09:12/15:45に置いてある点が異なる）。なお
削除した旧タスクは15:35＝決済中に寝てしまうのが問題だった。

### 【最重要・真因】午後の持ち越し問題＝「投資戦略_自動スリープ」タスク（2026-06-19 削除済み）

6-17〜6-19、午後にkabuStationが終了されず持ち越す事象が続いた。**3日連続で正確に 15:35:00 にスリープ**して
いたためイベントログ＋全タスク走査で真因を特定：**ユーザが2026-04-06に作った未文書化タスク
「投資戦略_自動スリープ」が平日15:35:00に `rundll32 powrprof.dll,SetSuspendState` でPCを強制スリープ**して
いた（Event42の Sleep Reason=Application API）。これは下記キープアウェイク/UNATTENDSLPを**全て無視して寝る**ため、
それらの対策が効かなかった。**このタスクを削除して根治**（6-06の金曜持ち越しも同根と推定）。

#### 併用している多層防御（副次・スリープ全般への保険）

真因は上記タスクだが、アイドル/無人スリープへの保険として以下も残している：

- **キープアウェイク**（`kabu_autologin.py` の `_keep_awake_until`）：午後ログイン後、15時台(minute<40)のログインは
  自動で **15:42までスリープ抑制**（`ES_CONTINUOUS|ES_SYSTEM_REQUIRED` を定期再アサート）。`--keep-awake-until HH:MM` で明示も可。
  このため `invest_login_pm` は15:20〜15:42常駐する（ExecutionTimeLimit=60分に設定済み）。
- **UNATTENDSLP**（端末の電源設定・git管理外）：無人スリープタイムアウト(AC)を既定120秒→**1800秒**に延長済み。
  ```
  powercfg -setacvalueindex SCHEME_CURRENT SUB_SLEEP 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0 1800
  powercfg -setactive SCHEME_CURRENT
  ```
  Windows Update等でリセットされ得るので、午後の不調再発時はまず `powercfg /lastwake` と本値を確認。

#### Code:10016（取引セッション失効）対策（2026-06-06、現行も有効）

昼アイドルで取引ログインセッションが失効する対策として、午前で一旦終了→**15:20に再ログイン**して決済までを短縮する設計。
加えて `kabu_order.py` の決済が `Code:10016` を返したら `kabu_autologin.do_login(force=True)`→トークン再取得→未決済分のみ
再発注（自動リカバリ）。失敗が残れば `token_monitor.json` で自分宛に即時Gmailアラート（制度信用SHORTは手動返済要・`check_positions.py`で確認）。
パスキー処理は実績ある高速版＋「ウィンドウ消失=進行済み」ガード（最終判定は `do_login` のAPI確認）。

---

## タスクスケジューラの再登録（唯一の手順）

9タスクの定義は **`invest_setup_tasks.ps1`（英語のみ）に集約**。これを実行すると「既存invest関連タスクを全削除→9本を再登録」する（`-Force`で冪等）。

**注意点:**
- **管理者権限（UAC昇格）が必要**（タスク登録は `Access is denied` になるため）。
- **Gドライブはadminでマップされない**が、本スクリプトは bat の「パス文字列」を登録するだけでG:にアクセスしないため、**C:にコピーして実行**する。
- **PS1に日本語を書かない**（PowerShell 5.1がCP932で誤読しparse error。コメントも英語のみ）。日本語タスク名の削除は `[char]0x6295`（投）でマッチして回避している。

```powershell
# 1. C: にコピー（Gはadminで見えないため）
Copy-Item "G:\My Drive\Claude Code\Invest\invest_setup_tasks.ps1" "C:\Users\tropi\invest_setup_tasks.ps1" -Force
# 2. 昇格実行（UACで「はい」）。結果は C:\Users\tropi\invest_setup_tasks.log
powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','C:\Users\tropi\invest_setup_tasks.ps1'"
```

実行コンテキストは `InteractiveToken`＋SID `S-1-5-21-2752900438-3444082329-101990108-1001`（GUI自動化のため対話セッションで実行）。

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

→ 上の「日次スケジュール」内「タスクスケジューラの再登録（唯一の手順）」を参照（`invest_setup_tasks.ps1` を C:にコピーしてUAC昇格実行）。旧 XML/import/sync 方式は廃止。

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
- タスク登録（`invest_setup_tasks.ps1`）は**管理者権限（UAC昇格）が必要**。Gはadminで見えないため**C:にコピーして実行**する（登録するのはbatのパス文字列のみでG:アクセスは不要）

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
- **現在のステータス: 🧪 DRY検証中（2026-06-08〜 約1か月）**
- 発注・決済タスクは DRY RUN（実注文なし）。kabuステーション価格ベースで仮想損益を記録。
- 検証終了後は本番（実発注）へ戻す（下記参照）。
- `run_daily.bat dry` はデバッグ・動作確認専用（実際の注文は発生しない）

### DRY検証モード（2026-06-08〜）の構成と戻し方

**仕組み**（タスク定義は変えず、ラッパーbatの呼び出し先のみ変更。タスク再登録不要）:

| ラッパーbat | DRY中の呼び出し | 本番時の呼び出し |
|-------------|----------------|-----------------|
| `invest_open.bat` | `run_daily.bat dry_open` | `run_daily.bat open` |
| `invest_close.bat` | `run_daily.bat dry_close` | `run_daily.bat close` |
| `invest_report.bat` | `run_daily.bat paper` | `run_daily.bat report` |

- **仮想資金は100万円**（検証期間の取引数量算出用）。`.env_windows` の `PORTFOLIO_VALUE=30万`
  とは**独立**に、DRY経路だけ100万に固定（本番復帰時に誤って大きい金額で実発注しない安全分離）。
  - `run_daily.bat` の dry_open/dry_close は `--value 1000000`
  - `paper_trade.py` の `VERIFY_CAPITAL = 1_000_000`
- `dry_open` / `dry_close`: `kabu_order.py`（`--execute` なし）→ 実注文は出ない。ログは `log_order.txt`。
- `paper`: `paper_trade.py` → シグナルの各銘柄について kabuステーション `/board` の
  `OpeningPrice`(始値) / `CurrentPrice`(終値) を取得し、`sign(ポジション)×数量×(終値−始値)` で
  仮想損益を計算（数量は仮想資金100万円ベース）。`paper_pnl_history.csv` /
  `paper_pnl_detail_history.csv` に蓄積し、**`paper_trade_history.xlsx`（紫ヘッダ＝仮想、2シート）**
  に1ファイルでまとめる。Gmail通知あり。SHORTスキップ条件は本番(`kabu_order.py`)と同一。
  当日価格が未確定の銘柄は「価格取得不可」。
- ログイン(08:47)・シグナル(08:50)・約定照会(15:32)・終了(15:40) は通常どおり（fetch_fills は
  DRYでは約定0件で空振りするが無害）。

**本番（実発注）に戻す手順**（batを元に戻すだけ。タスク再登録不要）:
1. `invest_open.bat` の `dry_open` → `open`
2. `invest_close.bat` の `dry_close` → `close`
3. `invest_report.bat` の `paper` → `report`
4. `git add -A && git commit && git push`（masterへ）

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
| 2026-06-06 | 自動終了タスク堅牢化（StartWhenAvailable=true、バッテリー制限解除） |
| 2026-06-06 | 補助タスク5本（英語名）をCLAUDE.mdに正式記載 |
| 2026-06-06 | 金曜型Code:10016対策①: invest_afternoon_login 15:10→15:20へ前倒し |
| 2026-06-06 | 金曜型Code:10016対策②(a): パスキー処理をUIA Invoke複数回リトライ方式に変更 |
| 2026-06-06 | 金曜型Code:10016対策②(b): 決済でCode:10016検知→force再ログイン→未決済分リトライ |
| 2026-06-06 | 金曜型Code:10016対策②(c): 発注失敗時に即時Gmailアラート（手動返済案内） |
| 2026-06-06 | check_positions.py（建玉確認・読み取り専用）、テストタスク掃除スクリプト追加 |
| 2026-06-06 | close_all_positions.py（残建玉を実保有Side基準で返済・ExecutionDayで当日新規除外）追加 |
| 2026-06-06 | 月曜寄付き前(08:55)の持ち越し建玉 自動返済タスク（単発）を用意 |
| 2026-06-06 | kabuStation終了の高速化（SHUTDOWN_WAIT_SEC 15→5秒）＋終了確認ダイアログ対応 |
| 2026-06-08 | DRY検証モード開始（約1か月）。発注/決済をDRY化、paper_trade.pyで仮想損益をExcel蓄積 |
| 2026-06-08 | _send_gmail のscope修正（readonly除去→sendのみ、宛先固定）。invalid_scope解消 |
| 2026-06-08 | DRY初日に仮想損益が0になる不具合修正（古いトークンで板/board が401）。2FA待ち30→90秒 |
| 2026-06-08 | get_token堅牢化：_authed_request で401検知→force_refresh自動リトライ（本番send_order/板も自己回復） |
| 2026-06-10 | 午後ログイン不安定対策：口座番号送信Enterの取りこぼし(CEFフォーカス外れ)対策。2FA未着なら最前面化してEnter再送→再待機を最大3回（_resend_login_enter）。決済/照会/レポートのcmd窓を非表示VBS起動化 |
| 2026-06-08 | universe を仕様どおり17銘柄に復帰：daily_signalに1625.T（電機・精密）追加（v3シクリカルにも追加）。執行は売建可能な200A.Tに置換（kabu_order JP_TICKER_TO_CODE）。cache_prior.parquet再構築 |
| 2026-06-08 | v2（国スプレッド）を仕様どおり 1/√N → 1/N（米国1/11・日本1/17）に修正。daily_signal.py / backtest.py 両方を統一（仕様完全準拠） |
| 2026-06-20 | 省電力スリープ2本を追加（計11タスク）：`invest_sleep_am`(09:12, 午前終了後→昼間休止)・`invest_sleep_pm`(15:45, 午後終了後→夜間休止)。SetSuspendState 0,1,0（ウェイクタイマー有効）でWakeToRunログインが起こす。取引と衝突しない時刻に配置。invest_setup_tasks.ps1に統合 |
| 2026-06-19 | 【午後持ち越しの真因特定＆根治】未文書化タスク「投資戦略_自動スリープ」(平日15:35:00 SetSuspendStateでPC強制スリープ)が3日連続15:35:00スリープの正体と判明→削除。あわせて**タスク構成を13本→9本に簡素化**（全bat直起動・隠しVBS全廃・命名invest_*統一・平日トリガー）。唯一の正本 `invest_setup_tasks.ps1` を新設し、旧基盤(XML/task_names/import/sync/hidden vbs/fix系)を全削除。キープアウェイク(6-17)・UNATTENDSLP(6-18)は副次の保険として残置 |
| 2026-06-18 | 午後スリープ対策②：UNATTENDSLP(無人スリープ既定120秒)をAC1800秒へ延長（端末側電源設定）。※真因は翌6-19に判明（自動スリープタスク）で、本対策は副次の保険 |
| 2026-06-17 | 午後の終了保証：WakeToRunが実機で不発（イベントログで15:35スリープ→15:40終了不発→手動復帰まで放置を確認）。`kabu_autologin.py` に `_keep_awake_until` を追加し、15時台ログインは自動で15:42までスリープ抑制を維持（`--keep-awake-until HH:MM` 手動指定も可）。タスク無変更・管理者不要 |
| 2026-06-11 | 【6-10 cmd窓非表示化の撤回】決済/照会/レポートのwscript+非表示VBS起動が、Smart App Control(Enforced)＋Google Drive同期のMOTW付与で `Code:800711CE` ブロックされ全不発。タスクXML 3本を**bat直接起動に戻し**、`invest_{close,fills,report}_hidden.vbs` と `invest_fix_hidden_tasks.ps1` を削除。cmd窓は再表示されるが確実性を優先。再登録は管理者権限要（昨日adminで登録された影響）→ UAC昇格でinvest_import_tasks.ps1実行。※GドライブのVBSにMOTWが付くと.vbs実行が弾かれる点に注意（必要時は `Get-ChildItem *.vbs \| Unblock-File`） |
