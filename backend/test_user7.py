"""
Script to test notification for User ID 7 (Telegram bot registration)
"""
from app import app, db, User, send_email_notification, send_telegram_notification, search_properties

with app.app_context():
    # Get the Telegram bot registered user
    user = User.query.get(7)
    if not user:
        print("User ID 7 not found")
        exit(1)
    
    print(f"Testing notification for user: {user.email}")
    print(f"User ID: {user.id}")
    print(f"Telegram ID: {user.telegram_id}")
    print(f"User criteria: min_price={user.min_price}, max_price={user.max_price}, zip_codes={user.zip_codes}")
    
    # Use their actual search criteria
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
    print(f"Found {len(properties)} properties")
    
    if properties:
        print("\nSending email notification...")
        email_result = send_email_notification(user, properties)
        print(f"Email result: {email_result}")
        
        print("\nSending Telegram notification...")
        telegram_result = send_telegram_notification(user, properties)
        print(f"Telegram result: {telegram_result}")
    else:
        print("No properties found with their criteria, trying broader search...")
        # Try broader search
        broad_criteria = {
            'min_price': None,
            'max_price': None,
            'zip_codes': None,
            'property_type': None,
            'bedrooms': None,
            'bathrooms': None,
            'min_sqft': None
        }
        properties = search_properties(broad_criteria)
        print(f"Found {len(properties)} properties with broad search")
        
        if properties:
            print("\nSending email notification...")
            email_result = send_email_notification(user, properties)
            print(f"Email result: {email_result}")
            
            print("\nSending Telegram notification...")
            telegram_result = send_telegram_notification(user, properties)
            print(f"Telegram result: {telegram_result}")
