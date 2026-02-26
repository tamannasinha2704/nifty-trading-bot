import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- SETTINGS ---
INITIAL_CAPITAL = 2000000.0  # 20 Lakhs
RISK_PER_TRADE_PCT = 0.005   # 0.5% Risk per trade
BROKERAGE_RATE = 0.0015      # 0.15% per side
HARD_STOP_PCT = 0.02         # 2% Hard Stop Loss

# yfinance only allows 1h data for the last 730 days. 
# Calculating dates dynamically for the max 1h window.
END_DATE = datetime.today().strftime('%Y-%m-%d')
START_DATE = (datetime.today() - timedelta(days=729)).strftime('%Y-%m-%d')

# Target Ticker: Nifty 50 Spot Index
TICKER = "^NSEI" 

def calculate_t3(df, length=8, v_factor=0.7):
    """
    Calculates Tillson T3 Moving Average.
    """
    # Calculate EMA constants
    a = v_factor
    c1 = -a**3
    c2 = 3*a**2 + 3*a**3
    c3 = -6*a**2 - 3*a - 3*a**3
    c4 = 1 + 3*a + a**3 + 3*a**2

    # Calculate sequential EMAs
    e1 = df['Close'].ewm(span=length, adjust=False).mean()
    e2 = e1.ewm(span=length, adjust=False).mean()
    e3 = e2.ewm(span=length, adjust=False).mean()
    e4 = e3.ewm(span=length, adjust=False).mean()
    e5 = e4.ewm(span=length, adjust=False).mean()
    e6 = e5.ewm(span=length, adjust=False).mean()

    # T3 Formula
    df['T3'] = c1*e6 + c2*e5 + c3*e4 + c4*e3
    return df

def run_backtest(ticker):
    # Download Hourly Data
    df = yf.download(ticker, start=START_DATE, end=END_DATE, interval="1h", progress=False)
    
    if df.empty or len(df) < 50: 
        return []
    
    # Flatten MultiIndex if necessary (recent yfinance updates)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    # --- INDICATOR CALCULATIONS ---
    df = calculate_t3(df, length=8, v_factor=0.7)
    df.dropna(inplace=True)
    
    # --- TRADING LOGIC ---
    trades = []
    position = 0 # 1 for Long, -1 for Short, 0 for Flat
    entry_price = 0.0
    entry_date = None
    qty = 0
    
    for i in range(1, len(df)):
        curr_date = df.index[i]
        close = df['Close'].iloc[i]
        high = df['High'].iloc[i]
        low = df['Low'].iloc[i]
        t3_val = df['T3'].iloc[i]
        
        # Check Crosses for Entry/Exit signals
        bullish_close = close > t3_val
        bearish_close = close < t3_val
        
        if position == 1: # CURRENTLY LONG
            hard_sl_price = entry_price * (1 - HARD_STOP_PCT)
            
            # 1. Check Hard Stop Loss (Intra-candle via Low)
            if low <= hard_sl_price:
                exit_price = hard_sl_price
                exit_reason = "2% SL Hit"
                
                gross_pnl = (exit_price - entry_price) * qty
                buy_val = entry_price * qty
                sell_val = exit_price * qty
                brokerage = (buy_val * BROKERAGE_RATE) + (sell_val * BROKERAGE_RATE)
                net_pnl = gross_pnl - brokerage
                
                trades.append(create_trade_log(ticker, "LONG", entry_date, curr_date, entry_price, exit_price, qty, gross_pnl, brokerage, net_pnl, buy_val, exit_reason))
                position = 0 # Flat
                
            # 2. Check Reversal (Candle Close Below T3)
            elif bearish_close:
                exit_price = close
                exit_reason = "T3 Cross Down"
                
                gross_pnl = (exit_price - entry_price) * qty
                buy_val = entry_price * qty
                sell_val = exit_price * qty
                brokerage = (buy_val * BROKERAGE_RATE) + (sell_val * BROKERAGE_RATE)
                net_pnl = gross_pnl - brokerage
                
                trades.append(create_trade_log(ticker, "LONG", entry_date, curr_date, entry_price, exit_price, qty, gross_pnl, brokerage, net_pnl, buy_val, exit_reason))
                
                # Immediately Enter Short
                position, entry_price, entry_date, qty = enter_trade(curr_date, close, -1)

        elif position == -1: # CURRENTLY SHORT
            hard_sl_price = entry_price * (1 + HARD_STOP_PCT)
            
            # 1. Check Hard Stop Loss (Intra-candle via High)
            if high >= hard_sl_price:
                exit_price = hard_sl_price
                exit_reason = "2% SL Hit"
                
                gross_pnl = (entry_price - exit_price) * qty
                sell_val = entry_price * qty
                buy_val = exit_price * qty
                brokerage = (buy_val * BROKERAGE_RATE) + (sell_val * BROKERAGE_RATE)
                net_pnl = gross_pnl - brokerage
                
                trades.append(create_trade_log(ticker, "SHORT", entry_date, curr_date, entry_price, exit_price, qty, gross_pnl, brokerage, net_pnl, sell_val, exit_reason))
                position = 0 # Flat
                
            # 2. Check Reversal (Candle Close Above T3)
            elif bullish_close:
                exit_price = close
                exit_reason = "T3 Cross Up"
                
                gross_pnl = (entry_price - exit_price) * qty
                sell_val = entry_price * qty
                buy_val = exit_price * qty
                brokerage = (buy_val * BROKERAGE_RATE) + (sell_val * BROKERAGE_RATE)
                net_pnl = gross_pnl - brokerage
                
                trades.append(create_trade_log(ticker, "SHORT", entry_date, curr_date, entry_price, exit_price, qty, gross_pnl, brokerage, net_pnl, sell_val, exit_reason))
                
                # Immediately Enter Long
                position, entry_price, entry_date, qty = enter_trade(curr_date, close, 1)

        elif position == 0: # CURRENTLY FLAT
            if bullish_close:
                position, entry_price, entry_date, qty = enter_trade(curr_date, close, 1)
            elif bearish_close:
                position, entry_price, entry_date, qty = enter_trade(curr_date, close, -1)

    return trades

