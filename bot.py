import yfinance as yf
import pandas as pd
import pandas_ta as ta
import schedule
import time
import json
import requests
from datetime import datetime
import pytz  # <--- NEW: Handles Timezones
import os

# --- GLOBAL CONFIG VARIABLE ---
CONFIG = {}
LOG_FILE = "paper_trades.csv"

# Define IST Timezone
IST = pytz.timezone('Asia/Kolkata')

def load_config():
    """Loads settings from config.json"""
    global CONFIG
    try:
        with open('config.json', 'r') as f:
            CONFIG = json.load(f)
    except Exception as e:
        print(f"❌ Error loading config.json: {e}")
        exit()

def send_telegram_alert(message):
    """Sends a message to your Telegram"""
    if not CONFIG['telegram']['enabled']: return

    token = CONFIG['telegram']['bot_token']
    chat_id = CONFIG['telegram']['chat_id']
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        data = {"chat_id": chat_id, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print(f"   >>> ❌ Telegram Failed: {e}")

def get_current_time_ist():
    """Returns the current time in IST"""
    return datetime.now(IST)

def is_market_open():
    if CONFIG['strategy_settings']['test_mode']: return True
    
    now_ist = get_current_time_ist()
    
    # Check Weekend (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5: return False 
    
    # Check Time (09:15 to 15:30)
    current_time = now_ist.time()
    market_start = datetime.strptime("09:15", "%H:%M").time()
    market_end = datetime.strptime("15:30", "%H:%M").time()
    
    return market_start <= current_time <= market_end

def save_signal(ticker, price, signal_type, reason):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a") as f:
        if not file_exists: f.write("Date,Time,Ticker,Price,Signal,Reason\n")
        now = get_current_time_ist()
        f.write(f"{now.strftime('%Y-%m-%d')},{now.strftime('%H:%M:%S')},{ticker},{price},{signal_type},{reason}\n")
    print(f"   >>> 📝 Trade Saved to {LOG_FILE}")

def clean_data(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df if not df.empty else None

def check_nifty_trend():
    try:
        tf = CONFIG['strategy_settings']['timeframe']
        trend_ema = CONFIG['indicators']['ema_trend']
        
        df = yf.download("^NSEI", period="1y", interval=tf, progress=False)
        df = clean_data(df)
        if df is None or len(df) < 25: return False

        df['EMA_Trend'] = ta.ema(df['Close'], length=trend_ema)
        latest = df.iloc[-1]
        
        close = float(latest['Close'])
        ema_val = float(latest['EMA_Trend'])
        
        status = "BULLISH 🟢" if close > ema_val else "BEARISH 🔴"
        print(f"\n[Market Status] Nifty 50 is {status} (Price: {close:.0f} | EMA{trend_ema}: {ema_val:.0f})")
        return close > ema_val
    except Exception as e:
        print(f"[Error] Nifty Check Failed: {e}")
        return False

def analyze_stock(ticker):
    try:
        tf = CONFIG['strategy_settings']['timeframe']
        inds = CONFIG['indicators']
        
        df = yf.download(ticker, period="2y", interval=tf, progress=False)
        df = clean_data(df)
        
        if df is None or len(df) < 55: return False 

        # Indicators
        df['EMA_F'] = ta.ema(df['Close'], length=inds['ema_fast'])
        df['EMA_S'] = ta.ema(df['Close'], length=inds['ema_slow'])
        df['EMA_T'] = ta.ema(df['Close'], length=inds['ema_trend'])
        df['EMA_L'] = ta.ema(df['Close'], length=inds['ema_long'])

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        c_price = float(curr['Close'])
        c_fast, c_slow = float(curr['EMA_F']), float(curr['EMA_S'])
        c_trend, c_long = float(curr['EMA_T']), float(curr['EMA_L'])
        p_fast, p_slow = float(prev['EMA_F']), float(prev['EMA_S'])
        p_trend, p_long = float(prev['EMA_T']), float(prev['EMA_L'])

        # --- 1. BUY LOGIC ---
        cond_align = (c_slow > c_trend) and (c_trend > c_long)
        cond_cross_up = (c_fast > c_slow) and (p_fast <= p_slow)
        cond_rising = (c_fast > p_fast) and (c_slow > p_slow) and \
                      (c_trend > p_trend) and (c_long > p_long)

        if cond_align and cond_cross_up and cond_rising:
            msg = f"🚀 BUY SIGNAL: {ticker}\nPrice: {c_price:.2f}\nStrategy: 4-EMA Buy"
            print(f"\n{msg}")
            save_signal(ticker, c_price, "BUY", "4-EMA Crossover")
            send_telegram_alert(msg)
            return True

        # --- 2. SELL LOGIC ---
        cond_cross_down = (c_fast < c_slow) and (p_fast >= p_slow)
        
        if cond_cross_down:
            msg = f"🔻 SELL SIGNAL: {ticker}\nPrice: {c_price:.2f}\nReason: EMA 5 crossed below EMA 9"
            print(f"\n{msg}")
            save_signal(ticker, c_price, "SELL", "EMA 5 < EMA 9")
            send_telegram_alert(msg)
            return True
        
        return False

    except Exception:
        return False

def run_scanner():
    load_config()
    now_ist = get_current_time_ist()
    now_str = now_ist.strftime('%H:%M:%S')
    
    if not is_market_open():
        print(f"\r[{now_str} IST] Market Closed. Waiting...", end="")
        return

    print(f"\n[{now_str} IST] Scanning {len(CONFIG['watchlist'])} stocks...", end="", flush=True)
    
    if not check_nifty_trend():
        print(">>> Nifty is Bearish. Skipping stocks.")
        return

    signals_found = 0
    for stock in CONFIG['watchlist']:
        if analyze_stock(stock):
            signals_found += 1
            
    print(f" Done. {signals_found} Signals found.")

# --- EXECUTION ---
load_config()
print(f"🤖 Bot Started. Timezone: Asia/Kolkata")
send_telegram_alert(f"🤖 Bot Deployed! Time: {get_current_time_ist().strftime('%H:%M IST')}")

run_scanner()
schedule.every(CONFIG['strategy_settings']['scan_interval_minutes']).minutes.do(run_scanner)

print("\nScheduler active. Ctrl+C to stop.")
while True:
    schedule.run_pending()
    time.sleep(1)