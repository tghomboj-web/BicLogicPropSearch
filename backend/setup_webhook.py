import os
from dotenv import load_dotenv
import requests

load_dotenv()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
webhook_url = 'https://your-domain.com/api/telegram/webhook'  # Replace with your actual URL

print("Setting up Telegram webhook...")
print(f"Bot Token: {bot_token[:10]}...{bot_token[-10:] if bot_token else 'None'}")
print(f"Webhook URL: {webhook_url}")

if not bot_token:
    print("❌ Telegram bot token not configured")
    exit(1)

url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
data = {
    'url': webhook_url
}

response = requests.post(url, data=data)
print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        print(f"✅ Webhook set successfully!")
    else:
        print(f"❌ Failed to set webhook: {data.get('description')}")
else:
    print(f"❌ API error: {response.text}")

# Check current webhook
print("\n--- Checking current webhook ---")
url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
response = requests.get(url)
print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        webhook_info = data.get('result', {})
        print(f"Current webhook URL: {webhook_info.get('url', 'Not set')}")
        print(f"Pending update count: {webhook_info.get('pending_update_count', 0)}")
        print(f"Last error date: {webhook_info.get('last_error_date', 'None')}")
        print(f"Last error message: {webhook_info.get('last_error_message', 'None')}")
