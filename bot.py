import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
import time

# --- CONFIGURATION ---
PORTFOLIO_FILE = "portfolio.json"
CAPITAL = 4000000.0  # ₹40 Lakhs
RISK_PER_TRADE_PCT = 0.005  # 0.5% Risk
BROKERAGE = 0.0015   # 0.15%

# Nifty 50 Watchlist (Partial list for speed, add full list as needed)
WATCHLIST = [
    'RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'ITC.NS', 'TCS.NS', 'LT.NS', 
    'BHARTIARTL.NS', 'AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HINDUNILVR.NS', 'BAJFINANCE.NS', 
    'M&M.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'HCLTECH.NS', 'TITAN.NS', 'SUNPHARMA.NS', 'NTPC.NS',
    'TATAMOTORS.NS', 'ULTRACEMCO.NS', 'POWERGRID.NS', 'ONGC.NS', 'BAJAJFINSV.NS'
]

# --- HELPER FUNCTIONS ---

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {
        "capital": CAPITAL, 
        "long_positions": {}, 
        "short_positions": {}, 
        "long_history": [], 
        "short_history": []
    }

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def fetch_data(ticker):
    """Fetches 1-Hour data for calculation."""
    try:
        # 60 days of 1h data to ensure enough length for SMA 200
        df = yf.download(ticker, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 205: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # --- INDICATORS ---
        df['SMA_100'] = df['Close'].rolling(window=100).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA_10'] = df['Close'].ewm(span=10, adjust=False).mean()
        df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
        
        # Shifted columns for crossover detection
        df['EMA_10_Prev'] = df['EMA_10'].shift(1)
        df['EMA_21_Prev'] = df['EMA_21'].shift(1)
        df['EMA_5_Prev'] = df['EMA_5'].shift(1)
        df['EMA_10_Prev_Candle'] = df['EMA_10'].shift(1) # Duplicate naming fix
        
        return df.iloc[-1], df.iloc[-2] # Return Current and Previous candle
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None, None

# --- STRATEGY LOGIC ---

def run_bot():
    print(f"\n🚀 Running HOURLY Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    data = load_portfolio()
    
    # Unpack Data
    long_positions = data["long_positions"]
    short_positions = data["short_positions"]
    current_capital = data["capital"]
    
    # ---------------------------------------------------------
    # 1. MANAGE EXISTING POSITIONS (Trailing SL & Exits)
    # ---------------------------------------------------------
    
    # --- LONG POSITIONS ---
    for ticker in list(long_positions.keys()):
        curr, prev = fetch_data(ticker)
        if curr is None: continue
        
        pos = long_positions[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['initial_risk_per_share']
        current_sl = pos['stop_loss']
        
        # A. Trailing Stop Logic (Long)
        reward = curr['High'] - entry_price
        r_multiple = reward / initial_risk if initial_risk > 0 else 0
        
        new_sl = current_sl
        if r_multiple >= 2.0:
            # Shift SL to 1:1 Level (Entry + 1R)
            target_sl = entry_price + initial_risk
            if target_sl > current_sl:
                new_sl = target_sl
                print(f"⬆️ Trailing SL Update for {ticker} (Long): Moved to 1:1 Level")
        elif r_multiple >= 1.0:
             # Shift SL to Breakeven (Entry Price)
            if entry_price > current_sl:
                new_sl = entry_price
                print(f"⬆️ Trailing SL Update for {ticker} (Long): Moved to Breakeven")
                
        long_positions[ticker]['stop_loss'] = new_sl
        
        # B. Exit Conditions (Long)
        # 1. Hard SL Hit
        sl_hit = curr['Low'] <= new_sl
        # 2. Strategy Exit: EMA 5 crosses BELOW EMA 10
        strategy_exit = (curr['EMA_5'] < curr['EMA_10']) and (prev['EMA_5'] >= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            pnl = (exit_price - entry_price) * qty
            
            # Log Trade
            data["long_history"].append({
                "Ticker": ticker,
                "Type": "LONG EXIT",
                "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price,
                "Exit Price": round(exit_price, 2),
                "Qty": qty,
                "PnL": round(pnl, 2),
                "Reason": "Stop Loss" if sl_hit else "EMA 5 < EMA 10"
            })
            del long_positions[ticker]
            print(f"❌ CLOSED LONG: {ticker} | PnL: {pnl:.2f}")

    # --- SHORT POSITIONS ---
    for ticker in list(short_positions.keys()):
        curr, prev = fetch_data(ticker)
        if curr is None: continue
        
        pos = short_positions[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['initial_risk_per_share']
        current_sl = pos['stop_loss']
        
        # A. Trailing Stop Logic (Short)
        # For shorts, reward is Entry - Low
        reward = entry_price - curr['Low']
        r_multiple = reward / initial_risk if initial_risk > 0 else 0
        
        new_sl = current_sl
        if r_multiple >= 2.0:
            # Shift SL down to 1:1 Level (Entry - 1R)
            target_sl = entry_price - initial_risk
            if target_sl < current_sl:
                new_sl = target_sl
                print(f"⬇️ Trailing SL Update for {ticker} (Short): Moved to 1:1 Level")
        elif r_multiple >= 1.0:
            # Shift SL down to Breakeven (Entry Price)
            if entry_price < current_sl:
                new_sl = entry_price
                print(f"⬇️ Trailing SL Update for {ticker} (Short): Moved to Breakeven")

        short_positions[ticker]['stop_loss'] = new_sl
        
        # B. Exit Conditions (Short)
        # 1. Hard SL Hit (High > SL)
        sl_hit = curr['High'] >= new_sl
        # 2. Strategy Exit: EMA 5 crosses ABOVE EMA 10
        strategy_exit = (curr['EMA_5'] > curr['EMA_10']) and (prev['EMA_5'] <= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            pnl = (entry_price - exit_price) * qty # Short PnL = (Entry - Exit) * Qty
            
            # Log Trade
            data["short_history"].append({
                "Ticker": ticker,
                "Type": "SHORT EXIT",
                "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price,
                "Exit Price": round(exit_price, 2),
                "Qty": qty,
                "PnL": round(pnl, 2),
                "Reason": "Stop Loss" if sl_hit else "EMA 5 > EMA 10"
            })
            del short_positions[ticker]
            print(f"❌ CLOSED SHORT: {ticker} | PnL: {pnl:.2f}")

    # ---------------------------------------------------------
    # 2. CHECK NEW ENTRIES
    # ---------------------------------------------------------
    
    for ticker in WATCHLIST:
        # Skip if already in a position for this ticker
        if ticker in long_positions or ticker in short_positions:
            continue
            
        curr, prev = fetch_data(ticker)
        if curr is None: continue
        
        # --- LONG SETUP ---
        # Trend: SMA 100 > SMA 200, EMA 50 > SMA 100, EMA 21 > EMA 50
        long_trend = (curr['SMA_100'] > curr['SMA_200']) and \
                     (curr['EMA_50'] > curr['SMA_100']) and \
                     (curr['EMA_21'] > curr['EMA_50'])
        
        # Trigger: EMA 10 Crosses Above EMA 21
        long_trigger = (curr['EMA_10'] > curr['EMA_21']) and (prev['EMA_10'] <= prev['EMA_21'])
        
        if long_trend and long_trigger:
            entry_price = curr['Close']
            # Initial Stop Loss: 0.1% below EMA 21
            sl_price = curr['EMA_21'] * 0.999 
            risk_per_share = entry_price - sl_price
            
            if risk_per_share > 0:
                total_risk_amt = CAPITAL * RISK_PER_TRADE_PCT # ₹20,000
                qty = int(total_risk_amt / risk_per_share)
                
                if qty > 0:
                    long_positions[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2),
                        "qty": qty,
                        "stop_loss": round(sl_price, 2),
                        "initial_risk_per_share": round(risk_per_share, 2),
                        "current_price": round(entry_price, 2)
                    }
                    print(f"✅ OPEN LONG: {ticker} @ {entry_price} | Qty: {qty}")
        
        # --- SHORT SETUP ---
        # Trend: SMA 100 < SMA 200, EMA 50 < SMA 100, EMA 21 < EMA 50
        short_trend = (curr['SMA_100'] < curr['SMA_200']) and \
                      (curr['EMA_50'] < curr['SMA_100']) and \
                      (curr['EMA_21'] < curr['EMA_50'])
        
        # Trigger: EMA 10 Crosses Below EMA 21
        short_trigger = (curr['EMA_10'] < curr['EMA_21']) and (prev['EMA_10'] >= prev['EMA_21'])
        
        if short_trend and short_trigger:
            entry_price = curr['Close']
            # Initial Stop Loss: 0.1% above EMA 21
            sl_price = curr['EMA_21'] * 1.001
            risk_per_share = sl_price - entry_price # Risk is SL - Entry for shorts
            
            if risk_per_share > 0:
                total_risk_amt = CAPITAL * RISK_PER_TRADE_PCT
                qty = int(total_risk_amt / risk_per_share)
                
                if qty > 0:
                    short_positions[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2),
                        "qty": qty,
                        "stop_loss": round(sl_price, 2),
                        "initial_risk_per_share": round(risk_per_share, 2),
                        "current_price": round(entry_price, 2)
                    }
                    print(f"✅ OPEN SHORT: {ticker} @ {entry_price} | Qty: {qty}")

    # Save Updates
    data["long_positions"] = long_positions
    data["short_positions"] = short_positions
    save_portfolio(data)
    print("💾 Portfolio Updated.")

if __name__ == "__main__":
    run_bot()