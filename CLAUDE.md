# 閾ｪ蜍募｣ｲ雋ｷ繧ｷ繧ｹ繝・Β 窶・Claude Code 繝励Ο繧ｸ繧ｧ繧ｯ繝郁ｨｭ螳・
## 繝励Ο繧ｸ繧ｧ繧ｯ繝域ｦりｦ・
**謌ｦ逡･**: 譌･邀ｳ讌ｭ遞ｮ繝ｪ繝ｼ繝峨Λ繧ｰ謚戊ｳ・姶逡･  
蜑肴律縺ｮ邀ｳ蝗ｽ繧ｻ繧ｯ繧ｿ繝ｼETF・・PDR XL邉ｻ・峨・繝ｪ繧ｿ繝ｼ繝ｳ縺九ｉ縲∝ｽ捺律縺ｮ譌･譛ｬ繧ｻ繧ｯ繧ｿ繝ｼETF・域擲險ｼ1617縲・633・峨・繧ｷ繧ｰ繝翫Ν繧堤函謌舌＠縺ｦ繝医Ξ繝ｼ繝峨・
**險ｼ蛻ｸ莨夂､ｾ**: 荳芽廠UFJ e繧ｹ繝槭・繝郁ｨｼ蛻ｸ・域立au繧ｫ繝悶さ繝・・ 
**API**: kabu繧ｹ繝・・繧ｷ繝ｧ繝ｳﾂｮ REST API (localhost:18080)  
**驕狗畑繝｢繝ｼ繝・*: 迴ｾ蝨ｨ DRY RUN・・--execute` 縺ｪ縺暦ｼ・竊・譚･騾ｱ莉･髯・譛ｬ逡ｪ莠亥ｮ・
---

## 繝・ぅ繝ｬ繧ｯ繝医Μ讒区・

```
G:\My Drive\Claude Code\Invest\
笏懌楳笏 CLAUDE.md              # 縺薙・繝輔ぃ繧､繝ｫ
笏懌楳笏 .env_windows           # 迺ｰ蠅・､画焚 (KABU_API_PASSWORD, PORTFOLIO_VALUE)
笏懌楳笏 config.py              # 繝代せ險ｭ螳夲ｼ・ac/Windows荳｡蟇ｾ蠢懶ｼ・笏・笏懌楳笏 daily_signal.py        # 繧ｷ繧ｰ繝翫Ν險育ｮ暦ｼ育ｱｳ蝗ｽ蜑肴律 竊・譌･譛ｬ蠖捺律・・笏懌楳笏 kabu_order.py          # 逋ｺ豕ｨ繝｢繧ｸ繝･繝ｼ繝ｫ・・RY RUN / 譛ｬ逡ｪ・・笏懌楳笏 kabu_autologin.py      # kabuStation閾ｪ蜍輔Ο繧ｰ繧､繝ｳ・・UI閾ｪ蜍募喧・・笏懌楳笏 monitor_agent.py       # 繝ｭ繧ｰ逶｣隕・竊・Gmail騾夂衍
笏・笏懌楳笏 run_daily.bat          # 荳ｭ螟ｮ繝・ぅ繧ｹ繝代ャ繝√Ε (login/signal/open/close/shutdown/monitor)
笏懌楳笏 invest_login.bat       # 繧ｿ繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ逕ｨ繝ｩ繝・ヱ繝ｼ
笏懌楳笏 invest_signal.bat
笏懌楳笏 invest_open.bat
笏懌楳笏 invest_close.bat
笏懌楳笏 invest_shutdown.bat
笏懌楳笏 invest_monitor.bat
笏・笏懌楳笏 task_invest_login.xml  # 繧ｿ繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ XML螳夂ｾｩ・・譛ｬ・・笏懌楳笏 task_invest_signal.xml
笏懌楳笏 task_invest_open.xml
笏懌楳笏 task_invest_close.xml
笏懌楳笏 task_invest_shutdown.xml
笏・笏懌楳笏 invest_import_tasks.bat   # 繧ｿ繧ｹ繧ｯ蜀咲匳骭ｲ・郁ｦ∫ｮ｡逅・・ｨｩ髯撰ｼ・笏懌楳笏 invest_import_tasks.ps1
笏・笏懌楳笏 log_autologin.txt      # kabu_autologin.py / monitor_agent.py 縺ｮ繝ｭ繧ｰ
笏懌楳笏 log_signal.txt         # daily_signal.py 縺ｮ繝ｭ繧ｰ
笏披楳笏 log_order.txt          # kabu_order.py 縺ｮ繝ｭ繧ｰ
```

---

## 譌･谺｡繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｫ・医ち繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ・・
| 譎ょ綾  | 繧ｿ繧ｹ繧ｯ蜷搾ｼ・ask Scheduler・・| 蜃ｦ逅・・螳ｹ                     |
|-------|---------------------------|------------------------------|
| 08:45 | invest_login              | kabuStation襍ｷ蜍・+ 2FA + API隱崎ｨｼ・・BS髱櫁｡ｨ遉ｺ襍ｷ蜍包ｼ・|
| 08:50 | invest_signal             | daily_signal.py 竊・signal_YYYYMMDD.csv |
| 09:00 | invest_open               | kabu_order.py・・RY RUN 逋ｺ豕ｨ・・|
| 09:05 | 窶費ｼ域焔蜍・or 蛻･騾費ｼ・         | monitor_agent.py 竊・Gmail・域悃騾夂衍・・|
| 09:10 | invest_morning_shutdown   | kabuStation邨ゆｺ・竊・PC閾ｪ辟ｶ繧ｹ繝ｪ繝ｼ繝励∈ |
| 縲懊せ繝ｪ繝ｼ繝励・| | |
| 15:10 | invest_afternoon_login    | kabuStation蜀崎ｵｷ蜍・+ 2FA + API隱崎ｨｼ |
| 15:25 | invest_close              | kabu_order.py --close・・RY RUN 豎ｺ貂茨ｼ・|
| 15:30 | invest_shutdown           | kabuStation邨ゆｺ・ｼ・BS髱櫁｡ｨ遉ｺ襍ｷ蜍包ｼ・|
| 15:32 | 窶費ｼ域焔蜍・or 蛻･騾費ｼ・         | monitor_agent.py 竊・Gmail・亥､暮夂衍・・|

**繧ｿ繧ｹ繧ｯ逋ｻ骭ｲ繝輔ぃ繧､繝ｫ**: C:\Users\tropi\invest_import_tasks.ps1・育ｮ｡逅・・ｨｩ髯舌〒螳溯｡鯉ｼ・
---

## 謇句虚螳溯｡後さ繝槭Φ繝・
```bat
# 繧ｷ繧ｰ繝翫Ν遒ｺ隱・run_daily.bat signal

