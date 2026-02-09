import streamlit as st
import pandas as pd
import json
import os
import pytz
import yfinance as yf
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Nifty Bot Dashboard", page_icon="📈", layout="wide")
TRADES_FILE = "trades.json"
HISTORY_FILE = "trade_history.json"
IST = pytz.timezone('Asia/Kolkata')

# --- FUNCTIONS ---
def load_json(filename):
    if not os.path.exists(filename): return {} if filename == TRADES_FILE else []
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return {} if filename == TRADES_FILE else []

def get_live_prices(tickers):
    if not tickers: return {}
    try:
        # Fetch live data
        df = yf.download(tickers, period="1d", progress=False)['Close']
        if len(tickers) == 1:
            return {tickers[0]: df.iloc[-1]}
        return df.iloc[-1].to_dict()
    except:
        return {}

# --- DASHBOARD UI ---
st.title("📈 Nifty 50 Swing Trading Bot")
st.markdown(f"**Last Updated:** {datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')}")

# 1. Load Data
active_portfolio = load_json(TRADES_FILE)
history_data = load_json(HISTORY_FILE)

# 2. Fetch Live Prices
if active_portfolio:
    tickers = list(active_portfolio.keys())
    live_prices = get_live_prices(tickers)
else:
    live_prices = {}

# --- TAB 1: ACTIVE POSITIONS ---
st.subheader("🟢 Active Positions")

if not active_portfolio:
    st.info("No active trades currently open.")
else:
    active_rows = []
    total_invested = 0
    total_curr_val = 0
    total_unrealized_pnl = 0

    for ticker, info in active_portfolio.items():
        qty = info['quantity']
        entry_price = info['entry_price']
        # Fallback to entry price if live price fails
        ltp = live_prices.get(ticker, entry_price)
        
        invested = entry_price * qty
        current = ltp * qty
        pnl = current - invested
        pnl_pct = (pnl / invested) * 100 if invested > 0 else 0
        
        total_invested += invested
        total_curr_val += current
        total_unrealized_pnl += pnl
        
        active_rows.append({
            "Ticker": ticker,
            "Entry Date": info['entry_date'],
            "Entry Time": info.get('entry_time', 'N/A'), # New Field
            "Qty": qty,
            "Entry Price": f"₹{entry_price:.2f}",
            "LTP": f"₹{ltp:.2f}", # Last Traded Price
            "Invested Value": f"₹{invested:,.0f}",
            "Present Value": f"₹{current:,.0f}",
            "Notional P/L": f"₹{pnl:,.0f}",
            "P/L %": f"{pnl_pct:.2f}%",
            "SL Price": f"₹{info['sl_price']:.2f}"
        })

    # Summary Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invested", f"₹{total_invested:,.0f}")
    c2.metric("Current Value", f"₹{total_curr_val:,.0f}")
    c3.metric("Unrealized P/L", f"₹{total_unrealized_pnl:,.0f}", delta=f"{(total_unrealized_pnl/total_invested)*100:.2f}%")
    c4.metric("Active Trades", len(active_portfolio))

    st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True)

st.divider()

# --- TAB 2: CLOSED POSITIONS (HISTORY) ---
st.subheader("🔴 Closed Positions (History)")

if not history_data:
    st.info("No closed trades in history yet.")
else:
    # Filter only SELL actions to show PnL
    closed_rows = [x for x in history_data if "SELL" in x['action']]
    
    if closed_rows:
        total_realized_pnl = sum([x['pnl'] for x in closed_rows])
        st.metric("Total Realized Profit", f"₹{total_realized_pnl:,.2f}")
        
        # Display table
        df_hist = pd.DataFrame(closed_rows)
        # Reorder/Rename for clarity
        display_cols = ['timestamp', 'ticker', 'action', 'quantity', 'price', 'pnl', 'reason']
        df_hist = df_hist[display_cols]
        df_hist.columns = ['Exit Time', 'Ticker', 'Action', 'Qty', 'Exit Price', 'Realized P/L', 'Reason']
        
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("History exists, but no closed trades yet (Only Buys).")

# Refresh Button
if st.button('🔄 Refresh Data'):
    st.rerun()