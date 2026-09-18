import os
from dotenv import load_dotenv
from app import app, db, User, SearchSubscription, TelegramConnectionCode

load_dotenv()

with app.app_context():
    # Create all tables including the new TelegramConnectionCode table
    db.create_all()
    print("Database schema updated successfully!")
    print("New TelegramConnectionCode table created for code-based Telegram linking.")
    print("Existing SearchSubscription table maintained.")
