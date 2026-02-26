# Dual-Engine Algorithmic Trading System 📈

An automated, cloud-hosted paper trading system designed to scan both Indian Equities (Nifty 50) and Cryptocurrencies. The system identifies trend-following setups on a 1-hour timeframe, manages risk with dynamic trailing stops, and visualizes real-time performance through dual Streamlit dashboards.

## System Architecture
* **Nifty Engine:** Fetches live market data using the **Angel One SmartAPI** (handling automated TOTP authentication).
* **Crypto Engine:** Fetches live OHLCV data using the **Binance Public API**.
* **Cloud Infrastructure:** Deployed on an **AWS EC2** instance, running continuously via Linux `screen` sessions.
* **Monitoring:** Live tracking via **Streamlit** dashboards and instant trade notifications via **Telegram Bot API**.

## The Trading Strategy
Both engines operate on a **1-Hour Timeframe** and execute the following logic:

### 1. Trend Identification (The Filter)
A trade is only considered if the broader trend aligns across multiple moving averages:
* **Long Trend:** 100 SMA > 200 SMA, 50 EMA > 100 SMA, and 21 EMA > 50 EMA.
* **Short Trend:** The exact inverse of the above.

### 2. Entry Trigger
* **Long Entry:** 10 EMA crosses *above* the 21 EMA.
* **Short Entry:** 10 EMA crosses *below* the 21 EMA.
* **Position Sizing:** Dynamically calculated based on a fixed percentage of total capital (Capital * Risk Per Trade) divided by the Stop Loss point distance.

### 3. Trade Management & Exits
* **Initial Stop Loss:** Placed just below/above the 21 EMA.
* **Trailing Stop Loss:** * At **1:1 Risk/Reward**, the SL is moved to breakeven.
  * At **2:1 Risk/Reward**, the SL is trailed to lock in 1R profit.
* **Strategy Exit:** The position is closed early if momentum shifts (e.g., for longs, if the 5 EMA crosses *below* the 10 EMA).
* **Brokerage Integration:** All PnL calculations automatically deduct a realistic **0.15% brokerage fee** per trade round-trip for accurate simulation.

## Tech Stack
* **Python** (Pandas, Numpy, Requests)
* **Streamlit** (Data visualization)
* **SmartAPI** (Angel One connection)
* **PyOTP** (Automated 2FA)