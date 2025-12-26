import yfinance as yf
import pandas as pd
import pandas_ta as ta
import json
import time

# --- CONFIGURATION ---
# We force these settings for the backtest to ensure deep history
TIMEFRAME = "1wk" 
HISTORY_YEARS = "5y"

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def backtest_stock(ticker, config):
    try:
        # 1. Fetch Data
        df = yf.download(ticker, period=HISTORY_YEARS, interval=TIMEFRAME, progress=False)
        
        # Clean Data
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty or len(df) < 50:
            return []

        # 2. Calculate Indicators (Using config settings)
        inds = config['indicators']
        df['EMA_F'] = ta.ema(df['Close'], length=inds['ema_fast'])
        df['EMA_S'] = ta.ema(df['Close'], length=inds['ema_slow'])
        df['EMA_T'] = ta.ema(df['Close'], length=inds['ema_trend'])
        df['EMA_L'] = ta.ema(df['Close'], length=inds['ema_long'])

        trades = []
        in_position = False
        buy_price = 0
        buy_date = None

        # 3. Walk through history (Simulate day by day)
        # We start from index 50 to ensure EMAs are calculated
        for i in range(50, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            
            # Extract values for cleaner code
            c_price = float(curr['Close'])
            c_fast, c_slow = float(curr['EMA_F']), float(curr['EMA_S'])
            c_trend, c_long = float(curr['EMA_T']), float(curr['EMA_L'])
            
            p_fast, p_slow = float(prev['EMA_F']), float(prev['EMA_S'])
            p_trend, p_long = float(prev['EMA_T']), float(prev['EMA_L'])

            # --- LOGIC ---
            
            # Check BUY Signal (If not already in position)
            if not in_position:
                cond_align = (c_slow > c_trend) and (c_trend > c_long)
                cond_cross = (c_fast > c_slow) and (p_fast <= p_slow)
                cond_rising = (c_fast > p_fast) and (c_slow > p_slow) and \
                              (c_trend > p_trend) and (c_long > p_long)
                
                if cond_align and cond_cross and cond_rising:
                    buy_price = c_price
                    buy_date = df.index[i]
                    in_position = True
            
            # Check SELL Signal (If we ARE in a position)
            # Strategy: Exit when Fast EMA crosses BELOW Slow EMA
            elif in_position:
                if c_fast < c_slow:
                    sell_price = c_price
                    profit = ((sell_price - buy_price) / buy_price) * 100
                    
                    trades.append({
                        "Ticker": ticker,
                        "Buy Date": buy_date.strftime('%Y-%m-%d'),
                        "Sell Date": df.index[i].strftime('%Y-%m-%d'),
                        "Buy Price": round(buy_price, 2),
                        "Sell Price": round(sell_price, 2),
                        "Profit %": round(profit, 2)
                    })
                    
                    in_position = False # Ready to look for new trades

        return trades

    except Exception as e:
        print(f"Error on {ticker}: {e}")
        return []

def run_backtest():
    print("--- ⏳ Starting Time Machine (5 Years) ---")
    config = load_config()
    watchlist = config['watchlist']
    
    all_trades = []
    
    print(f"Testing {len(watchlist)} stocks. This may take 1-2 minutes...")
    
    for i, ticker in enumerate(watchlist):
        print(f"\r[{i+1}/{len(watchlist)}] Analying {ticker}...", end="")
        trades = backtest_stock(ticker, config)
        all_trades.extend(trades)
        
    print("\n\n--- 📊 BACKTEST RESULTS ---")
    
    if not all_trades:
        print("No trades found in history.")
        return

    # Convert to DataFrame for analysis
    results = pd.DataFrame(all_trades)
    
    # Calculate Metrics
    total_trades = len(results)
    winners = results[results['Profit %'] > 0]
    losers = results[results['Profit %'] <= 0]
    
    win_rate = (len(winners) / total_trades) * 100
    avg_profit = results['Profit %'].mean()
    total_return = results['Profit %'].sum() # Simple sum (not compounded)
    
    print(f"Total Trades:      {total_trades}")
    print(f"Win Rate:          {win_rate:.2f}%")
    print(f"Average Return:    {avg_profit:.2f}% per trade")
    print(f"Best Trade:        {results['Profit %'].max()}% ({results.loc[results['Profit %'].idxmax()]['Ticker']})")
    print(f"Worst Trade:       {results['Profit %'].min()}%")
    
    # Save detailed log
    results.to_csv("backtest_results.csv", index=False)
    print(f"\nDetailed trade log saved to 'backtest_results.csv'")

if __name__ == "__main__":
    run_backtest()