import requests
import json

# Your Config
TOKEN = "example"
CHAT_ID = "example"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": "🔔 Test from Debugger"}

print(f"Attempting to send to Chat ID: {CHAT_ID}...")

# Send and Get Exact Response
response = requests.post(url, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
