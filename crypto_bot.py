import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime

# --- CRYPTO CONFIGURATION ---
PORTFOLIO_FILE = "crypto_portfolio.json"
CONFIG_FILE = "config.json" # Reusing this just for your Telegram keys

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Error: {CONFIG_FILE} not found!")
        exit()
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

config = load_config()

# Crypto Specific Overrides
CAPITAL = 10000.0  # $10,000 USD Paper Trading Capital
RISK_PER_TRADE = 0.005 # 0.5% Risk ($50 per trade)
BROKERAGE = 0.001  # 0.1% Crypto Exchange average fee
TELEGRAM_ENABLED = config['telegram']['enabled']
TELEGRAM_RECIPIENTS = config['telegram']['recipients']

WATCHLIST = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD', 
    'ADA-USD', 'DOGE-USD', 'AVAX-USD', 'LINK-USD', 'DOT-USD'
]

# --- HELPER FUNCTIONS ---
def send_telegram(message):
    if not TELEGRAM_ENABLED: return
    for user in TELEGRAM_RECIPIENTS:
        url = f"https://api.telegram.org/bot{user['bot_token']}/sendMessage"
        payload = {"chat_id": user['chat_id'], "text": f"🪙 CRYPTO ALGO\n{message}"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f: return json.load(f)
        except: pass
    return {
        "capital": CAPITAL, "open_longs": {}, "open_shorts": {}, 
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

def fetch_hourly_data(ticker):
    try:
        df = yf.download(ticker, period="60d", interval="1h", progress=False)
        if df.empty or len(df) < 205: return None, None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df['SMA_100'] = df['Close'].rolling(window=100).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA_10'] = df['Close'].ewm(span=10, adjust=False).mean()
        df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
        return df.iloc[-1], df.iloc[-2]
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None, None

# --- MAIN BOT LOOP ---
def run_bot():
    print(f"\n🪙 Running CRYPTO Bot | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    data = load_portfolio()
    
    open_longs, open_shorts, current_capital = data["open_longs"], data["open_shorts"], data["capital"]

    # 1. MANAGE EXITS
    for ticker in list(open_longs.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_longs[ticker]
        entry_price, initial_risk, current_sl = pos['entry_price'], pos['risk_points'], pos['stop_loss']
        
        r_multiple = (curr['High'] - entry_price) / initial_risk if initial_risk > 0 else 0
        new_sl = max(current_sl, entry_price + initial_risk) if r_multiple >= 2.0 else max(current_sl, entry_price) if r_multiple >= 1.0 else current_sl
            
        open_longs[ticker]['stop_loss'], open_longs[ticker]['current_price'] = round(new_sl, 4), round(curr['Close'], 4)
        
        sl_hit = curr['Low'] <= new_sl
        strategy_exit = (curr['EMA_5'] < curr['EMA_10']) and (prev['EMA_5'] >= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            net_pnl = ((exit_price - entry_price) * qty) - (((entry_price * qty) + (exit_price * qty)) * BROKERAGE)
            reason = "Stop Loss Hit" if sl_hit else "EMA 5 < 10"
            
            data['closed_longs'].append({
                "Ticker": ticker, "Entry Date": pos['entry_date'], "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 4), "Qty": qty, "Stop Loss": round(new_sl, 4), 
                "PnL": round(net_pnl, 2), "Status": "CLOSED", "Reason": reason
            })
            current_capital += (exit_price * qty) - (((entry_price * qty) + (exit_price * qty)) * BROKERAGE)
            del open_longs[ticker]
            log_event(data, f"❌ CLOSED LONG: {ticker} @ ${exit_price:.4f} | PnL: ${net_pnl:.2f}\nReason: {reason}")

    for ticker in list(open_shorts.keys()):
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        pos = open_shorts[ticker]
        entry_price, initial_risk, current_sl = pos['entry_price'], pos['risk_points'], pos['stop_loss']
        
        r_multiple = (entry_price - curr['Low']) / initial_risk if initial_risk > 0 else 0
        new_sl = min(current_sl, entry_price - initial_risk) if r_multiple >= 2.0 else min(current_sl, entry_price) if r_multiple >= 1.0 else current_sl
            
        open_shorts[ticker]['stop_loss'], open_shorts[ticker]['current_price'] = round(new_sl, 4), round(curr['Close'], 4)
        
        sl_hit = curr['High'] >= new_sl
        strategy_exit = (curr['EMA_5'] > curr['EMA_10']) and (prev['EMA_5'] <= prev['EMA_10'])
        
        if sl_hit or strategy_exit:
            exit_price = new_sl if sl_hit else curr['Close']
            qty = pos['qty']
            net_pnl = ((entry_price - exit_price) * qty) - (((entry_price * qty) + (exit_price * qty)) * BROKERAGE)
            reason = "Stop Loss Hit" if sl_hit else "EMA 5 > 10"
            
            data['closed_shorts'].append({
                "Ticker": ticker, "Entry Date": pos['entry_date'], "Exit Date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "Entry Price": entry_price, "Exit Price": round(exit_price, 4), "Qty": qty, "Stop Loss": round(new_sl, 4), 
                "PnL": round(net_pnl, 2), "Status": "CLOSED", "Reason": reason
            })
            current_capital += (entry_price * qty) + net_pnl
            del open_shorts[ticker]
            log_event(data, f"❌ CLOSED SHORT: {ticker} @ ${exit_price:.4f} | PnL: ${net_pnl:.2f}\nReason: {reason}")

    # 2. CHECK ENTRIES
    for ticker in WATCHLIST:
        if ticker in open_longs or ticker in open_shorts: continue
        curr, prev = fetch_hourly_data(ticker)
        if curr is None: continue
        
        if (curr['SMA_100'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_100']) and (curr['EMA_21'] > curr['EMA_50']) and (curr['EMA_10'] > curr['EMA_21']) and (prev['EMA_10'] <= prev['EMA_21']):
            entry_price, sl_price = curr['Close'], curr['EMA_21'] * 0.999
            risk_points = entry_price - sl_price
            if risk_points > 0:
                qty = (CAPITAL * RISK_PER_TRADE) / risk_points # Crypto can have fractional quantities!
                cost = qty * entry_price
                if qty > 0 and current_capital >= cost:
                    current_capital -= (cost + (cost * BROKERAGE))
                    open_longs[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'), "entry_price": round(entry_price, 4), 
                        "qty": round(qty, 4), "risk_points": round(risk_points, 4), "stop_loss": round(sl_price, 4), "current_price": round(entry_price, 4)
                    }
                    log_event(data, f"✅ OPEN LONG: {ticker}\nEntry: ${entry_price:.4f} | Qty: {qty:.4f}\nSL: ${sl_price:.4f}")
        
        if (curr['SMA_100'] < curr['SMA_200']) and (curr['EMA_50'] < curr['SMA_100']) and (curr['EMA_21'] < curr['EMA_50']) and (curr['EMA_10'] < curr['EMA_21']) and (prev['EMA_10'] >= prev['EMA_21']):
            entry_price, sl_price = curr['Close'], curr['EMA_21'] * 1.001
            risk_points = sl_price - entry_price
            if risk_points > 0:
                qty = (CAPITAL * RISK_PER_TRADE) / risk_points
                margin_req = qty * entry_price
                if qty > 0 and current_capital >= margin_req:
                    current_capital -= (margin_req * BROKERAGE)
                    open_shorts[ticker] = {
                        "entry_date": datetime.now().strftime('%Y-%m-%d %H:%M'), "entry_price": round(entry_price, 4), 
                        "qty": round(qty, 4), "risk_points": round(risk_points, 4), "stop_loss": round(sl_price, 4), "current_price": round(entry_price, 4)
                    }
                    log_event(data, f"✅ OPEN SHORT: {ticker}\nEntry: ${entry_price:.4f} | Qty: {qty:.4f}\nSL: ${sl_price:.4f}")

    data["open_longs"], data["open_shorts"], data["capital"] = open_longs, open_shorts, current_capital
    save_portfolio(data)
    print("💾 Crypto Portfolio Updated.")

if __name__ == "__main__":
    run_bot()