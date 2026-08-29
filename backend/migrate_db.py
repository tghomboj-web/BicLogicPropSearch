import os
from dotenv import load_dotenv
from app import app, db, User, SearchSubscription

load_dotenv()

with app.app_context():
    # Create the new SearchSubscription table
    db.create_all()
    print("Database schema updated successfully!")
    print("New SearchSubscription table created.")
    print("Users will need to create new subscriptions with their preferred frequency.")
