import yfinance as yf
import pandas as pd
import numpy as np
import os

# --- SETTINGS ---
INITIAL_CAPITAL = 2000000.0  # 20 Lakhs
RISK_PER_TRADE_PCT = 0.005   # 0.5% Risk per trade
BROKERAGE_RATE = 0.0015      # 0.15% per side
START_DATE = "2022-01-01"
END_DATE = "2026-01-01"

# Nifty 50 Watchlist (Auto-fallback)
NIFTY_50 = [
    'RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'ITC.NS', 'TCS.NS', 'LT.NS', 
    'BHARTIARTL.NS', 'AXISBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'HINDUNILVR.NS', 'BAJFINANCE.NS', 
    'M&M.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'HCLTECH.NS', 'TITAN.NS', 'SUNPHARMA.NS', 'NTPC.NS', 
    'TATASTEEL.NS', 'ULTRACEMCO.NS', 'POWERGRID.NS', 'ONGC.NS', 'BAJAJFINSV.NS', 'NESTLEIND.NS', 
    'ADANIENT.NS', 'INDUSINDBK.NS', 'GRASIM.NS', 'ADANIPORTS.NS', 'HINDALCO.NS', 'COALINDIA.NS', 
    'JSWSTEEL.NS', 'DRREDDY.NS', 'TATAMOTORS.NS', 'APOLLOHOSP.NS', 'TRENT.NS', 'EICHERMOT.NS', 
    'CIPLA.NS', 'DIVISLAB.NS', 'BPCL.NS', 'TECHM.NS', 'WIPRO.NS', 'BRITANNIA.NS', 'LTIM.NS', 
    'SHRIRAMFIN.NS', 'BAJAJ-AUTO.NS', 'HEROMOTOCO.NS', 'TATACONSUM.NS', 'HDFCLIFE.NS'
]