# DRY RUN 逋ｺ豕ｨ繝・せ繝・run_daily.bat dry

# 譛ｬ逡ｪ逋ｺ豕ｨ・郁ｦ・--execute 繝輔Λ繧ｰ螟画峩・・run_daily.bat open

# 繝ｭ繧ｰ遒ｺ隱・type log_autologin.txt
type log_signal.txt
type log_order.txt

# 莉頑律縺ｮ繧ｷ繧ｰ繝翫ΝCSV・遺ｻ繝輔ぃ繧､繝ｫ蜷阪・邀ｳ蝗ｽ蟶ょｴ縺ｮ譌･莉・= 譌･譛ｬ縺ｮ蜑榊霧讌ｭ譌･・・# 萓・ 譌･譛ｬ04-22縺ｮ蜿門ｼ・竊・signal_20260421.csv・亥燕譌･縺ｮ邀ｳ蝗ｽ04-21繝・・繧ｿ・・type signal_YYYYMMDD.csv

# 謳咲寢險育ｮ暦ｼ亥・譌･・・python -X utf8 calc_pnl.py

# 謳咲寢險育ｮ暦ｼ育音螳壽律: 邀ｳ蝗ｽ蟶ょｴ譌･莉倥〒謖・ｮ夲ｼ・python -X utf8 calc_pnl.py 20260421
```

---

## 繧ｿ繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ縺ｮ蜀咲匳骭ｲ

**蠢・★邂｡逅・・ｨｩ髯舌〒螳溯｡後☆繧九％縺ｨ**・育ｮ｡逅・・ｨｩ髯舌↑縺励〒縺ｯ Set-ScheduledTask 縺悟､ｱ謨励☆繧具ｼ・
```bat
# 邂｡逅・・さ繝槭Φ繝峨・繝ｭ繝ｳ繝励ヨ縺ｧ
invest_import_tasks.bat
```

XML菫ｮ豁｣譎ゅ・豕ｨ諢・ XML繝輔ぃ繧､繝ｫ縺ｯUTF-16繧ｨ繝ｳ繧ｳ繝ｼ繝・ぅ繝ｳ繧ｰ縲１owerShell縺ｧ邱ｨ髮・☆繧句ｴ蜷医・  
`[System.IO.File]::ReadAllText(..., [Text.Encoding]::Unicode)` 繧剃ｽｿ縺・％縺ｨ縲・
---

## 驥崎ｦ√↑譌｢遏･莠矩・・豕ｨ諢冗せ

### 繧ｷ繧ｰ繝翫Ν繝輔ぃ繧､繝ｫ縺ｮ蜻ｽ蜷崎ｦ丞援
- 繝輔ぃ繧､繝ｫ蜷阪・**邀ｳ蝗ｽ蟶ょｴ縺ｮ譌･莉・*・域律譛ｬ縺ｮ蜑榊霧讌ｭ譌･・峨〒菫晏ｭ倥＆繧後ｋ
- 萓・ 譌･譛ｬ 04-22 縺ｮ蜿門ｼ輔す繧ｰ繝翫Ν 竊・`signal_20260421.csv`・亥燕譌･縺ｮ邀ｳ蝗ｽ 04-21 繝・・繧ｿ・・- `calc_pnl.py` 縺ｫ貂｡縺呎律莉伜ｼ墓焚繧らｱｳ蝗ｽ蟶ょｴ譌･莉倥〒謖・ｮ壹☆繧九％縺ｨ
- 縲御ｻ頑律縺ｮ繧ｷ繧ｰ繝翫Ν縺後↑縺・阪→諤昴▲縺溘ｉ蜑榊霧讌ｭ譌･縺ｮ繝輔ぃ繧､繝ｫ蜷阪ｒ遒ｺ隱阪☆繧九％縺ｨ

### 繝ｭ繧ｰ繝輔ぃ繧､繝ｫ縺ｮ遶ｶ蜷・- `kabu_autologin.py` / `monitor_agent.py` 縺ｯ `logging.basicConfig(filename=...)` 縺ｧ蜀・Κ逧・↓繝輔ぃ繧､繝ｫ繧帝幕縺・- `run_daily.bat` 縺ｧ `>> log_autologin.txt 2>&1` 繧・*霑ｽ蜉縺励※縺ｯ縺・￠縺ｪ縺・*・亥酔荳繝輔ぃ繧､繝ｫ繧剃ｺ碁㍾繧ｪ繝ｼ繝励Φ 竊・PermissionError・・- `daily_signal.py` / `kabu_order.py` 縺ｯ讓呎ｺ門・蜉帙・縺ｿ 竊・bat蛛ｴ縺ｮ `>> log_*.txt 2>&1` 縺ｧ繝ｪ繝繧､繝ｬ繧ｯ繝・
### 邂｡逅・・ｨｩ髯舌→G繝峨Λ繧､繝・- Windows縺ｧ縺ｯ**邂｡逅・・ｨｩ髯舌〒螳溯｡後☆繧九→G繝峨Λ繧､繝厄ｼ・oogle Drive・峨′繝槭ャ繝励＆繧後↑縺・*
- 繧ｿ繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ縺ｮ繧ｿ繧ｹ繧ｯ譛ｬ菴薙・G繝峨Λ繧､繝悶∈繧｢繧ｯ繧ｻ繧ｹ縺励↑縺・ｼ医Λ繝・ヱ繝ｼbat縺茎etlocal縺ｧ繝代せ繧定ｧ｣豎ｺ・・- 邂｡逅・・さ繝槭Φ繝峨・繝ｭ繝ｳ繝励ヨ縺九ｉG繝峨Λ繧､繝悶・繝輔ぃ繧､繝ｫ繧堤峩謗･螳溯｡後☆繧句ｴ蜷医・ `net use G: \\...` 縺悟ｿ・ｦ√↑蝣ｴ蜷医≠繧・
### PowerShell縺ｮ繧ｨ繝ｳ繧ｳ繝ｼ繝・ぅ繝ｳ繧ｰ
- PowerShell 5.x 縺ｯ CP932 縺ｧ隱ｭ繧縺溘ａ縲￣S1繝輔ぃ繧､繝ｫ縺ｫ譌･譛ｬ隱槭ｒ蜷ｫ繧√ｋ縺ｨ parse error 縺ｫ縺ｪ繧・- PS1繝輔ぃ繧､繝ｫ縺ｯ**闍ｱ隱槭・縺ｿ**縺ｧ險倩ｿｰ縺吶ｋ縺薙→

### Python迺ｰ蠅・- Python螳溯｡後ヵ繧｡繧､繝ｫ: `C:\Users\tropi\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- `run_daily.bat` 蜀帝ｭ縺ｧ `SET PATH=...` 繧呈・遉ｺ險ｭ螳壹＠縺ｦ縺・ｋ・医ち繧ｹ繧ｯ繧ｹ繧ｱ繧ｸ繝･繝ｼ繝ｩ迺ｰ蠅・〒縺ｯPATH縺御ｸ榊ｮ悟・縺ｪ縺溘ａ・・
### kabu繧ｹ繝・・繧ｷ繝ｧ繝ｳﾂｮ API
- REST: `http://localhost:18080/kabusapi/`
- WebSocket: `ws://localhost:18081/kabusapi/websocket`
- API繝代せ繝ｯ繝ｼ繝・ `.env_windows` 縺ｮ `KABU_API_PASSWORD`
- 繝昴・繝医ヵ繧ｩ繝ｪ繧ｪ驥鷹｡・ `.env_windows` 縺ｮ `PORTFOLIO_VALUE`・育樟蝨ｨ: 990,000蜀・ｼ・
### 逋ｺ豕ｨ繝｢繝ｼ繝・- **繝・ヵ繧ｩ繝ｫ繝茨ｼ・RY RUN・・*: `run_daily.bat open/close` 竊・繧ｷ繝溘Η繝ｬ繝ｼ繧ｷ繝ｧ繝ｳ縺ｮ縺ｿ縲∝ｮ滄圀縺ｮ豕ｨ譁・↑縺・- **譛ｬ逡ｪ**: `kabu_order.py` 縺ｫ `--execute` 繝輔Λ繧ｰ繧定ｿｽ蜉縺励※蛻昴ａ縺ｦ螳溽匱豕ｨ
- 迴ｾ蝨ｨ縺ｮ繧ｹ繝・・繧ｿ繧ｹ: DRY RUN騾ｱ・・026-04-14縲懶ｼ俄・ 譚･騾ｱ莉･髯肴悽逡ｪ讀懆ｨ・
---

