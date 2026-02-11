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

# --- CONSTANTS ---
CONFIG_FILE = "config.json"
TRADES_FILE = "trades.json"
HISTORY_FILE = "trade_history.json"
SIGNALS_FILE = "signals.json"  # <--- NEW FILE
IST = pytz.timezone('Asia/Kolkata')
CONFIG = {}

# --- UTILITIES ---
def load_config():
    global CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f: CONFIG = json.load(f)
    except: pass

def load_json(filename):
    if not os.path.exists(filename): return [] if filename in [HISTORY_FILE, SIGNALS_FILE] else {}
    try:
        with open(filename, 'r') as f: return json.load(f)
    except: return [] if filename in [HISTORY_FILE, SIGNALS_FILE] else {}

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

def get_ist_time():
    return datetime.now(IST)

# --- NEW FUNCTION: LOG SIGNALS ---
def log_signal_to_file(message):
    try:
        signals = load_json(SIGNALS_FILE)
        if not isinstance(signals, list): signals = []
        
        # Add new message with timestamp
        entry = {
            "timestamp": get_ist_time().strftime('%Y-%m-%d %H:%M'),
            "message": message
        }
        signals.append(entry)
        
        # Keep only the last 50 messages (to keep file small)
        save_json(SIGNALS_FILE, signals[-50:])
    except Exception as e:
        print(f"❌ Error logging signal: {e}")

def send_telegram(message):
    """Sends to Telegram AND saves to Signal Log"""
    # 1. Log to File for Dashboard
    log_signal_to_file(message)

    # 2. Send to Telegram
    if not CONFIG.get('telegram', {}).get('enabled', False): return
    for user in CONFIG['telegram'].get('recipients', []):
        try:
            url = f"https://api.telegram.org/bot{user['bot_token']}/sendMessage"
            requests.post(url, data={"chat_id": user['chat_id'], "text": message})
        except: pass

# --- TRADING LOGIC ---
def calculate_quantity(entry_price, sl_price):
    capital = CONFIG['strategy_settings']['capital']
    risk_pct = CONFIG['strategy_settings']['risk_per_trade_percent']
    return int((capital * (risk_pct / 100)) / (entry_price - sl_price))

def check_exit_conditions(ticker, trade_data, current_price, ema_fast, ema_slow):
    if ema_fast < ema_slow: return "SELL_ALL", "EMA Death Cross"
    if current_price <= trade_data['sl_price']: return "SELL_ALL", "Stop Loss Hit"
    return None, None

def analyze_market():
    load_config()
    portfolio = load_json(TRADES_FILE)
    
    # Time Check: strictly 3:15 PM to 3:30 PM, Monday through Friday
    now = get_ist_time()
    is_weekday = (now.weekday() < 5) # 0 = Monday, 4 = Friday
    
    start_time = datetime.strptime("15:15", "%H:%M").time()
    end_time = datetime.strptime("15:30", "%H:%M").time()
    
    checking_entries = is_weekday and (start_time <= now.time() <= end_time)

    print(f"[{now.strftime('%H:%M')}] Scanning... Entry Window: {checking_entries}")

    for ticker in CONFIG['watchlist']:
        try:
            # yfinance only allows max 730 days for 1-hour intervals
            df = yf.download(ticker, period="730d", interval="1h", progress=False)
            if len(df) < 55: continue
            
            # Indicators
            df['EMA_F'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_fast'])
            df['EMA_S'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_slow'])
            df['EMA_T'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_trend'])
            df['EMA_L'] = ta.ema(df['Close'], length=CONFIG['indicators']['ema_long'])
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            c_price = float(curr['Close'])
            
            # EXIT CHECK
            if ticker in portfolio:
                action, reason = check_exit_conditions(ticker, portfolio[ticker], c_price, curr['EMA_F'], curr['EMA_S'])
                if action == "SELL_ALL":
                    qty = portfolio[ticker]['quantity']
                    pnl = (c_price - portfolio[ticker]['entry_price']) * qty
                    msg = f"🔴 EXIT: {ticker}\nPrice: {c_price:.2f}\nPnL: ₹{pnl:.2f}\nReason: {reason}"
                    send_telegram(msg)
                    
                    # Save History
                    history = load_json(HISTORY_FILE)
                    history.append({
                        "timestamp": now.strftime('%Y-%m-%d %H:%M:%S'),
                        "ticker": ticker, "action": "SELL", "quantity": qty,
                        "price": c_price, "pnl": pnl, "reason": reason
                    })
                    save_json(HISTORY_FILE, history)
                    
                    del portfolio[ticker]
                    save_json(TRADES_FILE, portfolio)

            # ENTRY CHECK
            if checking_entries and ticker not in portfolio:
                if (curr['EMA_S'] > curr['EMA_T'] > curr['EMA_L']) and \
                   (curr['EMA_F'] > curr['EMA_S']) and (prev['EMA_F'] <= prev['EMA_S']):
                    
                    sl_price = curr['EMA_T'] * 0.999
                    qty = calculate_quantity(c_price, sl_price)
                    
                    if qty > 0:
                        msg = f"🚀 BUY SIGNAL: {ticker}\nEntry: {c_price:.2f}\nSL: {sl_price:.2f}"
                        send_telegram(msg)
                        
                        portfolio[ticker] = {
                            "entry_date": now.strftime('%Y-%m-%d'),
                            "entry_time": now.strftime('%H:%M:%S'),
                            "entry_price": c_price, "quantity": qty,
                            "sl_price": sl_price, "status": "OPEN"
                        }
                        save_json(TRADES_FILE, portfolio)
        except: continue

def scheduled_job():
    analyze_market()

def morning_wake_up():
    # Only send the message Monday through Friday
    if get_ist_time().weekday() < 5: 
        send_telegram("🔔 Market Open! Bot is awake and will look for trades at 3:15 PM.")

if __name__ == "__main__":
    load_config()
    send_telegram(f"🤖 Bot Started.\nTime: {get_ist_time().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. Market Scan (Every 5 mins)
    schedule.every(5).minutes.do(scheduled_job)
    
    # 2. Daily Wake Up Alert (At 9:15 AM)
    schedule.every().day.at("09:15").do(morning_wake_up)
    
    print("Scheduler active...")
    
    while True:
        schedule.run_pending()
        time.sleep(1)