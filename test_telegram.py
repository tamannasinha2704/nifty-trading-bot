import requests
import json

# Your Config
TOKEN = "YOUR_TOKEN_HERE"
CHAT_ID = "YOUR_TOKEN_HERE"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": "🔔 Test from Debugger"}

print(f"Attempting to send to Chat ID: {CHAT_ID}...")

# Send and Get Exact Response
response = requests.post(url, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
