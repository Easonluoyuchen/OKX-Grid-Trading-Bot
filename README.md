# OKX-Grid-Trading-Bot
This project is a grid trading bot for OKX (perpetual swaps), built with Python + CCXT + Streamlit. It implements the traditional grid strategy

✨ Features
Grid Strategy
At startup: place buy orders below the current price, sell orders above.
Supports init_position:
When enabled: open a market position at startup, with size equal to the sum of all sell orders.
Ensures consistency between top sell orders and the base position.
After fills:
If a buy order is filled, place a new sell order one grid above.
If a sell order is filled, place a new buy order one grid below.
First fill after init_position is ignored to maintain consistency.
PnL Accounting
FIFO-based realized/unrealized PnL calculation.
Configurable fee rate.
State & Control
JSON state (grid_state.json) records price, orders, positions, and PnL.
Command channel (grid_commands.jsonl) supports cancel, restore, and manual place operations.
Atomic file writes for safe state persistence.
Monitoring UI
Built with Streamlit.
KPIs: price, inventory, realized/unrealized PnL.
Price chart with active grid levels.
Equity curve with selectable time frame (raw / 1h / 4h / 1d).
Control panel: cancel all, restore level, manual buy/sell.
Auto-refresh every 10s (configurable).
⚙️ Installation
git clone https://github.com/yourname/okx-grid-bot.git
cd okx-grid-bot
pip install -r requirements.txt
🔑 API Keys
Create a .env file in project root:
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASS=your_passphrase
OKX_USE_TESTNET=true   # true = testnet, false = live
📝 Configuration
Edit configs/config.local.yml:
exchange:
  symbol: BTC-USDT-SWAP
  default_type: swap

grid:
  lower_price: 10000
  upper_price: 12000
  levels: 20
  order_size: 20
  init_position: true   # enable or disable initial position

runtime:
  state_path: grid_state.json
  commands_path: grid_commands.jsonl
  fee_rate: 0.0005
  sleep_sec: 0.5
  rest_poll_sec: 2
  band_ttl: 8
▶️ Run the Bot
python -m src.main --config configs/config.local.yml
📊 Run the UI
streamlit run src/streamlit_app.py
Open http://localhost:8501 in your browser.
📂 File Structure
src/
  main.py          # entrypoint
  engine.py        # grid engine core
  streamlit_app.py # monitoring UI
configs/
  config.local.yml # config file
.env               # API keys
grid_state.json    # state file (auto-generated)
grid_commands.jsonl# command channel
✅ Example Workflow
Configure .env and config.local.yml.
Run the bot (python -m src.main).
Bot places grid orders (and optional initial position).
Open the UI (streamlit run src/streamlit_app.py).
Monitor PnL, equity, and open orders.
Send commands via the UI to control the bot.
中文（简体）
🚀 OKX 网格交易机器人
这是一个基于 Python + CCXT + Streamlit 开发的 OKX 网格交易机器人，支持 传统全挂单模式，并提供可选的 初始仓位功能。
✨ 功能特点
网格策略
启动时：在现价下方挂买单，在现价上方挂卖单。
支持 初始仓位 (init_position)：
启用时：启动时市价买入一笔仓位，数量等于所有卖单的合计。
确保上方卖单与初始仓位一致。
成交后逻辑：
买单成交 → 在该价格的上方一个网格挂卖单。
卖单成交 → 在该价格的下方一个网格挂买单。
首次成交会被忽略，以保证一致性。
盈亏计算
基于 FIFO 的已实现/未实现盈亏计算。
手续费率可配置。
状态与控制
状态文件 (grid_state.json) 记录价格、订单、仓位、PnL。
命令通道 (grid_commands.jsonl) 支持撤单、恢复、手动挂单。
原子写入，保证数据安全。
监控界面
使用 Streamlit 构建。
KPI 卡片：当前价格、持仓、已实现/未实现盈亏。
价格图：展示挂单网格。
权益曲线：支持时间粒度选择（原始 / 1h / 4h / 1d）。
控制面板：一键撤单、恢复挂单、手动买卖。
支持 10 秒自动刷新（可配置）。
⚙️ 安装
git clone https://github.com/yourname/okx-grid-bot.git
cd okx-grid-bot
pip install -r requirements.txt
🔑 API Key 配置
在项目根目录创建 .env 文件：
OKX_API_KEY=你的API_KEY
OKX_API_SECRET=你的API_SECRET
OKX_PASS=你的PASS_PHRASE
OKX_USE_TESTNET=true   # true = 测试网, false = 实盘
📝 参数配置
编辑 configs/config.local.yml：
exchange:
  symbol: BTC-USDT-SWAP
  default_type: swap

grid:
  lower_price: 10000
  upper_price: 12000
  levels: 20
  order_size: 20
  init_position: true   # 是否启用初始仓位

runtime:
  state_path: grid_state.json
  commands_path: grid_commands.jsonl
  fee_rate: 0.0005
  sleep_sec: 0.5
  rest_poll_sec: 2
  band_ttl: 8
▶️ 运行机器人
python -m src.main --config configs/config.local.yml
📊 打开监控界面
streamlit run src/streamlit_app.py
浏览器访问 http://localhost:8501
📂 项目结构
src/
  main.py          # 启动入口
  engine.py        # 网格策略核心
  streamlit_app.py # 监控与控制 UI
configs/
  config.local.yml # 配置文件
.env               # API Key
grid_state.json    # 状态文件（自动生成）
grid_commands.jsonl# 指令通道
✅ 使用流程示例
配置 .env 和 config.local.yml。
启动机器人 (python -m src.main)。
机器人挂出网格单（可选初始仓位）。
打开 UI (streamlit run src/streamlit_app.py)。
监控盈亏、权益和挂单。
通过 UI 发送指令控制机器人。
