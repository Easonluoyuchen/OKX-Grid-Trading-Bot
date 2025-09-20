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
git clone https://github.com/yourname/okx-grid-bot.git
cd okx-grid-bot
pip install -r requirements.txt
