import yfinance as yf
import schedule
import time
from datetime import datetime

print("--- Nifty Bot Initialized ---")

def run_bot():
    print(f"\n[Time: {datetime.now().strftime('%H:%M:%S')}] Checking Market...")
    
    # Fetch 1 stock to test connection (Reliance)
    try:
        ticker = "RELIANCE.NS"
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        
        if not df.empty:
            # FIX: Use .iloc[0] to safely get the value as a float
            latest_price = df['Close'].iloc[-1]
            print(f"Success! {ticker} Current Price: {float(latest_price.iloc[0]):.2f}")
        else:
            print("Data fetched but empty. Market might be closed or ticker invalid.")
            
    except Exception as e:
        print(f"Connection Error: {e}")

# Run once immediately
run_bot()

# Schedule it
schedule.every(1).minutes.do(run_bot)

print("Scheduler started. Waiting for next update...")

while True:
    schedule.run_pending()
    time.sleep(1)