def enter_trade(date, price, pos_type):
    """
    Helper to calculate position sizing for entering a trade.
    pos_type: 1 for Long, -1 for Short
    """
    risk_amount = INITIAL_CAPITAL * RISK_PER_TRADE_PCT # Fix amount to risk
    risk_per_share = price * HARD_STOP_PCT # Distance to hard stop
    
    qty = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    return pos_type if qty > 0 else 0, price, date, qty

def create_trade_log(ticker, type, entry_date, exit_date, entry_price, exit_price, qty, gross_pnl, brokerage, net_pnl, base_val, reason):
    """
    Helper to format the trade record dict consistently.
    """
    return {
        'Ticker': ticker,
        'Type': type,
        'Entry Date': entry_date.strftime('%Y-%m-%d %H:%M'),
        'Exit Date': exit_date.strftime('%Y-%m-%d %H:%M'),
        'Exit Reason': reason,
        'Entry Price': round(entry_price, 2),
        'Exit Price': round(exit_price, 2),
        'Qty': qty,
        'Gross P/L': round(gross_pnl, 2),
        'Brokerage': round(brokerage, 2),
        'Net P/L': round(net_pnl, 2),
        'Return %': round((net_pnl / base_val) * 100, 2) if base_val > 0 else 0
    }

if __name__ == "__main__":
    print(f"\n🚀 Starting HOURLY T3(8) Backtest on {TICKER}...")
    print(f"📅 Period: {START_DATE} to {END_DATE} (Max 1hr Data Limit)")
    print(f"💰 Capital: ₹{INITIAL_CAPITAL:,.0f} | Stop Loss: {HARD_STOP_PCT*100}% | Brokerage: {BROKERAGE_RATE*100}%")
    print("-" * 65)
    
    try:
        all_trades = run_backtest(TICKER)
    except Exception as e:
        print(f"❌ Error during backtest: {e}")
        all_trades = []

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
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
        
        long_trades = results_df[results_df['Type'] == 'LONG']
        short_trades = results_df[results_df['Type'] == 'SHORT']
        
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
        print(f"Total Trades:           {total_trades} (Long: {len(long_trades)}, Short: {len(short_trades)})")
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
        csv_name = "Hourly_T3_Nifty_Backtest.csv"
        results_df.drop(columns=['Peak', 'Drawdown'], inplace=True) # Clean export
        results_df.to_csv(csv_name, index=False)
        print(f"✅ Detailed trade log saved to '{csv_name}'")