## 迺ｰ蠅・､画焚・・env_windows・・
```
KABU_API_PASSWORD=<API繝代せ繝ｯ繝ｼ繝・
PORTFOLIO_VALUE=990000
```

---

## 繧ｻ繧ｯ繧ｿ繝ｼETF蟇ｾ蠢懆｡ｨ・域擲險ｼ・・
| 繝・ぅ繝・き繝ｼ | 繧ｻ繧ｯ繧ｿ繝ｼ蜷・      |
|------------|------------------|
| 1617.T     | 鬟溷刀             |
| 1618.T     | 繧ｨ繝阪Ν繧ｮ繝ｼ雉・ｺ・  |
| 1619.T     | 蟒ｺ險ｭ繝ｻ雉・攝       |
| 1620.T     | 邏譚舌・蛹門ｭｦ       |
| 1621.T     | 蛹ｻ阮ｬ蜩・          |
| 1622.T     | 閾ｪ蜍戊ｻ翫・霈ｸ騾∵ｩ・  |
| 1623.T     | 驩・蕎繝ｻ髱樣延       |
| 1624.T     | 讖滓｢ｰ             |
| 1625.T     | 髮ｻ讖溘・邊ｾ蟇・      |
| 1626.T     | 諠・ｱ騾壻ｿ｡繝ｻ繧ｵ繝ｼ繝薙せ |
| 1627.T     | 髮ｻ蜉帙・繧ｬ繧ｹ       |
| 1628.T     | 驕玖ｼｸ繝ｻ迚ｩ豬・      |
| 1629.T     | 蝠・､ｾ繝ｻ蜊ｸ螢ｲ       |
| 1630.T     | 蟆丞｣ｲ             |
| 1631.T     | 驫陦・            |
| 1632.T     | 驥題檮・磯勁縺城橿陦鯉ｼ・|
| 1633.T     | 荳榊虚逕｣           |

