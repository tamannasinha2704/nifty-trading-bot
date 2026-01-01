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
IST = pytz.timezone('Asia/Kolkata')
CONFIG = {}

def load_config():
    global CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            CONFIG = json.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")

def load_portfolio():
    if not os.path.exists(TRADES_FILE):
        return {}
    try:
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_portfolio(portfolio):
    with open(TRADES_FILE, 'w') as f:
        json.dump(portfolio, f, indent=4)

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
            print(f"   >>> ❌ Telegram Failed for {user.get('note', 'User')}: {e}")

# --- NEW FUNCTION: Send Documents (Excel) ---
def send_telegram_file(file_path, caption=""):
    """Sends a file to ALL recipients"""
    if not CONFIG.get('telegram', {}).get('enabled', False): return
    
    recipients = CONFIG['telegram'].get('recipients', [])
    
    for user in recipients:
        try:
            token = user['bot_token']
            chat_id = user['chat_id']
            url = f"https://api.telegram.org/bot{token}/sendDocument"
            
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': chat_id, 'caption': caption}
                requests.post(url, data=data, files=files)
                print(f"   >>> 📤 Report sent to {user.get('note', 'User')}")
        except Exception as e:
            print(f"   >>> ❌ Telegram File Error for {user.get('note', 'User')}: {e}")

# --- NEW FUNCTION: Generate & Send Excel Report ---
def generate_and_send_report():
    print("\n📊 Generating Daily Excel Report...")
    portfolio = load_portfolio()
    
    if not portfolio:
        print("   >>> Portfolio is empty. No report generated.")
        return

    try:
        # 1. Convert Portfolio JSON to DataFrame
        data = []
        for ticker, info in portfolio.items():
            row = info.copy()
            row['Ticker'] = ticker  # Add Ticker as a column
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # 2. Reorder columns for better readability (Optional)
        preferred_order = ['Ticker', 'status', 'entry_date', 'entry_price', 'quantity', 'sl_price', 'initial_sl']
        # Filter existing columns only
        cols = [c for c in preferred_order if c in df.columns] + [c for c in df.columns if c not in preferred_order]
        df = df[cols]

        # 3. Save to Excel
        timestamp = get_ist_time().strftime('%Y%m%d_%H%M')
        filename = f"Portfolio_Report_{timestamp}.xlsx"
        df.to_excel(filename, index=False)
        
        # 4. Send to Telegram
        caption = f"📊 Daily Portfolio Report - {get_ist_time().strftime('%d-%m-%Y')}"
        send_telegram_file(filename, caption)
        
        print(f"   >>> ✅ Report generated and sent: {filename}")
        
    except Exception as e:
        print(f"   >>> ❌ Error generating report: {e}")

def get_ist_time():
    return datetime.now(IST)

# --- 1. SCHEDULING LOGIC ---
def is_entry_window():
    if CONFIG['strategy_settings']['test_mode']: return True
    
    now = get_ist_time()
    today_str = now.strftime('%Y-%m-%d')
    weekday = now.weekday()
    current_time = now.time()
    
    start_time = datetime.strptime("15:15", "%H:%M").time()
    end_time = datetime.strptime("15:30", "%H:%M").time()
    
    if not (start_time <= current_time <= end_time):
        return False

    if weekday == 4: # Friday
        if today_str not in CONFIG['holidays']: return True
            
    if weekday == 3: # Thursday
        tomorrow = now + timedelta(days=1)
        if tomorrow.strftime('%Y-%m-%d') in CONFIG['holidays']: return True
            
    return False

def calculate_quantity(entry_price, sl_price):
    capital = CONFIG['strategy_settings']['capital']
    risk_pct = CONFIG['strategy_settings']['risk_per_trade_percent']
    risk_amount = capital * (risk_pct / 100)
    risk_per_share = entry_price - sl_price
    if risk_per_share <= 0: return 0
    return int(risk_amount / risk_per_share)

def check_exit_conditions(ticker, trade_data, current_price, ema_fast, ema_slow):
    entry_price = trade_data['entry_price']
    sl_price = trade_data['sl_price']
    status = trade_data['status']
    
    if ema_fast < ema_slow: return "SELL_ALL", "EMA Death Cross (5 < 9)"
    if current_price <= sl_price: return "SELL_ALL", f"Stop Loss Hit ({sl_price})"
    
    risk = entry_price - trade_data['initial_sl']
    target_1 = entry_price + risk
    target_2 = entry_price + (2 * risk)
    
    if status == 'OPEN' and current_price >= target_1:
        return "SELL_PARTIAL", f"Target 1 Hit ({target_1:.2f})"
        
    if status == 'PARTIAL' and current_price >= target_2 and sl_price < target_1:
        return "UPDATE_SL", f"Target 2 Hit ({target_2:.2f})"
        
    return None, None

