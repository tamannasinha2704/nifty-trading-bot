import requests
import json

# Your Config
TOKEN = "8084818503:AAGtnTpRo_WQb6igmrpIyw1ZW_T8kYc-z8Q"
CHAT_ID = "1712000290"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": "🔔 Test from Debugger"}

print(f"Attempting to send to Chat ID: {CHAT_ID}...")

# Send and Get Exact Response
response = requests.post(url, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")