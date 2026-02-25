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
    capital = data.get("capital", 10000)
    open_longs = data.get("open_longs", {})
    open_shorts = data.get("open_shorts", {})
    closed_longs = data.get("closed_longs", [])
    closed_shorts = data.get("closed_shorts", [])
    
    unrealized_long_pnl = sum([(p['current_price'] - p['entry_price']) * p['qty'] for p in open_longs.values()])
    unrealized_short_pnl = sum([(p['entry_price'] - p['current_price']) * p['qty'] for p in open_shorts.values()])
    total_unrealized = unrealized_long_pnl + unrealized_short_pnl
    realized_pnl = sum([t['PnL'] for t in closed_longs]) + sum([t['PnL'] for t in closed_shorts])
    
    # --- TABLE FORMATTING FUNCTIONS ---
    def format_open_positions(pos_dict, position_type):
        rows = []
        for ticker, info in pos_dict.items():
            dt_split = info['entry_date'].split(' ')
            d = dt_split[0] if len(dt_split) > 0 else '-'
            t = dt_split[1] if len(dt_split) > 1 else '-'
            
            e_price = info['entry_price']
            c_price = info['current_price']
            qty = info['qty']
            e_val = e_price * qty
            c_val = c_price * qty
            
            if position_type == "LONG":
                b_s = "BUY"
                pnl = c_val - e_val
            else:
                b_s = "SELL"
                pnl = e_val - c_val
                
            rows.append({
                'Date': d, 'Time': t, 'Script Name': ticker, 'Buy/Sell': b_s,
                'Price': e_price, 'Qty': qty, 'Value': round(e_val, 4),
                'Current Price': c_price, 'Current Value': round(c_val, 4), 'Current P/L': round(pnl, 2)
            })
        return pd.DataFrame(rows)

    def format_closed_positions(history_list, position_type):
        rows = []
        for trade in history_list:
            ent_split = trade['Entry Date'].split(' ')
            ent_d = ent_split[0] if len(ent_split) > 0 else '-'
            ent_t = ent_split[1] if len(ent_split) > 1 else '-'
            
            ext_split = trade['Exit Date'].split(' ')
            ext_d = ext_split[0] if len(ext_split) > 0 else '-'
            ext_t = ext_split[1] if len(ext_split) > 1 else '-'
            
            e_price = trade['Entry Price']
            ex_price = trade['Exit Price']
            qty = trade['Qty']
            e_val = e_price * qty
            ex_val = ex_price * qty
            pnl = trade['PnL']
            
            # Logic maps entry/exit to Buy/Sell depending on trade direction
            if position_type == "LONG":
                buy_d, buy_t, buy_p, buy_v = ent_d, ent_t, e_price, e_val
                sell_d, sell_t, sell_p, sell_v = ext_d, ext_t, ex_price, ex_val
            else:
                sell_d, sell_t, sell_p, sell_v = ent_d, ent_t, e_price, e_val
                buy_d, buy_t, buy_p, buy_v = ext_d, ext_t, ex_price, ex_val
                
            rows.append({
                'Buy Date': buy_d, 'Buy Time': buy_t, 'Script Name': trade['Ticker'],
                'Buy Price': buy_p, 'Buy Qty': qty, 'Buy Value': round(buy_v, 4),
                'Sell Date': sell_d, 'Sell Time': sell_t, 'Sell Price': sell_p,
                'Sell Qty': qty, 'Sell Value': round(sell_v, 4), 'P/L': round(pnl, 2)
            })
        return pd.DataFrame(rows)

    def color_pnl(val):
        if isinstance(val, (int, float)):
            return f"color: {'green' if val > 0 else 'red' if val < 0 else 'gray'}"
        return ''

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Available Capital", f"${capital:,.2f}")
    col2.metric("📈 Realized P&L", f"${realized_pnl:,.2f}", delta_color="normal")
    col3.metric("📊 Unrealized P&L", f"${total_unrealized:,.2f}")
    col4.metric("🔄 Active Trades", f"{len(open_longs)} L / {len(open_shorts)} S")

    st.markdown("---")
    t1, t2, t3, t4 = st.tabs(["🟢 Open Longs", "🔴 Open Shorts", "✅ Closed Longs", "❌ Closed Shorts"])

    with t1:
        df_ol = format_open_positions(open_longs, "LONG")
        if not df_ol.empty: st.dataframe(df_ol.style.map(color_pnl, subset=['Current P/L']), use_container_width=True, hide_index=True)
        else: st.info("No open long positions.")
    with t2:
        df_os = format_open_positions(open_shorts, "SHORT")
        if not df_os.empty: st.dataframe(df_os.style.map(color_pnl, subset=['Current P/L']), use_container_width=True, hide_index=True)
        else: st.info("No open short positions.")
    with t3:
        df_cl = format_closed_positions(closed_longs, "LONG")
        if not df_cl.empty: st.dataframe(df_cl.style.map(color_pnl, subset=['P/L']), use_container_width=True, hide_index=True)
        else: st.info("No closed long positions.")
    with t4:
        df_cs = format_closed_positions(closed_shorts, "SHORT")
        if not df_cs.empty: st.dataframe(df_cs.style.map(color_pnl, subset=['P/L']), use_container_width=True, hide_index=True)
        else: st.info("No closed short positions.")