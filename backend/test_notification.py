import os
from dotenv import load_dotenv
from app import app, db, User, Property, send_email_notification, send_telegram_notification, search_properties

load_dotenv()

with app.app_context():
    # Test with user 1 (has zip code 28134 which we know has properties)
    user = User.query.get(1)
    if not user:
        print("No user found with ID 1")
        exit(1)
    
    print(f"Testing notification for user: {user.email}")
    print(f"User criteria: min_price={user.min_price}, max_price={user.max_price}")
    print(f"Zip codes: {user.zip_codes}, Bedrooms: {user.bedrooms}, Bathrooms: {user.bathrooms}")
    
    # Search for properties with user's actual criteria
    criteria = {
        'min_price': user.min_price,
        'max_price': user.max_price,
        'zip_codes': user.zip_codes,
        'property_type': user.property_type,
        'bedrooms': user.bedrooms,
        'bathrooms': user.bathrooms,
        'min_sqft': user.min_sqft
    }
    
    properties = search_properties(criteria)
    print(f"Found {len(properties)} properties matching criteria")
    
    if properties:
        print("\nSending email notification...")
        email_result = send_email_notification(user, properties)
        print(f"Email result: {email_result}")
        
        print("\nSending Telegram notification...")
        telegram_result = send_telegram_notification(user, properties)
        print(f"Telegram result: {telegram_result}")
    else:
        print("No properties found to send notifications")