def analyze_market():
    load_config()
    portfolio = load_portfolio()
    checking_entries = is_entry_window()
    now_str = get_ist_time().strftime('%H:%M')
    
    print(f"\n[{now_str}] Market Scan. Entry Window: {checking_entries}")
    
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
            
            c_price, c_fast, c_slow = float(curr['Close']), float(curr['EMA_F']), float(curr['EMA_S'])
            c_trend, c_long = float(curr['EMA_T']), float(curr['EMA_L'])
            p_fast, p_slow = float(prev['EMA_F']), float(prev['EMA_S'])
            p_trend, p_long = float(prev['EMA_T']), float(prev['EMA_L'])
            
            # EXIT CHECKS
            if ticker in portfolio:
                action, reason = check_exit_conditions(ticker, portfolio[ticker], c_price, c_fast, c_slow)
                if action == "SELL_ALL":
                    msg = f"🔴 EXIT: {ticker}\nPrice: {c_price:.2f}\nReason: {reason}"
                    print(msg); send_telegram(msg)
                    del portfolio[ticker]; save_portfolio(portfolio)
                elif action == "SELL_PARTIAL":
                    qty = portfolio[ticker]['quantity']
                    sell_qty = int(round(qty * 0.5))
                    portfolio[ticker]['quantity'] -= sell_qty
                    portfolio[ticker]['status'] = 'PARTIAL'
                    portfolio[ticker]['sl_price'] = portfolio[ticker]['entry_price']
                    msg = f"💰 T1 HIT: {ticker}\nSold {sell_qty} (50%)\nSL moved to Entry"
                    print(msg); send_telegram(msg); save_portfolio(portfolio)
                elif action == "UPDATE_SL":
                    risk = portfolio[ticker]['entry_price'] - portfolio[ticker]['initial_sl']
                    new_sl = portfolio[ticker]['entry_price'] + risk
                    portfolio[ticker]['sl_price'] = new_sl
                    msg = f"📈 T2 HIT: {ticker}\nTrailing SL moved to {new_sl:.2f}"
                    print(msg); send_telegram(msg); save_portfolio(portfolio)

            # ENTRY CHECKS
            if checking_entries and ticker not in portfolio:
                cond_align = (c_slow > c_trend) and (c_trend > c_long)
                cond_cross = (c_fast > c_slow) and (p_fast <= p_slow)
                cond_rising = (c_fast > p_fast) and (c_slow > p_slow) and (c_trend > p_trend) and (c_long > p_long)
                
                if cond_align and cond_cross and cond_rising:
                    sl_price = c_trend * 0.999
                    qty = calculate_quantity(c_price, sl_price)
                    if qty > 0:
                        msg = f"🚀 BUY: {ticker}\nEntry: {c_price:.2f}\nSL: {sl_price:.2f}\nQty: {qty}"
                        print(msg); send_telegram(msg)
                        portfolio[ticker] = {
                            "entry_date": datetime.now().strftime('%Y-%m-%d'),
                            "entry_price": c_price, "quantity": qty,
                            "initial_sl": sl_price, "sl_price": sl_price, "status": "OPEN"
                        }
                        save_portfolio(portfolio)
        except: continue

if __name__ == "__main__":
    load_config()
    send_telegram(f"🤖 Bot Active (Nifty 50)\nMonitoring {len(CONFIG['watchlist'])} stocks")
    
    # 1. Run Market Analysis immediately
    analyze_market()
    
    # 2. Schedule Market Analysis (Every 5 mins)
    schedule.every(CONFIG['strategy_settings']['scan_interval_minutes']).minutes.do(analyze_market)
    
    # 3. Schedule Daily Excel Report (Every day at 15:45 IST)
    # This ensures you get the file after the market closes.
    schedule.every().day.at("15:45").do(generate_and_send_report)
    
    print("Scheduler active (Scan: 5min, Report: 15:45)...")
    
    while True: 
        schedule.run_pending()
        time.sleep(1)