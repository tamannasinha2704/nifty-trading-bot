import streamlit as st
import pandas as pd
import json
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="Hourly Swing Bot", layout="wide")

PORTFOLIO_FILE = "portfolio.json"
CONFIG_FILE = "config.json"

def load_data():
    if not os.path.exists(PORTFOLIO_FILE):
        return None
    with open(PORTFOLIO_FILE, 'r') as f:
        return json.load(f)

data = load_data()

# --- SIDEBAR: LIVE SIGNALS FEED ---
with st.sidebar:
    st.header("🔔 Live Alerts Feed")
    st.markdown("---")
    if data and "signals" in data and data["signals"]:
        for signal in data["signals"][:20]: # Display the latest 20 signals
            if "OPEN" in signal:
                st.success(signal)
            elif "CLOSED" in signal:
                st.warning(signal)
            else:
                st.info(signal)
    else:
        st.info("No signals generated yet. Waiting for market setups...")

# --- MAIN DASHBOARD ---
st.title("⚡ Hourly Algo Dashboard")

if data is None:
    st.error("⚠️ No portfolio data found. Please run 'bot.py' first.")
else:
    capital = data.get("capital", 4000000)
    open_longs = data.get("open_longs", {})
    open_shorts = data.get("open_shorts", {})
    closed_longs = data.get("closed_longs", [])
    closed_shorts = data.get("closed_shorts", [])
    
    # Calculate Unrealized PnL
    unrealized_long_pnl = sum([(p['current_price'] - p['entry_price']) * p['qty'] for p in open_longs.values()])
    unrealized_short_pnl = sum([(p['entry_price'] - p['current_price']) * p['qty'] for p in open_shorts.values()])
    total_unrealized = unrealized_long_pnl + unrealized_short_pnl
    
    realized_pnl = sum([t['PnL'] for t in closed_longs]) + sum([t['PnL'] for t in closed_shorts])
    
    COLUMNS = ['Ticker', 'Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Qty', 'Stop Loss', 'PnL', 'Status', 'Reason']

    def format_open_positions(pos_dict, position_type):
        rows = []
        for ticker, info in pos_dict.items():
            pnl = (info['current_price'] - info['entry_price']) * info['qty'] if position_type == "LONG" else (info['entry_price'] - info['current_price']) * info['qty']
            rows.append({
                'Ticker': ticker, 'Entry Date': info['entry_date'], 'Exit Date': '-',
                'Entry Price': info['entry_price'], 'Exit Price': info['current_price'], 
                'Qty': info['qty'], 'Stop Loss': info['stop_loss'], 'PnL': round(pnl, 2),
                'Status': 'OPEN', 'Reason': '-'
            })
        return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)

    def color_pnl(val):
        if isinstance(val, (int, float)):
            color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
            return f'color: {color}'
        return ''

    # --- METRICS SECTION ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Available Capital", f"₹{capital:,.2f}")
    col2.metric("📈 Realized P&L", f"₹{realized_pnl:,.2f}", delta_color="normal")
    col3.metric("📊 Unrealized P&L", f"₹{total_unrealized:,.2f}")
    col4.metric("🔄 Active Trades", f"{len(open_longs)} L / {len(open_shorts)} S")

    st.markdown("---")

    # --- TABS FOR TABLES ---
    t1, t2, t3, t4 = st.tabs(["🟢 Open Longs", "🔴 Open Shorts", "✅ Closed Longs", "❌ Closed Shorts"])

    with t1:
        df_ol = format_open_positions(open_longs, "LONG")
        st.dataframe(df_ol.style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)

    with t2:
        df_os = format_open_positions(open_shorts, "SHORT")
        st.dataframe(df_os.style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)

    with t3:
        df_cl = pd.DataFrame(closed_longs, columns=COLUMNS) if closed_longs else pd.DataFrame(columns=COLUMNS)
        st.dataframe(df_cl.style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)

    with t4:
        df_cs = pd.DataFrame(closed_shorts, columns=COLUMNS) if closed_shorts else pd.DataFrame(columns=COLUMNS)
        st.dataframe(df_cs.style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)