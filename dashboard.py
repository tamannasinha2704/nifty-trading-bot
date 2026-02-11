import streamlit as st
import pandas as pd
import json
import os
import pytz
import yfinance as yf
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="Nifty Bot Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
TRADES_FILE = "trades.json"
HISTORY_FILE = "trade_history.json"
SIGNALS_FILE = "signals.json"
IST = pytz.timezone('Asia/Kolkata')

# --- LOADERS ---
def load_json(filename):
    if not os.path.exists(filename): return {} if filename == TRADES_FILE else []
    try:
        with open(filename, 'r') as f: return json.load(f)
    except: return {} if filename == TRADES_FILE else []

def get_live_prices(tickers):
    if not tickers: return {}
    try:
        df = yf.download(tickers, period="1d", progress=False)['Close']
        if len(tickers) == 1: return {tickers[0]: df.iloc[-1]}
        return df.iloc[-1].to_dict()
    except: return {}

# --- SIDEBAR: ACTIVITY LOG ---
st.sidebar.header("🔔 Activity Log")
signals = load_json(SIGNALS_FILE)

if not signals:
    st.sidebar.info("No activity recorded yet.")
else:
    # Show last 15 signals
    for s in reversed(signals[-15:]):
        st.sidebar.text(f"🕒 {s['timestamp']}")
        st.sidebar.info(s['message'])
        st.sidebar.markdown("---")

# --- MAIN PAGE ---
st.title("📈 Nifty 50 Swing Trading Bot")
st.markdown(f"**Last Updated:** {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')}")

# Load Data
portfolio = load_json(TRADES_FILE)
history = load_json(HISTORY_FILE)
tickers = list(portfolio.keys())
live_prices = get_live_prices(tickers)

# --- TABS ---
tab1, tab2 = st.tabs(["🟢 Active Positions", "🔴 Closed History"])

with tab1:
    if not portfolio:
        st.info("No active trades.")
    else:
        rows = []
        total_inv, total_val, total_pnl = 0, 0, 0
        
        for ticker, info in portfolio.items():
            qty = info['quantity']
            entry = info['entry_price']
            ltp = live_prices.get(ticker, entry)
            
            inv = entry * qty
            val = ltp * qty
            pnl = val - inv
            
            total_inv += inv
            total_val += val
            total_pnl += pnl
            
            rows.append({
                "Ticker": ticker,
                "Entry Date": info['entry_date'],
                "Entry Time": info.get('entry_time', 'N/A'),
                "Qty": qty,
                "Entry Price": f"₹{entry:.2f}",
                "LTP": f"₹{ltp:.2f}",
                "Invested Value": f"₹{inv:,.0f}",
                "Present Value": f"₹{val:,.0f}",
                "Notional P/L": f"₹{pnl:,.0f}",
                "P/L %": f"{(pnl/inv)*100:.2f}%",
                "SL Price": f"₹{info['sl_price']:.2f}"
            })
            
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Invested", f"₹{total_inv:,.0f}")
        c2.metric("Current Value", f"₹{total_val:,.0f}")
        c3.metric("Unrealized P/L", f"₹{total_pnl:,.0f}", delta=f"{(total_pnl/total_inv)*100:.2f}%")
        c4.metric("Active Trades", len(portfolio))
        
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab2:
    if not history:
        st.info("No history yet.")
    else:
        st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)

if st.button('🔄 Refresh'):
    st.rerun()