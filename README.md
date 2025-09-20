# OKX Grid Trading Bot

A grid trading bot for **OKX perpetual swaps**, built with **Python + CCXT + Streamlit**.  
Implements the **traditional grid strategy** with an optional **initial position** feature.

---

## ✨ Features

- **Grid Strategy**
  - Place buy orders below current price and sell orders above at startup.
  - **Optional Initial Position (`init_position`)**:
    - Start with a market buy equal to the sum of all sell orders.
    - Keeps upper sell orders consistent with a base position.
  - After fills:
    - Buy filled → place sell one grid above.  
    - Sell filled → place buy one grid below.  
    - First fill after init_position is ignored for consistency.

- **PnL Accounting**
  - FIFO-based realized/unrealized PnL.
  - Configurable fee rate.

- **State & Control**
  - `grid_state.json`: stores price, orders, PnL, inventory.
  - `grid_commands.jsonl`: supports cancel, restore, manual order.
  - Atomic writes for safety.

- **Monitoring UI**
  - Built with **Streamlit**.
  - KPIs: price, inventory, realized/unrealized PnL.
  - Price chart with grid levels.
  - Equity curve with time-frame selection (raw / 1h / 4h / 1d).
  - Control panel: cancel all, restore level, manual buy/sell.
  - Auto-refresh every 10s (configurable).

---

## ⚙️ Installation

```bash
git clone https://github.com/Easonluoyuchen/okx-grid-bot.git
cd okx-grid-bot
pip install -r requirements.txt
```
---

## 🔑 API Keys
Create a .env file in the project root:
```bash
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASS=your_passphrase
OKX_USE_TESTNET=true   # true = testnet, false = live
```

## 📝 Configuration
Edit configs/config.local.yml:
```bash
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
```

## ▶️ Run
Start the bot:
```bash
python -m src.main --config configs/config.local.yml
Start the UI:
streamlit run src/streamlit_app.py
```
Then open http://localhost:8501 in your browser.


-**Workflow**
  -Configure .env and config.local.yml.
  -Run the bot.
  -Grid orders are placed (and optional init position).
  -Open the UI.
  -Monitor PnL, equity, and orders.
  -Control via UI commands.
