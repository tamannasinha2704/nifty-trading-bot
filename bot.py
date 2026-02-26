import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
import pyotp

# --- CONFIGURATION FILES ---
PORTFOLIO_FILE = "portfolio.json"
CONFIG_FILE = "config.json"

# --- LOAD CONFIG ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Error: {CONFIG_FILE} not found!")
        exit()
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

config = load_config()
CAPITAL = config['strategy_settings']['capital']
RISK_PER_TRADE = config['strategy_settings']['risk_per_trade_percent'] / 100.0
BROKERAGE = config['strategy_settings']['brokerage_percent'] / 100.0
WATCHLIST = config['watchlist']
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

def get_token_map():
    print("🔄 Fetching NSE Token Master List...")
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        response = requests.get(url, timeout=10)
        instrument_list = response.json()
        token_map = {}
        for instrument in instrument_list:
            if instrument["exch_seg"] == "NSE" and instrument["symbol"].endswith("-EQ"):
                base_symbol = instrument["symbol"].replace("-EQ", "")
                token_map[base_symbol] = instrument["token"]
        return token_map
    except Exception as e:
        print(f"❌ Failed to fetch tokens: {e}")
        return {}

# Initialize Angel One connection and fetch tokens
smartApi = get_angel_session()
TOKEN_MAP = get_token_map()

