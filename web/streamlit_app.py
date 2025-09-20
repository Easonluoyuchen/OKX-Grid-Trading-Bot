# web/streamlit_app.py
import streamlit as st
import json, os
import plotly.graph_objects as go
from datetime import datetime
import pandas as pd

STATE_PATH = "grid_state.json"
COMMANDS_PATH = "grid_commands.jsonl"

import streamlit as st

def setup_autorefresh(seconds: int = 10, key: str = "refresh"):
    """自動刷新：優先用官方 API，否則 fallback 到 JS。"""
    # 新版 (>=1.41)
    if hasattr(st, "autorefresh"):
        st.autorefresh(interval=seconds * 1000, key=key)
        return
    # 舊版 (~1.11–1.40)
    if hasattr(st, "experimental_autorefresh"):
        st.experimental_autorefresh(interval=seconds * 1000, key=key)
        return
    # fallback: JS 刷新
    import streamlit.components.v1 as components
    components.html(
        f"""
        <script>
          setTimeout(function() {{
            window.location.reload();
          }}, {seconds * 1000});
        </script>
        """,
        height=0,
    )

# 設定頁面
st.set_page_config(page_title="OKX Grid Monitor", layout="wide")
st.title("📊 OKX Grid Trading – Monitor & Control")

# 啟用 10 秒自動刷新
setup_autorefresh(10, "refresh")


# --- 載入狀態檔 ---
def load_state(path=STATE_PATH):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

state = load_state()

if state is None:
    st.warning("⚠️ 暫無數據，等待 engine 寫入 grid_state.json ...")
    st.stop()

# --- KPI 區塊 ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Current Price", f"{state['current_price']:.2f}")
col2.metric("Inventory (contracts)", f"{state['inventory_contracts']:.4f}")
col3.metric("Realized PnL", f"{state['realized_pnl']:.2f}")
col4.metric("Unrealized PnL", f"{state['unrealized_pnl']:.2f}")

# --- 價格 & 網格單 ---
st.subheader("📈 Price + Grid Orders")

fig = go.Figure()

# 價格點（當前）
fig.add_trace(go.Scatter(
    x=[state['ts']], y=[state['current_price']],
    mode="markers", name="Current Price",
    marker=dict(size=10, symbol="x")
))

# 買單線
for o in state.get('open_orders', []):
    if o.get('side') == 'buy':
        fig.add_hline(y=o['price'], line=dict(dash="dot"), annotation_text="BUY", annotation_position="right")

# 賣單線
for o in state.get('open_orders', []):
    if o.get('side') == 'sell':
        fig.add_hline(y=o['price'], line=dict(dash="dot"), annotation_text="SELL", annotation_position="right")

fig.update_layout(height=400, xaxis_title="Time", yaxis_title="Price", showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# --- Equity 曲線（支援時間粒度切換） ---
st.subheader("💰 Equity Curve")

equity_series = state.get("equity_series", [])

if equity_series:
    # 轉成 DataFrame
    df = pd.DataFrame(equity_series)
    # 時間處理（ISO 8601，末尾 Z → UTC）
    df['ts'] = pd.to_datetime(df['ts'], utc=True, errors='coerce')
    df = df.dropna(subset=['ts']).set_index('ts').sort_index()

    # 粒度選擇
    granularity = st.selectbox("時間粒度", ["原始", "1h", "4h", "1d"], index=0)

    if granularity != "原始":
        rule = {"1h": "1H", "4h": "4H", "1d": "1D"}[granularity]
        # 使用最後一筆（更貼近權益序列的狀態型時間序列）
        df_res = df.resample(rule).last().dropna(how="all")
    else:
        df_res = df

    # 圖：Equity（可勾選是否顯示 realized/unrealized）
    show_realized = st.checkbox("顯示 Realized PnL", value=False)
    show_unrealized = st.checkbox("顯示 Unrealized PnL", value=False)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df_res.index, y=df_res['equity'], mode="lines", name="Equity"))

    if show_realized and 'realized' in df_res:
        fig2.add_trace(go.Scatter(x=df_res.index, y=df_res['realized'], mode="lines", name="Realized PnL"))
    if show_unrealized and 'unrealized' in df_res:
        fig2.add_trace(go.Scatter(x=df_res.index, y=df_res['unrealized'], mode="lines", name="Unrealized PnL"))

    fig2.update_layout(height=320, xaxis_title="Time (UTC)", yaxis_title="Value")
    st.plotly_chart(fig2, use_container_width=True)

    st.caption(f"點數：{len(df_res)}（來源粒度：{granularity}）")
else:
    st.info("暫無 Equity 數據")

# --- 控制面板 ---
st.subheader("⚙️ Control Panel")

default_price = float(state.get('current_price', 0.0) or 0.0)
price_input = st.number_input("Price", value=default_price, step=1.0, format="%.2f")
contracts_input = st.number_input("Contracts", value=0.01, step=0.01, format="%.4f")

colA, colB, colC = st.columns(3)

if colA.button("Cancel All Orders"):
    with open(COMMANDS_PATH, "a") as f:
        f.write(json.dumps({"op": "cancel_all"}) + "\n")
    st.success("已發送 Cancel All 指令")

if colB.button("Place Buy"):
    with open(COMMANDS_PATH, "a") as f:
        f.write(json.dumps({"op": "place_limit", "side": "buy", "price": price_input, "contracts": contracts_input}) + "\n")
    st.success(f"已發送 Buy {contracts_input} @ {price_input}")

if colC.button("Place Sell"):
    with open(COMMANDS_PATH, "a") as f:
        f.write(json.dumps({"op": "place_limit", "side": "sell", "price": price_input, "contracts": contracts_input}) + "\n")
    st.success(f"已發送 Sell {contracts_input} @ {price_input}")
