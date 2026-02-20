import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- CONFIGURATION ---
PORTFOLIO_FILE = "portfolio.json"
CAPITAL = 4000000.0  # ₹40 Lakhs
RISK_PER_TRADE = 0.005  # 0.5% Risk
BROKERAGE = 0.0015   # 0.15%

# Nifty 50 Watchlist
WATCHLIST = [
    'RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'ITC.NS', 'TCS.NS', 'LT.NS', 
    'BHARTIARTL.NS', 'AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HINDUNILVR.NS', 'BAJFINANCE.NS', 
    'M&M.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'HCLTECH.NS', 'TITAN.NS', 'SUNPHARMA.NS', 'NTPC.NS', 
    'TATASTEEL.NS', 'ULTRACEMCO.NS', 'POWERGRID.NS', 'ONGC.NS', 'BAJAJFINSV.NS', 'NESTLEIND.NS', 
    'ADANIENT.NS', 'INDUSINDBK.NS', 'GRASIM.NS', 'ADANIPORTS.NS', 'HINDALCO.NS', 'COALINDIA.NS', 
    'JSWSTEEL.NS', 'DRREDDY.NS', 'TATAMOTORS.NS', 'APOLLOHOSP.NS', 'TRENT.NS', 'EICHERMOT.NS', 
    'CIPLA.NS', 'DIVISLAB.NS', 'BPCL.NS', 'TECHM.NS', 'WIPRO.NS', 'BRITANNIA.NS', 'LTIM.NS', 
    'SHRIRAMFIN.NS', 'BAJAJ-AUTO.NS', 'HEROMOTOCO.NS', 'TATACONSUM.NS', 'HDFCLIFE.NS'
]

