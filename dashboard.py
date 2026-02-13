import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="Hourly Swing Bot", layout="wide")
st.title("⚡ Algo Trading Dashboard (Hourly)")

PORTFOLIO_FILE = "portfolio.json"

def load_data():
    if not os.path.exists(PORTFOLIO_FILE):
        return None
    with open(PORTFOLIO_FILE, 'r') as f:
        return json.load(f)

data = load_data()

if data is None:
    st.warning("⚠️ No portfolio data found. Please run 'bot.py' first.")
else:
    # --- METRICS ---
    capital = data.get("capital", 4000000)
    long_pos = data.get("long_positions", {})
    short_pos = data.get("short_positions", {})
    long_hist = data.get("long_history", [])
    short_hist = data.get("short_history", [])
    
    # Calculate Unrealized PnL
    # (Note: In a real live dashboard, we would fetch live prices here to update PnL. 
    # For now, we use the prices stored in JSON or assume 0 change if static)
    unrealized_pnl = 0
    
    # Total PnL from History
    realized_pnl = sum([t['PnL'] for t in long_hist]) + sum([t['PnL'] for t in short_hist])
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Total Capital", f"₹{capital:,.0f}")
    col2.metric("📊 Realized P&L", f"₹{realized_pnl:,.2f}", delta_color="normal")
    col3.metric("🟢 Active Longs", len(long_pos))
    col4.metric("🔴 Active Shorts", len(short_pos))
    
    st.markdown("---")
    
    # --- ACTIVE POSITIONS TABS ---
    tab_long, tab_short = st.tabs(["🟢 Long Positions", "🔴 Short Positions"])
    
    with tab_long:
        if not long_pos:
            st.info("No Active Long Positions")
        else:
            df_long = pd.DataFrame.from_dict(long_pos, orient='index')
            df_long['Type'] = 'LONG'
            st.dataframe(df_long[['Type', 'entry_date', 'entry_price', 'qty', 'stop_loss', 'initial_risk_per_share']], use_container_width=True)
            
    with tab_short:
        if not short_pos:
            st.info("No Active Short Positions")
        else:
            df_short = pd.DataFrame.from_dict(short_pos, orient='index')
            df_short['Type'] = 'SHORT'
            st.dataframe(df_short[['Type', 'entry_date', 'entry_price', 'qty', 'stop_loss', 'initial_risk_per_share']], use_container_width=True)

    st.markdown("### 📜 Trade History")
    
    # Combine History
    all_history = long_hist + short_hist
    
    if not all_history:
        st.info("No completed trades yet.")
    else:
        df_hist = pd.DataFrame(all_history)
        
        # Sort by Exit Date (assuming ISO format YYYY-MM-DD HH:MM works for sorting)
        df_hist = df_hist.sort_values(by="Exit Date", ascending=False)
        
        # Unified Columns Layout
        cols = ["Ticker", "Type", "Entry Date", "Exit Date", "Entry Price", "Exit Price", "Qty", "PnL", "Reason"]
        
        # Color Logic for PnL
        def color_pnl(val):
            color = '#d4edda' if val > 0 else '#f8d7da' # Light green / Light red
            text_color = 'green' if val > 0 else 'red'
            return f'background-color: {color}; color: {text_color}'

        st.dataframe(
            df_hist[cols].style.applymap(color_pnl, subset=['PnL']),
            use_container_width=True
        )