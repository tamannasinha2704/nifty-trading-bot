import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np

# --- CONFIGURATION ---
CONFIG = {
    # Strategy Parameters
    "sma_fast": 50,
    "sma_slow": 200,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    
    # Target
    "ticker": "SBIN.NS",
    "start_date": "2023-01-01",  # CHANGED: Start 1 year early for indicators
    "trade_start_date": "2024-01-01", # NEW: When we actually start trading
    "end_date": "2025-12-31"
}

trade_log = []
active_trade = None # Stores current trade details if we are holding

def calculate_dema(series, length):
    """Calculates Double EMA: 2*EMA - EMA(EMA)"""
    ema1 = ta.ema(series, length=length)
    ema2 = ta.ema(ema1, length=length)
    return (2 * ema1) - ema2

def add_indicators(df):
    # 1. SMAs
    df['SMA50'] = ta.sma(df['Close'], length=CONFIG['sma_fast'])
    df['SMA200'] = ta.sma(df['Close'], length=CONFIG['sma_slow'])
    
    # 2. MACD DEMA Logic
    df['DEMA_Slow'] = calculate_dema(df['Close'], CONFIG['macd_slow'])
    df['DEMA_Fast'] = calculate_dema(df['Close'], CONFIG['macd_fast'])
    
    df['MACD_Line'] = df['DEMA_Fast'] - df['DEMA_Slow']
    df['Signal_Line'] = calculate_dema(df['MACD_Line'], CONFIG['macd_signal'])
    
    # 3. Helper for Rising/Falling
    df['Prev_Signal'] = df['Signal_Line'].shift(1)
    
    return df

def run_backtest():
    global active_trade
    print(f"🚀 Starting SBIN (1 Share) Backtest...")
    print(f"📅 Period: {CONFIG['start_date']} to Now")
    
    # 1. Download Data
    try:
        df = yf.download(CONFIG['ticker'], start=CONFIG['start_date'], interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        if len(df) < 50:
            print("❌ Not enough data.")
            return

        df = add_indicators(df)
        df.dropna(inplace=True)
    except Exception as e:
        print(f"Error: {e}")
        return

 # 2. Loop through Candles
    for i in range(len(df)):
        current_date = df.index[i]
        row = df.iloc[i]

        # SKIP TRADING if we are before our target start date (2024)
        if current_date < pd.Timestamp(CONFIG['trade_start_date']):
            continue 

        # ... (Rest of your Buy/Sell logic remains exactly the same)
        
        # --- SELL LOGIC (Check Exit First) ---
        if active_trade:
            # Condition: Signal Line Falling
            cond_falling = row['Signal_Line'] < row['Prev_Signal']
            
            if cond_falling:
                exit_price = row['Close'] # 3:27 PM Execution
                pnl = exit_price - active_trade['entry_price'] # Profit on 1 share
                
                trade_log.append({
                    'Entry Date': str(active_trade['entry_date'].date()),
                    'Exit Date': str(current_date.date()),
                    'Type': 'SELL',
                    'Entry Price': active_trade['entry_price'],
                    'Exit Price': exit_price,
                    'P&L (1 Share)': pnl,
                    'Reason': 'DEMA Falling'
                })
                active_trade = None # Reset state (Flat)
                continue

        # --- BUY LOGIC (Check Entry) ---
        if active_trade is None:
            # Conditions:
            # 1. Price > SMA 50
            # 2. Price > SMA 200
            # 3. SMA 50 > SMA 200
            # 4. Signal Line Rising
            
            cond_price_sma = (row['Close'] > row['SMA50']) and (row['Close'] > row['SMA200'])
            cond_alignment = (row['SMA50'] > row['SMA200'])
            cond_rising = (row['Signal_Line'] > row['Prev_Signal'])
            
            if cond_price_sma and cond_alignment and cond_rising:
                active_trade = {
                    'entry_price': row['Close'],
                    'entry_date': current_date
                }

    # --- RESULTS ---
    results_df = pd.DataFrame(trade_log)
    
    print("\n" + "="*30)
    print("📊 SBIN STRATEGY REPORT")
    print("="*30)
    
    if results_df.empty:
        print("No trades triggered.")
        return

    total_profit = results_df['P&L (1 Share)'].sum()
    wins = results_df[results_df['P&L (1 Share)'] > 0]
    win_rate = (len(wins) / len(results_df)) * 100
    
    print(f"Total Net P&L (1 Share):  ₹{total_profit:.2f}")
    print(f"Total Trades:             {len(results_df)}")
    print(f"Win Rate:                 {win_rate:.2f}%")
    print("-" * 20)
    
    # Save to Excel
    filename = "sbin_backtest_simple.xlsx"
    results_df.to_excel(filename, index=False)
    print(f"✅ Log saved to '{filename}'")

if __name__ == "__main__":
    run_backtest()