def calculate_supertrend(df, period=10, multiplier=3):
    """
    Custom optimized Supertrend calculation using numpy/pandas.
    Returns the DataFrame with 'Supertrend' and 'Supertrend_Dir' columns.
    """
    # ATR Calculation
    df['tr0'] = abs(df['High'] - df['Low'])
    df['tr1'] = abs(df['High'] - df['Close'].shift(1))
    df['tr2'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR'] = df['TR'].ewm(alpha=1/period, adjust=False).mean()
    
    # Basic Bands
    hl2 = (df['High'] + df['Low']) / 2
    df['Basic_Upper'] = hl2 + (multiplier * df['ATR'])
    df['Basic_Lower'] = hl2 - (multiplier * df['ATR'])
    
    # Final Bands Initialization
    df['Final_Upper'] = df['Basic_Upper']
    df['Final_Lower'] = df['Basic_Lower']
    df['Supertrend'] = np.nan
    
    # Iterative calculation for Supertrend logic
    for i in range(period, len(df)):
        # Upper Band Logic
        if df['Basic_Upper'].iloc[i] < df['Final_Upper'].iloc[i-1] or \
           df['Close'].iloc[i-1] > df['Final_Upper'].iloc[i-1]:
            df.loc[df.index[i], 'Final_Upper'] = df['Basic_Upper'].iloc[i]
        else:
            df.loc[df.index[i], 'Final_Upper'] = df['Final_Upper'].iloc[i-1]
            
        # Lower Band Logic
        if df['Basic_Lower'].iloc[i] > df['Final_Lower'].iloc[i-1] or \
           df['Close'].iloc[i-1] < df['Final_Lower'].iloc[i-1]:
            df.loc[df.index[i], 'Final_Lower'] = df['Basic_Lower'].iloc[i]
        else:
            df.loc[df.index[i], 'Final_Lower'] = df['Final_Lower'].iloc[i-1]
            
    # Supertrend Selection
    df['Supertrend'] = np.where(df['Close'] <= df['Final_Upper'], df['Final_Upper'], df['Final_Lower'])
    
    # Determine Trend Direction (True = Uptrend/Green, False = Downtrend/Red)
    # Refined logic: If Close > Supertrend, it's Uptrend.
    # Note: We need a loop or careful vectorization because Supertrend value itself flips.
    # A simple approach for backtesting:
    conditions = [
        (df['Close'] > df['Final_Upper'].shift(1)), 
        (df['Close'] < df['Final_Lower'].shift(1))
    ]
    choices = [True, False] # True = Bullish, False = Bearish
    
    # Simple recursive check (Vectorized approximation often fails on flips, so we use hybrid)
    # However, strictly for the Buy condition "Close > Supertrend", we can just compare Close vs Calculated ST
    
    # Re-running the standard logic to ensure 'Supertrend' column is accurate for signals
    st = [np.nan] * len(df)
    uptrend = True
    
    for i in range(period, len(df)):
        if uptrend:
            st[i] = df['Final_Lower'].iloc[i]
            if df['Close'].iloc[i] < st[i]:
                uptrend = False
                st[i] = df['Final_Upper'].iloc[i]
        else:
            st[i] = df['Final_Upper'].iloc[i]
            if df['Close'].iloc[i] > st[i]:
                uptrend = True
                st[i] = df['Final_Lower'].iloc[i]
                
    df['Supertrend'] = st
    return df

def run_backtest(ticker):
    # Download Weekly Data
    df = yf.download(ticker, start=START_DATE, end=END_DATE, interval="1wk", progress=False)
    
    if df.empty or len(df) < 60: 
        return []
    
    # Flatten MultiIndex if necessary
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # --- INDICATOR CALCULATIONS ---
    # 1. Supertrend (10, 3)
    df = calculate_supertrend(df, period=10, multiplier=3)
    
    # 2. SMA 50 on HIGH
    df['SMA_50_High'] = df['High'].rolling(window=50).mean()
    
    # 3. Previous Candle High
    df['Prev_High'] = df['High'].shift(1)
    
    df.dropna(inplace=True)
    
    # --- TRADING LOGIC ---
    trades = []
    in_position = False
    entry_price = 0.0
    qty = 0
    risk_per_share = 0.0
    
    for i in range(1, len(df)):
        curr_date = df.index[i]
        close = df['Close'].iloc[i]
        st_val = df['Supertrend'].iloc[i]
        sma_50 = df['SMA_50_High'].iloc[i]
        prev_high = df['Prev_High'].iloc[i]
        
        # Supertrend Filter: Close MUST be above Supertrend (Bullish)
        is_uptrend = close > st_val
        
        if in_position:
            # EXIT CONDITION: Close below Supertrend
            if not is_uptrend: # Close crossed below Supertrend
                exit_price = close
                gross_pnl = (exit_price - entry_price) * qty
                
                # Brokerage: 0.15% on Buy Value + 0.15% on Sell Value
                buy_val = entry_price * qty
                sell_val = exit_price * qty
                brokerage = (buy_val * BROKERAGE_RATE) + (sell_val * BROKERAGE_RATE)
                
                net_pnl = gross_pnl - brokerage
                
                trades.append({
                    'Ticker': ticker,
                    'Entry Date': entry_date,
                    'Exit Date': curr_date.strftime('%Y-%m-%d'),
                    'Entry Price': round(entry_price, 2),
                    'Exit Price': round(exit_price, 2),
                    'Qty': qty,
                    'Gross P/L': round(gross_pnl, 2),
                    'Brokerage': round(brokerage, 2),
                    'Net P/L': round(net_pnl, 2),
                    'Return %': round((net_pnl / buy_val) * 100, 2)
                })
                in_position = False
                
        else:
            # BUY CONDITIONS
            # 1. Close > Supertrend
            # 2. Close within 5% above Supertrend (Close <= ST * 1.05)
            # 3. Close > Prev Candle High
            # 4. Close > SMA 50 (High)
            
            c1 = is_uptrend
            c2 = close <= (st_val * 1.05)
            c3 = close > prev_high
            c4 = close > sma_50
            
            if c1 and c2 and c3 and c4:
                entry_price = close
                entry_date = curr_date.strftime('%Y-%m-%d')
                
                # Position Sizing: 0.5% Risk of Total Capital (Fixed 20L Base)
                # Stop Loss is the Supertrend Value
                sl_price = st_val
                risk_per_share = entry_price - sl_price
                
                if risk_per_share > 0:
                    risk_amount = INITIAL_CAPITAL * RISK_PER_TRADE_PCT # ₹10,000
                    qty = int(risk_amount / risk_per_share)
                    
                    if qty > 0:
                        in_position = True
                        
    return trades

if __name__ == "__main__":
    print(f"\n🚀 Starting WEEKLY Supertrend Backtest on Nifty 50...")
    print(f"📅 Period: {START_DATE} to {END_DATE}")
    print(f"💰 Capital: ₹{INITIAL_CAPITAL:,.0f} | Risk: {RISK_PER_TRADE_PCT*100}% | Brokerage: {BROKERAGE_RATE*100}%")
    print("-" * 60)
    
    all_trades = []
    
    for idx, ticker in enumerate(NIFTY_50, 1):
        print(f"⏳ [{idx}/{len(NIFTY_50)}] Processing {ticker}...")
        try:
            stock_trades = run_backtest(ticker)
            all_trades.extend(stock_trades)
        except Exception as e:
            print(f"❌ Error on {ticker}: {e}")

    # --- RESULTS AGGREGATION ---
    if not all_trades:
        print("\n📉 No trades found matching criteria.")
    else:
        results_df = pd.DataFrame(all_trades)
        
        # Sort chronologically
        results_df.sort_values(by='Exit Date', inplace=True)
        
        # Calculate Equity Curve for Drawdown
        results_df['Cumulative P/L'] = results_df['Net P/L'].cumsum()
        results_df['Equity'] = INITIAL_CAPITAL + results_df['Cumulative P/L']
        results_df['Peak'] = results_df['Equity'].cummax()
        results_df['Drawdown'] = (results_df['Peak'] - results_df['Equity']) / results_df['Peak'] * 100
        
        # Metrics
        total_trades = len(results_df)
        winners = results_df[results_df['Net P/L'] > 0]
        losers = results_df[results_df['Net P/L'] <= 0]
        
        win_count = len(winners)
        loss_count = len(losers)
        win_rate = (win_count / total_trades) * 100
        
        gross_pl = results_df['Gross P/L'].sum()
        total_brokerage = results_df['Brokerage'].sum()
        net_pl = results_df['Net P/L'].sum()
        
        avg_pl = results_df['Net P/L'].mean()
        max_dd = results_df['Drawdown'].max()
        
        final_capital = INITIAL_CAPITAL + net_pl
        roi = (net_pl / INITIAL_CAPITAL) * 100

        print("\n" + "="*50)
        print("      📊 STRATEGY PERFORMANCE REPORT")
        print("="*50)
        print(f"Total Trades:           {total_trades}")
        print(f"Win Rate:               {win_rate:.2f}% ({win_count} W / {loss_count} L)")
        print("-" * 50)
        print(f"Initial Capital:        ₹{INITIAL_CAPITAL:,.2f}")
        print(f"Final Capital:          ₹{final_capital:,.2f}")
        print(f"Net Profit/Loss:        ₹{net_pl:,.2f} ({roi:.2f}%)")
        print(f"Gross Profit/Loss:      ₹{gross_pl:,.2f}")
        print(f"Total Brokerage:        ₹{total_brokerage:,.2f}")
        print("-" * 50)
        print(f"Avg P/L per Trade:      ₹{avg_pl:,.2f}")
        print(f"Max Drawdown:           {max_dd:.2f}%")
        print("="*50)
        
        # Export
        csv_name = "Weekly_Supertrend_Backtest.csv"
        results_df.drop(columns=['Peak', 'Drawdown'], inplace=True) # Clean export
        results_df.to_csv(csv_name, index=False)
        print(f"✅ Detailed trade log saved to '{csv_name}'")