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
IST = pytz.timezone('Asia/Kolkata')

# --- FUNCTIONS ---
def load_data():
    if not os.path.exists(TRADES_FILE):
        return {}
    try:
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def get_live_prices(tickers):
    if not tickers: return {}
    try:
        # Download live data for all tickers at once
        df = yf.download(tickers, period="1d", progress=False)['Close']
        # Handle single ticker vs multiple tickers
        if len(tickers) == 1:
            return {tickers[0]: df.iloc[-1]}
        return df.iloc[-1].to_dict()
    except:
        return {}

# --- DASHBOARD LAYOUT ---
st.title("📈 Nifty 50 Swing Trading Bot")
st.markdown(f"**Last Updated:** {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}")

# 1. Load Data
portfolio = load_data()

if not portfolio:
    st.info("Waiting for trades... Market is quiet. 😴")
else:
    # 2. Fetch Live Prices
    tickers = list(portfolio.keys())
    live_prices = get_live_prices(tickers)

    # 3. Process Data for Table
    active_rows = []
    
    total_invested = 0
    total_current_value = 0
    total_pnl = 0

    for ticker, info in portfolio.items():
        # Basic Info
        qty = info['quantity']
        entry_price = info['entry_price']
        ltp = live_prices.get(ticker, entry_price)  # Fallback to entry price if fetch fails
        
        # Calculations
        invested_val = entry_price * qty
        current_val = ltp * qty
        pnl = current_val - invested_val
        pnl_pct = (pnl / invested_val) * 100 if invested_val > 0 else 0
        
        # Add to Totals
        total_invested += invested_val
        total_current_value += current_val
        total_pnl += pnl

        # Row Data
        active_rows.append({
            "Ticker": ticker,
            "Entry Date": info['entry_date'],
            "Qty": qty,
            "Entry Price": f"₹{entry_price:.2f}",
            "LTP": f"₹{ltp:.2f}",
            "Invested Value": f"₹{invested_val:,.2f}",
            "Present Value": f"₹{current_val:,.2f}",
            "P/L": f"₹{pnl:,.2f}",
            "P/L %": f"{pnl_pct:.2f}%",
            "Status": info['status']
        })

    # 4. Metric Cards (Summary)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Invested", f"₹{total_invested:,.0f}")
    with col2: st.metric("Current Value", f"₹{total_current_value:,.0f}")
    with col3: st.metric("Total P/L", f"₹{total_pnl:,.0f}", delta=f"{(total_pnl/total_invested)*100:.2f}%")
    with col4: st.metric("Active Positions", len(portfolio))

    st.divider()

    # 5. Active Holdings Table
    st.subheader("📋 Active Holdings")
    df_active = pd.DataFrame(active_rows)
    st.dataframe(df_active, use_container_width=True, hide_index=True)

    # 6. Closed / Booked Profits Section (Simulated from PARTIAL trades)
    # Since your JSON only tracks current holding, we infer 'booked' profits if status is PARTIAL.
    # (Note: Strictly speaking, the bot needs to save 'closed_trades' to a separate list to track this permanently. 
    # For now, this shows the 'Active' portion of partial trades).
    
    st.divider()
    st.caption("ℹ️ Note: 'Closed Positions' requires a separate history file. Currently showing live P/L of active partial holdings.")

# Manual Refresh
if st.button('🔄 Refresh Prices'):
    st.rerun()