# --- HELPER FUNCTIONS ---
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "capital": CAPITAL, 
        "open_longs": {}, 
        "open_shorts": {}, 
        "closed_longs": [], 
        "closed_shorts": []
    }

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def fetch_hourly_data(ticker):
    """Fetches 1-Hour data and calculates MAs."""
    try:
        # Fetch 60 days to ensure we have enough data for SMA 200 on an hourly chart
        df = yf.download(ticker, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 205: return None, None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Calculate Indicators
        df['SMA_100'] = df['Close'].rolling(window=100).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA_10'] = df['Close'].ewm(span=10, adjust=False).mean()
        df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
        
        return df.iloc[-1], df.iloc[-2] # Current and Previous candle
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None, None

# --- MAIN BOT LOOP ---
def run_bot():
    print(f"\n🚀 Running HOURLY Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    data = load_portfolio()
    
    open_longs = data["open_longs"]
    open_shorts = data["open_shorts"]
    current_capital = data["capital"]

    # ---------------------------------------------------------
    # 1. MANAGE EXITS & TRAILING STOPS
    # ---------------------------------------------------------
    
    # --- CHECK OPEN LONGS ---
    for ticker in list(open_longs.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_longs[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['risk_points']
        current_sl = pos['stop_loss']
        
        # Trailing SL Logic
        r_multiple = (curr['High'] - entry_price) / initial_risk if initial_risk > 0 else 0
        new_sl = current_sl
        
        if r_multiple >= 2.0:
            new_sl = max(current_sl, entry_price + initial_risk) # 1:1 Level
        elif r_multiple >= 1.0:
            new_sl = max(current_sl, entry_price) # Breakeven Level
            
        open_longs[ticker]['stop_loss'] = round(new_sl, 2)
        open_longs[ticker]['current_price'] = round(curr['Close'], 2)
        
        # Exit Conditions
        sl_hit = curr['Low'] <= new_sl
        strategy_exit = (curr['EMA_5'] < curr['EMA_10']) and (prev['EMA_5'] >= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            
            gross_pnl = (exit_price - entry_price) * qty
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE
            net_pnl = gross_pnl - brokerage
            
            data['closed_longs'].append({
                "Ticker": ticker,
                "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price,
                "Exit Price": round(exit_price, 2),
                "Qty": qty,
                "Stop Loss": round(new_sl, 2),
                "PnL": round(net_pnl, 2),
                "Status": "CLOSED",
                "Reason": "Stop Loss Hit" if sl_hit else "EMA 5 < 10"
            })
            current_capital += (exit_price * qty) - brokerage
            del open_longs[ticker]
            print(f"❌ CLOSED LONG: {ticker} | PnL: ₹{net_pnl:.2f}")

    # --- CHECK OPEN SHORTS ---
    for ticker in list(open_shorts.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_shorts[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['risk_points']
        current_sl = pos['stop_loss']
        
        # Trailing SL Logic
        r_multiple = (entry_price - curr['Low']) / initial_risk if initial_risk > 0 else 0
        new_sl = current_sl
        
        if r_multiple >= 2.0:
            new_sl = min(current_sl, entry_price - initial_risk) # 1:1 Level
        elif r_multiple >= 1.0:
            new_sl = min(current_sl, entry_price) # Breakeven Level
            
        open_shorts[ticker]['stop_loss'] = round(new_sl, 2)
        open_shorts[ticker]['current_price'] = round(curr['Close'], 2)
        
        # Exit Conditions
        sl_hit = curr['High'] >= new_sl
        strategy_exit = (curr['EMA_5'] > curr['EMA_10']) and (prev['EMA_5'] <= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            
            gross_pnl = (entry_price - exit_price) * qty
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE
            net_pnl = gross_pnl - brokerage
            
            data['closed_shorts'].append({
                "Ticker": ticker,
                "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price,
                "Exit Price": round(exit_price, 2),
                "Qty": qty,
                "Stop Loss": round(new_sl, 2),
                "PnL": round(net_pnl, 2),
                "Status": "CLOSED",
                "Reason": "Stop Loss Hit" if sl_hit else "EMA 5 > 10"
            })
            current_capital += (entry_price * qty) + net_pnl # Add margin and profit back
            del open_shorts[ticker]
            print(f"❌ CLOSED SHORT: {ticker} | PnL: ₹{net_pnl:.2f}")

    # ---------------------------------------------------------
    # 2. CHECK NEW ENTRIES
    # ---------------------------------------------------------
    print("\n🔎 Scanning for New Hourly Signals...")
    for ticker in WATCHLIST:
        if ticker in open_longs or ticker in open_shorts:
            continue
            
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        # --- LONG SETUP ---
        long_trend = (curr['SMA_100'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_100']) and (curr['EMA_21'] > curr['EMA_50'])
        long_trigger = (curr['EMA_10'] > curr['EMA_21']) and (prev['EMA_10'] <= prev['EMA_21'])
        
        if long_trend and long_trigger:
            entry_price = curr['Close']
            sl_price = curr['EMA_21'] * 0.999 # 0.1% Below
            risk_points = entry_price - sl_price
            
            if risk_points > 0:
                risk_amt = CAPITAL * RISK_PER_TRADE # ₹20,000
                qty = int(risk_amt // risk_points)
                cost = qty * entry_price
                
                if qty > 0 and current_capital >= cost:
                    brokerage = cost * BROKERAGE
                    current_capital -= (cost + brokerage)
                    
                    open_longs[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2),
                        "qty": qty,
                        "risk_points": round(risk_points, 2),
                        "stop_loss": round(sl_price, 2),
                        "current_price": round(entry_price, 2)
                    }
                    print(f"✅ OPEN LONG: {ticker} @ {entry_price:.2f} | Qty: {qty}")
        
        # --- SHORT SETUP ---
        short_trend = (curr['SMA_100'] < curr['SMA_200']) and (curr['EMA_50'] < curr['SMA_100']) and (curr['EMA_21'] < curr['EMA_50'])
        short_trigger = (curr['EMA_10'] < curr['EMA_21']) and (prev['EMA_10'] >= prev['EMA_21'])
        
        if short_trend and short_trigger:
            entry_price = curr['Close']
            sl_price = curr['EMA_21'] * 1.001 # 0.1% Above
            risk_points = sl_price - entry_price
            
            if risk_points > 0:
                risk_amt = CAPITAL * RISK_PER_TRADE
                qty = int(risk_amt // risk_points)
                margin_req = qty * entry_price
                
                if qty > 0 and current_capital >= margin_req:
                    brokerage = margin_req * BROKERAGE
                    current_capital -= brokerage # Deduct fee, freeze margin virtually
                    
                    open_shorts[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2),
                        "qty": qty,
                        "risk_points": round(risk_points, 2),
                        "stop_loss": round(sl_price, 2),
                        "current_price": round(entry_price, 2)
                    }
                    print(f"✅ OPEN SHORT: {ticker} @ {entry_price:.2f} | Qty: {qty}")

    # Save
    data["open_longs"] = open_longs
    data["open_shorts"] = open_shorts
    data["capital"] = current_capital
    save_portfolio(data)
    print("💾 Portfolio Updated Successfully.")

if __name__ == "__main__":
    run_bot()