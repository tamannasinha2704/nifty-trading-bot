import yfinance as yf
import pandas as pd
import pandas_ta as ta
import schedule
import time
import json
import requests
import os
from datetime import datetime, timedelta
import pytz

# --- CONSTANTS & CONFIG ---
CONFIG_FILE = "config.json"
TRADES_FILE = "trades.json"
HISTORY_FILE = "trade_history.json"
IST = pytz.timezone('Asia/Kolkata')
CONFIG = {}

def load_config():
    global CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            CONFIG = json.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")

def load_json(filename):
    if not os.path.exists(filename): return {} if filename == TRADES_FILE else []
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return {} if filename == TRADES_FILE else []

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram(message):
    """Sends text message to ALL recipients"""
    if not CONFIG.get('telegram', {}).get('enabled', False): return
    recipients = CONFIG['telegram'].get('recipients', [])
    for user in recipients:
        try:
            token = user['bot_token']
            chat_id = user['chat_id']
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message})
        except Exception as e:
            print(f"   >>> ❌ Telegram Failed: {e}")

def get_ist_time():
    return datetime.now(IST)

# --- HISTORY LOGGING ---
def log_trade_history(ticker, action, qty, price, pnl=0, reason=""):
    history = load_json(HISTORY_FILE)
    if not isinstance(history, list): history = []
    
    record = {
        "timestamp": get_ist_time().strftime('%Y-%m-%d %H:%M:%S'),
        "ticker": ticker,
        "action": action, # 'BUY', 'SELL', 'PARTIAL_SELL'
        "quantity": qty,
        "price": price,
        "pnl": pnl,
        "reason": reason
    }
    history.append(record)
    save_json(HISTORY_FILE, history)

# --- 1. SCHEDULING LOGIC ---
def is_entry_window():
    # Only trade on FRIDAYS between 3:15 PM and 3:30 PM
    now = get_ist_time()
    weekday = now.weekday() # 4 = Friday
    current_time = now.time()
    
    start_time = datetime.strptime("15:15", "%H:%M").time()
    end_time = datetime.strptime("15:30", "%H:%M").time()
    
    # Strict Friday Check
    if weekday == 4:
        if start_time <= current_time <= end_time:
            return True
            
    return False

def calculate_quantity(entry_price, sl_price):
    capital = CONFIG['strategy_settings']['capital']
    risk_pct = CONFIG['strategy_settings']['risk_per_trade_percent']
    risk_amount = capital * (risk_pct / 100)
    risk_per_share = entry_price - sl_price
    if risk_per_share <= 0: return 0
    return int(risk_amount / risk_per_share)

# --- STRICT EXIT CONDITIONS ---
def check_exit_conditions(ticker, trade_data, current_price, ema_fast, ema_slow):
    sl_price = trade_data['sl_price']
    
    # 1. Death Cross (EMA 5 < EMA 9)
    if ema_fast < ema_slow: 
        return "SELL_ALL", "EMA Death Cross (5 < 9)"
    
    # 2. Stop Loss
    if current_price <= sl_price: 
        return "SELL_ALL", f"Stop Loss Hit ({sl_price})"
    
    return None, None

def analyze_market():
    load_config()
    portfolio = load_json(TRADES_FILE)
    checking_entries = is_entry_window()
    now_str = get_ist_time().strftime('%H:%M')
    
    print(f"\n[{now_str}] Market Scan. Friday Entry Window: {checking_entries}")

    # Wake Up Signal (Only once per session)
    if checking_entries:
        print("🔔 Active Trading Window Open!")

    for ticker in CONFIG['watchlist']:
        try:
            df = yf.download(ticker, period="2y", interval="1wk", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            if len(df) < 55: continue

            df['EMA_F'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_fast'])
            df['EMA_S'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_slow'])
            df['EMA_T'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_trend'])
            df['EMA_L'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_long'])
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            c_price = float(curr['Close'])
            c_fast, c_slow = float(curr['EMA_F']), float(curr['EMA_S'])
            c_trend, c_long = float(curr['EMA_T']), float(curr['EMA_L'])
            p_fast, p_slow = float(prev['EMA_F']), float(prev['EMA_S'])
            p_trend, p_long = float(prev['EMA_T']), float(prev['EMA_L'])
            
            # --- EXIT LOGIC ---
            if ticker in portfolio:
                action, reason = check_exit_conditions(ticker, portfolio[ticker], c_price, c_fast, c_slow)
                
                if action == "SELL_ALL":
                    # Calculate PnL
                    entry_price = portfolio[ticker]['entry_price']
                    qty = portfolio[ticker]['quantity']
                    pnl = (c_price - entry_price) * qty
                    
                    msg = f"🔴 EXIT: {ticker}\nPrice: {c_price:.2f}\nPnL: ₹{pnl:.2f}\nReason: {reason}"
                    print(msg); send_telegram(msg)
                    
                    # Log to History & Remove from Portfolio
                    log_trade_history(ticker, "SELL", qty, c_price, pnl, reason)
                    del portfolio[ticker]
                    save_json(TRADES_FILE, portfolio)

            # --- ENTRY LOGIC (Only on Fridays) ---
            if checking_entries and ticker not in portfolio:
                cond_align = (c_slow > c_trend) and (c_trend > c_long)
                cond_cross = (c_fast > c_slow) and (p_fast <= p_slow)
                cond_rising = (c_fast > p_fast) and (c_slow > p_slow) and (c_trend > p_trend) and (c_long > p_long)
                
                if cond_align and cond_cross and cond_rising:
                    sl_price = c_trend * 0.999
                    qty = calculate_quantity(c_price, sl_price)
                    if qty > 0:
                        msg = f"🚀 BUY SIGNAL: {ticker}\nEntry: {c_price:.2f}\nSL: {sl_price:.2f}\nQty: {qty}"
                        print(msg); send_telegram(msg)
                        
                        portfolio[ticker] = {
                            "entry_date": datetime.now().strftime('%Y-%m-%d'),
                            "entry_time": datetime.now().strftime('%H:%M:%S'),
                            "entry_price": c_price, 
                            "quantity": qty,
                            "initial_sl": sl_price, 
                            "sl_price": sl_price, 
                            "status": "OPEN"
                        }
                        save_json(TRADES_FILE, portfolio)
                        log_trade_history(ticker, "BUY", qty, c_price, 0, "Entry Signal")
        except: continue

def scheduled_job():
    # This runs every 5 minutes
    analyze_market()

def friday_wake_up():
    # Just a heartbeat message to tell dad the bot is awake
    send_telegram("🔔 It is Friday! Bot is awake and scanning for trades (3:15 PM - 3:30 PM).")

if __name__ == "__main__":
    load_config()
    send_telegram(f"🤖 Bot Started & Ready\nTime: {get_ist_time().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. Regular Scan (Every 5 mins)
    schedule.every(5).minutes.do(scheduled_job)
    
    # 2. Friday Wake Up Alert (At 3:15 PM)
    schedule.every().friday.at("15:15").do(friday_wake_up)
    
    print("Scheduler active...")
    
    while True: 
        schedule.run_pending()
        time.sleep(1)