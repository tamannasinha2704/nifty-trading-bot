import pandas as pd
import numpy as np
import json
import os
import requests
import time  # <--- Add this here
from datetime import datetime, timedelta, timezone
# ... (rest of imports)
from SmartApi import SmartConnect
import pyotp
import warnings

# Suppress pandas warnings for cleaner terminal output
warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
PORTFOLIO_FILE = "dmi_portfolio.json"  # Brand new ledger so it doesn't mix with your old bot!
CONFIG_FILE = "config.json"

# --- STRATEGY SETTINGS ---
TOTAL_CAPITAL = 1000000.0        # ₹10 Lakhs Total Capital
TRADE_CAPITAL = 200000.0         # ₹2 Lakhs Deployed Per Trade
BROKERAGE_RATE = 0.0015          # 0.15% of deployed capital
WATCHLIST = ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "BAJAJFINSV", "NATGASMINI"]

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Error: {CONFIG_FILE} not found!")
        exit()
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

config = load_config()
TELEGRAM_ENABLED = config['telegram']['enabled']
TELEGRAM_RECIPIENTS = config['telegram']['recipients']

# --- ANGEL ONE API SETUP ---
def get_angel_session():
    print("🔐 Authenticating with Angel One SmartAPI...")
    try:
        api_key = config['angel_one']['api_key']
        client_id = config['angel_one']['client_id']
        pin = config['angel_one']['pin']
        totp_secret = config['angel_one']['totp_secret']
        
        smartApi = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        session = smartApi.generateSession(client_id, pin, totp)
        
        if session.get('status'):
            print("✅ SmartAPI Login Successful!")
            return smartApi
        else:
            print("❌ Angel One Login Failed:", session)
            exit()
    except Exception as e:
        print("❌ Angel One Connection Error:", e)
        exit()

# --- DYNAMIC FUTURES TOKEN FETCHER ---
def get_futures_tokens(watchlist):
    """Finds the closest expiring Futures contract for the watchlist."""
    print("🔄 Scanning for Near-Month Future Contracts...")
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        response = requests.get(url, timeout=10)
        instrument_list = response.json()
        
        df = pd.DataFrame(instrument_list)
        
        # Filter for NFO (Futures & Options) and specifically Futures (FUTIDX and FUTSTK)
        # Filter for NFO & MCX Futures
        df_nfo = df[(df['exch_seg'].isin(['NFO', 'MCX'])) & (df['instrumenttype'].isin(['FUTIDX', 'FUTSTK', 'FUTCOM', 'FUTENG']))]

        # Convert the string 'expiry' to actual dates so we can sort them mathematically
        df_nfo['expiry_date'] = pd.to_datetime(df_nfo['expiry'], format='%d%b%Y')
        
        # Filter out contracts that have already expired
        today = pd.to_datetime('today').normalize()
        df_nfo = df_nfo[df_nfo['expiry_date'] >= today]
        
        token_map = {}
        for script in watchlist:
            # Find all available futures for the specific script
            script_df = df_nfo[df_nfo['name'] == script]
            
            if not script_df.empty:
                # Sort by expiry date (closest date first)
                script_df = script_df.sort_values(by='expiry_date')
                near_month = script_df.iloc[0]
                
                token_map[script] = {
                    "token": near_month['token'],
                    "trading_symbol": near_month['symbol'],
                    "expiry": near_month['expiry']
                }
                print(f"🎯 Locked onto {script} -> {near_month['symbol']} (Expires: {near_month['expiry']})")
            else:
                print(f"⚠️ Could not find future contracts for {script}")
                
        return token_map
    except Exception as e:
        print(f"❌ Failed to fetch tokens: {e}")
        return {}

