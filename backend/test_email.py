import os
from dotenv import load_dotenv
import smtplib

load_dotenv()

print("Testing Email Configuration...")
print(f"SMTP Server: {os.getenv('SMTP_SERVER')}")
print(f"SMTP Port: {os.getenv('SMTP_PORT')}")
print(f"SMTP Username: {os.getenv('SMTP_USERNAME')}")
print(f"SMTP Password: {os.getenv('SMTP_PASSWORD')}")

try:
    server = smtplib.SMTP(os.getenv('SMTP_SERVER', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', '587')))
    server.starttls()
    server.login(os.getenv('SMTP_USERNAME'), os.getenv('SMTP_PASSWORD'))
    print("✅ Email configuration is working!")
    server.quit()
except Exception as e:
    print(f"❌ Email configuration failed: {e}")
    print("\nPlease check your SMTP password - it should be a 16-character app password without spaces.")
