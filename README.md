NIFTY 50 WEEKLY SWING TRADING BOT

DESCRIPTION This is a Python-based automated trading bot designed for swing trading Nifty 50 stocks. It scans the market using Weekly candles to find trend-following opportunities based on EMA crossovers. It runs automatically on a schedule, logs trades to a local file (Paper Trading), and sends real-time alerts and daily Excel reports via Telegram.

FEATURES

Automated Market Scanning: Runs automatically every Friday between 3:15 PM and 3:30 PM IST (or Thursday if Friday is a holiday).

Telegram Integration: Sends instant alerts for Buy, Sell, and Stop Loss updates.

Daily Reporting: Generates an Excel file of your active portfolio and sends it to your Telegram at 3:45 PM every day.

Risk Management: Automatically calculates trade quantity based on risk percentage and handles partial profit booking.

Data Persistence: Saves all trade data to a JSON file so no data is lost if the server restarts.

STRATEGY LOGIC The bot uses a 4-EMA trend-following strategy on Weekly Candles.

Indicators Used:

EMA 5 (Fast)

EMA 9 (Slow)

EMA 21 (Trend)

EMA 50 (Long Trend)

Buy Conditions (All must be true):

Trend Alignment: EMA 9 is above EMA 21, and EMA 21 is above EMA 50.

Crossover Trigger: EMA 5 crosses above EMA 9.

Momentum Check: All four EMAs (5, 9, 21, 50) are higher than their values from the previous week.

Sell Conditions:

Stop Loss: Price drops below the calculated Stop Loss level.

Death Cross: EMA 5 crosses below EMA 9.

Target & Trailing Logic:

Target 1 (1:1 Risk): Sells 50% of the position and moves Stop Loss to the Entry Price.

Target 2 (1:2 Risk): Trails the Stop Loss up to lock in profits.

INSTALLATION

Clone this repository to your local machine or server.

Install the required Python libraries using the command: pip install yfinance pandas pandas_ta schedule requests openpyxl

Configure your settings in the config.json file (see Configuration section).

CONFIGURATION (config.json) You must update the config.json file with your specific details:

telegram: Add your Bot Token and Chat ID here to receive alerts.

strategy_settings: Adjust your capital, risk percentage, and test mode.

watchlist: List of stock symbols to scan (e.g., RELIANCE.NS, TCS.NS).

HOW TO RUN To start the bot, run the following command in your terminal: python3 bot.py

The bot will print a confirmation message and begin its schedule. It is designed to run 24/7 on a cloud server (like AWS EC2).

FILES IN THIS REPOSITORY

bot.py: The main script containing the strategy, scheduling, and telegram logic.

config.json: Configuration file for user settings and watchlist.

trades.json: Automatically created file that stores your active and closed trades.

DISCLAIMER This software is for educational purposes only. Do not risk money you cannot afford to lose. The authors are not responsible for any financial losses incurred from using this code.