# Initialize the connection and lock onto the tokens
smartApi = get_angel_session()
TOKEN_MAP = get_futures_tokens(WATCHLIST)
# --- DATA FETCHING & MATH ENGINE ---
def fetch_hourly_data(script_name):
    """Fetches 1-Hour data for the active future and calculates RSI-DMI."""
    if smartApi is None or script_name not in TOKEN_MAP: 
        return None, None
    
    token_info = TOKEN_MAP[script_name]
    token = token_info['token']
    exchange = "MCX" if script_name == "NATGASMINI" else "NFO"
        
    to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    from_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M")
    
    try:
        historicParam = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": "ONE_HOUR",
            "fromdate": from_date,
            "todate": to_date
        }
        res = smartApi.getCandleData(historicParam)
        
        if res.get('status') and res.get('data'):
            columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
            df = pd.DataFrame(res['data'], columns=columns)
            
            # 1. CALCULATE RSI (14) using PineScript's RMA method
            delta = df['Close'].diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            
            # Pandas ewm(alpha=1/length) perfectly matches TradingView's ta.rma()
            ema_up = up.ewm(alpha=1/14, adjust=False).mean()
            ema_down = down.ewm(alpha=1/14, adjust=False).mean()
            rs = ema_up / ema_down
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # 2. CALCULATE DMI ON RSI
            rsi_diff = df['RSI'].diff()
            
            # UpMove and DownMove (Since High/Low/Close are all just the RSI value)
            upMove = rsi_diff
            downMove = -rsi_diff
            
            # +DM and -DM
            df['plusDM'] = np.where((upMove > downMove) & (upMove > 0), upMove, 0)
            df['minusDM'] = np.where((downMove > upMove) & (downMove > 0), downMove, 0)
            
            # True Range of RSI
            df['TR'] = abs(rsi_diff)
            
            # Smooth the TR, +DM, and -DM using RMA(14)
            smoothedTR = df['TR'].ewm(alpha=1/14, adjust=False).mean()
            smoothedPlusDM = df['plusDM'].ewm(alpha=1/14, adjust=False).mean()
            smoothedMinusDM = df['minusDM'].ewm(alpha=1/14, adjust=False).mean()
            
            # Calculate Base +DI and -DI
            df['plusDI'] = 100 * smoothedPlusDM / smoothedTR
            df['minusDI'] = 100 * smoothedMinusDM / smoothedTR
            
            # 3. APPLY 5 EMA SMOOTHING (As requested for the signals)
            df['plusDI_EMA5'] = df['plusDI'].ewm(span=5, adjust=False).mean()
            df['minusDI_EMA5'] = df['minusDI'].ewm(span=5, adjust=False).mean()
            
            # Return the last fully closed candle (-2) and the one before it (-3)
            return df.iloc[-2], df.iloc[-3]
        else:
            return None, None
    except Exception as e:
        print(f"Error fetching data for {script_name}: {e}")
        return None, None
    # --- HELPER FUNCTIONS ---
def send_telegram(message):
    if not TELEGRAM_ENABLED: return
    for user in TELEGRAM_RECIPIENTS:
        url = f"https://api.telegram.org/bot{user['bot_token']}/sendMessage"
        payload = {"chat_id": user['chat_id'], "text": f"📊 DMI ALGO\n{message}"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f: return json.load(f)
        except: pass
    return {
        "capital": TOTAL_CAPITAL, "open_longs": {}, "open_shorts": {}, 
        "closed_longs": [], "closed_shorts": [], "signals": []
    }

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=4)