# --- HELPER FUNCTIONS ---
def send_telegram(message):
    """Sends message to all recipients in config.json"""
    if not TELEGRAM_ENABLED: return
    
    for user in TELEGRAM_RECIPIENTS:
        url = f"https://api.telegram.org/bot{user['bot_token']}/sendMessage"
        payload = {"chat_id": user['chat_id'], "text": message}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"⚠️ Telegram alert failed for {user['note']}: {e}")

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {
        "capital": CAPITAL, 
        "open_longs": {}, 
        "open_shorts": {}, 
        "closed_longs": [], 
        "closed_shorts": [],
        "signals": []
    }

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def log_event(data, message):
    """Logs signal to console, JSON, and Telegram."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    
    if "signals" not in data: data["signals"] = []
    data["signals"].insert(0, log_msg)
    data["signals"] = data["signals"][:100]
    
    send_telegram(f"🤖 Algo Alert\n{message}")

# --- UPDATED DATA FETCHING ---
def fetch_hourly_data(ticker):
    """Fetches 1-Hour data from Angel One SmartAPI and calculates MAs."""
    if smartApi is None: return None, None
    
    # Convert "RELIANCE.NS" to "RELIANCE" to find the token
    base_symbol = ticker.replace(".NS", "")
    token = TOKEN_MAP.get(base_symbol)
    
    if not token:
        print(f"⚠️ Token not found for {ticker}")
        return None, None
        
    to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    from_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M")
    
    try:
        historicParam = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_HOUR",
            "fromdate": from_date,
            "todate": to_date
        }
        res = smartApi.getCandleData(historicParam)
        
        if res.get('status') and res.get('data'):
            # Convert Angel One data format to matching Pandas DataFrame
            columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
            df = pd.DataFrame(res['data'], columns=columns)
            
            df['SMA_100'] = df['Close'].rolling(window=100).mean()
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
            df['EMA_10'] = df['Close'].ewm(span=10, adjust=False).mean()
            df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
            
            return df.iloc[-1], df.iloc[-2]
        else:
            return None, None
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None, None

# --- MAIN BOT LOOP ---
def run_bot():
    print(f"\n🚀 Running HOURLY Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    data = load_portfolio()
    
    open_longs = data["open_longs"]
    open_shorts = data["open_shorts"]
    current_capital = data["capital"]

    # 1. MANAGE EXITS & TRAILING STOPS
    for ticker in list(open_longs.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_longs[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['risk_points']
        current_sl = pos['stop_loss']
        
        r_multiple = (curr['High'] - entry_price) / initial_risk if initial_risk > 0 else 0
        new_sl = current_sl
        
        if r_multiple >= 2.0:
            new_sl = max(current_sl, entry_price + initial_risk)
        elif r_multiple >= 1.0:
            new_sl = max(current_sl, entry_price)
            
        open_longs[ticker]['stop_loss'] = round(new_sl, 2)
        open_longs[ticker]['current_price'] = round(curr['Close'], 2)
        
        sl_hit = curr['Low'] <= new_sl
        strategy_exit = (curr['EMA_5'] < curr['EMA_10']) and (prev['EMA_5'] >= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            
            gross_pnl = (exit_price - entry_price) * qty
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE
            net_pnl = gross_pnl - brokerage
            reason = "Stop Loss Hit" if sl_hit else "EMA 5 < 10"
            
            data['closed_longs'].append({
                "Ticker": ticker, "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 2),
                "Qty": qty, "Stop Loss": round(new_sl, 2), "PnL": round(net_pnl, 2),
                "Status": "CLOSED", "Reason": reason
            })
            current_capital += (exit_price * qty) - brokerage
            del open_longs[ticker]
            log_event(data, f"❌ CLOSED LONG: {ticker} @ ₹{exit_price:.2f} | PnL: ₹{net_pnl:.2f}\nReason: {reason}")

    for ticker in list(open_shorts.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_shorts[ticker]
        entry_price = pos['entry_price']
        initial_risk = pos['risk_points']
        current_sl = pos['stop_loss']
        
        r_multiple = (entry_price - curr['Low']) / initial_risk if initial_risk > 0 else 0
        new_sl = current_sl
        
        if r_multiple >= 2.0:
            new_sl = min(current_sl, entry_price - initial_risk)
        elif r_multiple >= 1.0:
            new_sl = min(current_sl, entry_price)
            
        open_shorts[ticker]['stop_loss'] = round(new_sl, 2)
        open_shorts[ticker]['current_price'] = round(curr['Close'], 2)
        
        sl_hit = curr['High'] >= new_sl
        strategy_exit = (curr['EMA_5'] > curr['EMA_10']) and (prev['EMA_5'] <= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            
            gross_pnl = (entry_price - exit_price) * qty
            brokerage = ((entry_price * qty) + (exit_price * qty)) * BROKERAGE
            net_pnl = gross_pnl - brokerage
            reason = "Stop Loss Hit" if sl_hit else "EMA 5 > 10"
            
            data['closed_shorts'].append({
                "Ticker": ticker, "Entry Date": pos['entry_date'],
                "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 2),
                "Qty": qty, "Stop Loss": round(new_sl, 2), "PnL": round(net_pnl, 2),
                "Status": "CLOSED", "Reason": reason
            })
            current_capital += (entry_price * qty) + net_pnl
            del open_shorts[ticker]
            log_event(data, f"❌ CLOSED SHORT: {ticker} @ ₹{exit_price:.2f} | PnL: ₹{net_pnl:.2f}\nReason: {reason}")

    # 2. CHECK NEW ENTRIES
    print("\n🔎 Scanning for New Hourly Signals...")
    for ticker in WATCHLIST:
        if ticker in open_longs or ticker in open_shorts: continue
            
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        long_trend = (curr['SMA_100'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_100']) and (curr['EMA_21'] > curr['EMA_50'])
        long_trigger = (curr['EMA_10'] > curr['EMA_21']) and (prev['EMA_10'] <= prev['EMA_21'])
        
        if long_trend and long_trigger:
            entry_price = curr['Close']
            sl_price = curr['EMA_21'] * 0.999
            risk_points = entry_price - sl_price
            
            if risk_points > 0:
                qty = int((CAPITAL * RISK_PER_TRADE) // risk_points)
                cost = qty * entry_price
                if qty > 0 and current_capital >= cost:
                    current_capital -= (cost + (cost * BROKERAGE))
                    open_longs[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2), "qty": qty,
                        "risk_points": round(risk_points, 2), "stop_loss": round(sl_price, 2),
                        "current_price": round(entry_price, 2)
                    }
                    log_event(data, f"✅ OPEN LONG: {ticker}\nEntry: ₹{entry_price:.2f} | Qty: {qty}\nSL: ₹{sl_price:.2f}")
        
        short_trend = (curr['SMA_100'] < curr['SMA_200']) and (curr['EMA_50'] < curr['SMA_100']) and (curr['EMA_21'] < curr['EMA_50'])
        short_trigger = (curr['EMA_10'] < curr['EMA_21']) and (prev['EMA_10'] >= prev['EMA_21'])
        
        if short_trend and short_trigger:
            entry_price = curr['Close']
            sl_price = curr['EMA_21'] * 1.001
            risk_points = sl_price - entry_price
            
            if risk_points > 0:
                qty = int((CAPITAL * RISK_PER_TRADE) // risk_points)
                margin_req = qty * entry_price
                if qty > 0 and current_capital >= margin_req:
                    current_capital -= (margin_req * BROKERAGE)
                    open_shorts[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                        "entry_price": round(entry_price, 2), "qty": qty,
                        "risk_points": round(risk_points, 2), "stop_loss": round(sl_price, 2),
                        "current_price": round(entry_price, 2)
                    }
                    log_event(data, f"✅ OPEN SHORT: {ticker}\nEntry: ₹{entry_price:.2f} | Qty: {qty}\nSL: ₹{sl_price:.2f}")

    data["open_longs"] = open_longs
    data["open_shorts"] = open_shorts
    data["capital"] = current_capital
    save_portfolio(data)
    print("💾 Portfolio Updated Successfully.")

if __name__ == "__main__":
    run_bot()