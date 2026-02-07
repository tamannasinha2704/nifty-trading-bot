import streamlit as st
import pandas as pd
import json
import os
import pytz
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Nifty Bot Dashboard", page_icon="📈", layout="wide")
TRADES_FILE = "trades.json"
IST = pytz.timezone('Asia/Kolkata')

# --- FUNCTIONS ---
def load_data():
    """Reads the latest trade data from the JSON file."""
    if not os.path.exists(TRADES_FILE):
        return {}
    try:
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def get_ist_time():
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

# --- DASHBOARD LAYOUT ---
st.title("📈 Nifty 50 Swing Trading Bot")
st.markdown(f"**Last Updated:** {get_ist_time()}")

# 1. Load Data
portfolio = load_data()

# 2. Key Metrics Row
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Active Positions", len(portfolio))
with col2:
    # Calculate Total Invested (Approx)
    total_invested = sum([d['entry_price'] * d['quantity'] for d in portfolio.values()])
    st.metric("Total Invested", f"₹{total_invested:,.2f}")
with col3:
    st.metric("Status", "🤖 Bot Running")

st.divider()

# 3. Active Positions Table
st.subheader("📋 Active Holdings")

if not portfolio:
    st.info("No active trades right now. Waiting for signals...")
else:
    # Convert JSON to DataFrame for display
    data = []
    for ticker, info in portfolio.items():
        row = info.copy()
        row['Ticker'] = ticker
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Reorder columns for neatness
    display_cols = ['Ticker', 'entry_date', 'entry_price', 'quantity', 'sl_price', 'status']
    # Ensure columns exist before selecting
    cols = [c for c in display_cols if c in df.columns]
    df = df[cols]
    
    # Show the table
    st.dataframe(df, use_container_width=True)

# 4. Logs / Raw Data (Optional)
with st.expander("📂 View Raw JSON Data"):
    st.json(portfolio)

# 5. Manual Refresh Button
if st.button('🔄 Refresh Data'):
    st.rerun()