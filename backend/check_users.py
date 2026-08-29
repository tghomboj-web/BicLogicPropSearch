"""
Script to check all users in the database
"""
from app import app, db, User

with app.app_context():
    users = User.query.all()
    print(f"Total users: {len(users)}")
    for user in users:
        print(f"\nUser ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Phone: {user.phone}")
        print(f"Telegram ID: {user.telegram_id}")
        print(f"Created: {user.created_at}")
        print(f"Search Criteria:")
        print(f"  Min Price: {user.min_price}")
        print(f"  Max Price: {user.max_price}")
        print(f"  Zip Codes: {user.zip_codes}")
        print(f"  Property Type: {user.property_type}")
        print(f"  Bedrooms: {user.bedrooms}")
        print(f"  Bathrooms: {user.bathrooms}")
        print(f"  Min Sqft: {user.min_sqft}")