def log_event(data, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    if "signals" not in data: data["signals"] = []
    data["signals"].insert(0, log_msg)
    data["signals"] = data["signals"][:100]
    send_telegram(message)

def is_market_open(script_name):
    """Checks IST market hours. NFO closes at 15:30, MCX at 23:30."""
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    
    if now_ist.weekday() >= 5: return False
    if now_ist.strftime('%Y-%m-%d') in config.get('holidays', []): return False
        
    market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    
    if script_name == "NATGASMINI":
        market_end = now_ist.replace(hour=23, minute=30, second=0, microsecond=0)
    else:
        market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= now_ist <= market_end

# --- MAIN BOT LOOP ---
def run_bot():
    print(f"\n🚀 Running DMI-RSI Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    data = load_portfolio()
    
    open_longs = data["open_longs"]
    open_shorts = data["open_shorts"]
    current_capital = data["capital"]

    # 1. MANAGE EXITS
    for script in list(open_longs.keys()):
        if not is_market_open(script): continue
        curr, prev = fetch_hourly_data(script)
        if curr is None: continue
        open_longs[script]['current_price'] = round(curr['Close'], 2)
        # Buy Exit Condition: current +DI < previous +DI
        if curr['plusDI_EMA5'] < prev['plusDI_EMA5']:
            pos = open_longs[script]
            entry_price = pos['entry_price']
            exit_price = curr['Close']
            qty = pos['qty']
            
            gross_pnl = (exit_price - entry_price) * qty
            # 0.15% Brokerage on deployed capital (Entry + Exit values)
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE_RATE
            net_pnl = gross_pnl - brokerage
            
            data['closed_longs'].append({
                "Ticker": script, "Trading Symbol": pos['trading_symbol'],
                "Entry Date": pos['entry_date'], "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 2), "Qty": qty, 
                "PnL": round(net_pnl, 2), "Status": "CLOSED", "Reason": "+DI Decreased"
            })
            current_capital += (exit_price * qty) - brokerage
            del open_longs[script]
            log_event(data, f"❌ CLOSED LONG: {script}\nExit: ₹{exit_price:.2f} | PnL: ₹{net_pnl:.2f}")

    for script in list(open_shorts.keys()):
        if not is_market_open(script): continue
        curr, prev = fetch_hourly_data(script)
        if curr is None: continue
        open_shorts[script]['current_price'] = round(curr['Close'], 2)

        # Sell Exit Condition: current -DI < previous -DI
        if curr['minusDI_EMA5'] < prev['minusDI_EMA5']:
            pos = open_shorts[script]
            entry_price = pos['entry_price']
            exit_price = curr['Close']
            qty = pos['qty']
            
            gross_pnl = (entry_price - exit_price) * qty
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE_RATE
            net_pnl = gross_pnl - brokerage
            
            data['closed_shorts'].append({
                "Ticker": script, "Trading Symbol": pos['trading_symbol'],
                "Entry Date": pos['entry_date'], "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 2), "Qty": qty, 
                "PnL": round(net_pnl, 2), "Status": "CLOSED", "Reason": "-DI Decreased"
            })
            current_capital += (entry_price * qty) + net_pnl
            del open_shorts[script]
            log_event(data, f"❌ CLOSED SHORT: {script}\nExit: ₹{exit_price:.2f} | PnL: ₹{net_pnl:.2f}")

    # 2. CHECK ENTRIES
    print("\n🔎 Scanning for New Signals...")
    for script in WATCHLIST:
        if script in open_longs or script in open_shorts: continue
        if not is_market_open(script): continue
            
        curr, prev = fetch_hourly_data(script)
        if curr is None: continue
        
        # --- ENTRY LOGIC ---
        buy_cond = (curr['plusDI_EMA5'] > prev['plusDI_EMA5']) and (curr['minusDI_EMA5'] < prev['minusDI_EMA5'])
        sell_cond = (curr['minusDI_EMA5'] > prev['minusDI_EMA5']) and (curr['plusDI_EMA5'] < prev['plusDI_EMA5'])
        
        if buy_cond:
            entry_price = curr['Close']
            qty = int(TRADE_CAPITAL // entry_price) # Fixed ₹2 Lakhs per trade
            cost = qty * entry_price
            
            if qty > 0 and current_capital >= cost:
                current_capital -= (cost + (cost * BROKERAGE_RATE))
                open_longs[script] = {
                    "trading_symbol": TOKEN_MAP[script]['trading_symbol'],
                    "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                    "entry_price": round(entry_price, 2), "qty": qty
                }
                log_event(data, f"✅ OPEN LONG: {script} ({TOKEN_MAP[script]['trading_symbol']})\nEntry: ₹{entry_price:.2f} | Qty: {qty}")
                
        elif sell_cond:
            entry_price = curr['Close']
            qty = int(TRADE_CAPITAL // entry_price)
            margin_req = qty * entry_price
            
            if qty > 0 and current_capital >= margin_req:
                current_capital -= (margin_req * BROKERAGE_RATE)
                open_shorts[script] = {
                    "trading_symbol": TOKEN_MAP[script]['trading_symbol'],
                    "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                    "entry_price": round(entry_price, 2), "qty": qty
                }
                log_event(data, f"✅ OPEN SHORT: {script} ({TOKEN_MAP[script]['trading_symbol']})\nEntry: ₹{entry_price:.2f} | Qty: {qty}")

    data["open_longs"] = open_longs
    data["open_shorts"] = open_shorts
    data["capital"] = current_capital
    save_portfolio(data)
    print("💾 DMI Portfolio Updated.")

if __name__ == "__main__":
    while True:
        run_bot()
        
        # --- INSTITUTIONAL TIMING SYNC ---
        now = datetime.now()
        
        # Find the next 15-minute interval (0, 15, 30, or 45)
        next_minute = ((now.minute // 15) + 1) * 15
        
        # Calculate exact next timestamp, adding a 5-second buffer for the API to finalize data
        next_time = now.replace(minute=0, second=5, microsecond=0) + timedelta(minutes=next_minute)
        sleep_seconds = (next_time - now).total_seconds()
        
        print(f"\n⏳ Syncing to exchange clock... Sleeping for {int(sleep_seconds)} seconds until {next_time.strftime('%H:%M:%S')}")
        time.sleep(sleep_seconds)
