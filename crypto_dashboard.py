import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Crypto Algo Bot", layout="wide")

PORTFOLIO_FILE = "crypto_portfolio.json"

def load_data():
    if not os.path.exists(PORTFOLIO_FILE): return None
    with open(PORTFOLIO_FILE, 'r') as f: return json.load(f)

data = load_data()

with st.sidebar:
    st.header("🪙 Crypto Alerts Feed")
    st.markdown("---")
    if data and "signals" in data and data["signals"]:
        for signal in data["signals"][:20]:
            if "OPEN" in signal: st.success(signal)
            elif "CLOSED" in signal: st.warning(signal)
            else: st.info(signal)
    else: st.info("No crypto signals generated yet.")

st.title("🪙 Crypto Algo Dashboard")

if data is None:
    st.error("⚠️ No portfolio data found. Please run 'crypto_bot.py' first.")
else:
    capital, open_longs, open_shorts = data.get("capital", 10000), data.get("open_longs", {}), data.get("open_shorts", {})
    closed_longs, closed_shorts = data.get("closed_longs", []), data.get("closed_shorts", [])
    
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
                'Qty': info['qty'], 'Stop Loss': info['stop_loss'], 'PnL': round(pnl, 2), 'Status': 'OPEN', 'Reason': '-'
            })
        return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)

    def color_pnl(val):
        if isinstance(val, (int, float)): return f"color: {'green' if val > 0 else 'red' if val < 0 else 'gray'}"
        return ''

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Available Capital", f"${capital:,.2f}")
    col2.metric("📈 Realized P&L", f"${realized_pnl:,.2f}", delta_color="normal")
    col3.metric("📊 Unrealized P&L", f"${total_unrealized:,.2f}")
    col4.metric("🔄 Active Trades", f"{len(open_longs)} L / {len(open_shorts)} S")

    st.markdown("---")
    t1, t2, t3, t4 = st.tabs(["🟢 Open Longs", "🔴 Open Shorts", "✅ Closed Longs", "❌ Closed Shorts"])

    with t1: st.dataframe(format_open_positions(open_longs, "LONG").style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)
    with t2: st.dataframe(format_open_positions(open_shorts, "SHORT").style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)
    with t3: st.dataframe((pd.DataFrame(closed_longs, columns=COLUMNS) if closed_longs else pd.DataFrame(columns=COLUMNS)).style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)
    with t4: st.dataframe((pd.DataFrame(closed_shorts, columns=COLUMNS) if closed_shorts else pd.DataFrame(columns=COLUMNS)).style.map(color_pnl, subset=['PnL']), use_container_width=True, hide_index=True)