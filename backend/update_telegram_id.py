"""
Script to update user's Telegram ID
"""
from app import app, db, User

with app.app_context():
    # Get the user
    user = User.query.get(1)
    if user:
        user.telegram_id = "54350627"
        db.session.commit()
        print(f"✅ Updated Telegram ID for user {user.email} to {user.telegram_id}")
    else:
        print("❌ User not found")
