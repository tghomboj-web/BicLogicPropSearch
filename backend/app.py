from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
from datetime import datetime
import atexit

# Telegram polling state
telegram_conversation_state = {}  # Store conversation state for each user

load_dotenv()

app = Flask(__name__)
CORS(app)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///property_noti.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    telegram_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'phone': self.phone,
            'telegram_id': self.telegram_id,
            'created_at': self.created_at.isoformat()
        }

class SearchSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_frequency = db.Column(db.String(20), nullable=False)  # 'once', 'daily', 'weekly', 'monthly'
    last_notified = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Search criteria
    min_price = db.Column(db.Integer, nullable=True)
    max_price = db.Column(db.Integer, nullable=True)
    zip_codes = db.Column(db.String(200), nullable=True)
    property_type = db.Column(db.String(50), nullable=True)
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    min_sqft = db.Column(db.Integer, nullable=True)
    
    user = db.relationship('User', backref=db.backref('subscriptions', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'notification_frequency': self.notification_frequency,
            'last_notified': self.last_notified.isoformat() if self.last_notified else None,
            'created_at': self.created_at.isoformat(),
            'min_price': self.min_price,
            'max_price': self.max_price,
            'zip_codes': self.zip_codes,
            'property_type': self.property_type,
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms,
            'min_sqft': self.min_sqft
        }

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(300), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    property_type = db.Column(db.String(50), nullable=True)
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    sqft = db.Column(db.Integer, nullable=True)
    url = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    listed_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'price': self.price,
            'address': self.address,
            'zip_code': self.zip_code,
            'property_type': self.property_type,
            'bedrooms': self.bedrooms,
            'bathrooms': self.bathrooms,
            'sqft': self.sqft,
            'url': self.url,
            'description': self.description,
            'listed_date': self.listed_date.isoformat()
        }

# Initialize database
with app.app_context():
    db.create_all()

# Real property search using Searchapi.io (Zillow API)
def search_properties(criteria):
    """Search for properties matching user criteria using Searchapi.io Zillow API"""
    searchapi_key = os.getenv('SEARCHAPI_API_KEY')
    
    print(f"Search criteria: {criteria}")
    print(f"Searchapi.io API Key configured: {bool(searchapi_key)}")
    
    # Fall back to database search if API credentials not configured
    if not searchapi_key:
        print("Searchapi.io API key not configured, using database search")
        return search_properties_database(criteria)
    
    # Build location query
    location = ""
    if criteria.get('zip_codes'):
        zip_list = [z.strip() for z in criteria['zip_codes'].split(',')]
        location = zip_list[0]  # Use first zip code for search
    else:
        location = "United States"  # Default to broad search
    
    try:
        url = "https://www.searchapi.io/api/v1/search"
        params = {
            'engine': 'zillow',
            'api_key': searchapi_key,
            'q': location,
            'num': 20  # Get more results to filter locally
        }
        
        # Don't use API filters - they cause location bugs
        # We'll filter locally instead
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            properties = []
            
            # Get requested zip codes for filtering
            requested_zips = []
            if criteria.get('zip_codes'):
                requested_zips = [z.strip() for z in criteria['zip_codes'].split(',')]
            
            for item in data.get('properties', []):
                item_zip = item.get('zipcode', '')
                
                # Apply zip code filtering
                if requested_zips and item_zip not in requested_zips:
                    continue
                
                # Extract property data
                price = int(item.get('extracted_price', 0))
                beds = item.get('beds')
                baths = item.get('baths')
                sqft = item.get('sqft')
                home_type = item.get('home_type', '')
                
                # Apply price filtering
                if criteria.get('min_price') and price > 0 and price < criteria['min_price']:
                    continue
                if criteria.get('max_price') and price > 0 and price > criteria['max_price']:
                    continue
                
                # Apply bedroom filtering
                if criteria.get('bedrooms') and beds and beds < criteria['bedrooms']:
                    continue
                
                # Apply bathroom filtering
                if criteria.get('bathrooms') and baths and baths < criteria['bathrooms']:
                    continue
                
                # Apply sqft filtering
                if criteria.get('min_sqft') and sqft and sqft < criteria['min_sqft']:
                    continue
                
                # Apply property type filtering
                if criteria.get('property_type'):
                    type_mapping = {
                        'house': 'SINGLE_FAMILY',
                        'condo': 'CONDO',
                        'townhouse': 'TOWNHOUSE',
                        'multi-family': 'MULTI_FAMILY',
                        'land': 'LOT'
                    }
                    expected_type = type_mapping.get(criteria['property_type'].lower(), '')
                    if expected_type and home_type != expected_type:
                        continue
                
                property_data = {
                    'title': item.get('address', 'Property Listing'),
                    'price': price,
                    'address': item.get('address', ''),
                    'zip_code': item_zip,
                    'property_type': home_type,
                    'bedrooms': beds,
                    'bathrooms': baths,
                    'sqft': sqft,
                    'url': f"https://www.zillow.com/homedetails/{item.get('zpid')}_zpid/" if item.get('zpid') else '',
                    'description': f"{item.get('status_text', 'Property for sale')} - {item.get('days_on_zillow', 0)} days on Zillow"
                }
                
                properties.append(property_data)
                
                if len(properties) >= 5:
                    break
            
            # Log results
            if requested_zips:
                print(f"Found {len(properties)} properties in exact zip codes {requested_zips}")
                if len(properties) == 0:
                    print(f"No properties found in exact zip codes {requested_zips}")
                    print("Falling back to database search")
                    return search_properties_database(criteria)
            else:
                print(f"Found {len(properties)} properties via Searchapi.io (no zip filter)")
            
            return properties
        else:
            print(f"Searchapi.io error: {response.status_code} - {response.text}")
            return search_properties_database(criteria)
            
    except Exception as e:
        print(f"Error searching Searchapi.io: {e}")
        import traceback
        traceback.print_exc()
        return search_properties_database(criteria)

def search_properties_database(criteria):
    """Fallback search using local database"""
    query = Property.query
    
    if criteria.get('min_price'):
        query = query.filter(Property.price >= criteria['min_price'])
    if criteria.get('max_price'):
        query = query.filter(Property.price <= criteria['max_price'])
    if criteria.get('zip_codes'):
        zip_list = [z.strip() for z in criteria['zip_codes'].split(',')]
        query = query.filter(Property.zip_code.in_(zip_list))
    if criteria.get('property_type'):
        query = query.filter(Property.property_type == criteria['property_type'])
    if criteria.get('bedrooms') and criteria['bedrooms'] > 0:
        query = query.filter(Property.bedrooms >= criteria['bedrooms'])
    if criteria.get('bathrooms') and criteria['bathrooms'] > 0:
        query = query.filter(Property.bathrooms >= criteria['bathrooms'])
    if criteria.get('min_sqft') and criteria['min_sqft'] > 0:
        query = query.filter(Property.sqft >= criteria['min_sqft'])
    
    properties = query.limit(5).all()
    return [p.to_dict() for p in properties]

# Email notification
def send_email_notification(user, properties):
    """Send email notification with matching properties"""
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        print(f"Email notification attempt:")
        print(f"  To: {user.email}")
        print(f"  SMTP Server: {smtp_server}")
        print(f"  SMTP Port: {smtp_port}")
        print(f"  SMTP Username: {smtp_username}")
        print(f"  SMTP Password configured: {bool(smtp_password)}")
        print(f"  Properties to send: {len(properties)}")
        
        if not smtp_username or not smtp_password:
            print("SMTP credentials not configured")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'New Property Matches Found!'
        msg['From'] = smtp_username
        msg['To'] = user.email
        
        html_content = f"""
        <html>
        <body>
            <h2>New Properties Matching Your Criteria</h2>
            <p>Hi! We found {len(properties)} new properties that match your search criteria:</p>
            <br>
        """
        
        for prop in properties:
            html_content += f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h3>{prop['title']}</h3>
                <p><strong>Price:</strong> ${prop['price']:,}</p>
                <p><strong>Address:</strong> {prop['address']}</p>
                <p><strong>Zip Code:</strong> {prop['zip_code']}</p>
                <p><strong>Type:</strong> {prop['property_type'] or 'N/A'}</p>
                <p><strong>Bedrooms:</strong> {prop['bedrooms'] or 'N/A'}</p>
                <p><strong>Bathrooms:</strong> {prop['bathrooms'] or 'N/A'}</p>
                <p><strong>Sqft:</strong> {prop['sqft'] or 'N/A'}</p>
                {f'<p><a href="{prop["url"]}">View Property</a></p>' if prop['url'] else ''}
            </div>
            <br>
            """
        
        html_content += """
            <p>Best regards,<br>Property Notification Team</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        print("Attempting to connect to SMTP server...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        print("SMTP server connected, starting TLS...")
        server.starttls()
        print("TLS started, attempting login...")
        server.login(smtp_username, smtp_password)
        print("Login successful, sending message...")
        server.send_message(msg)
        print("Message sent, quitting...")
        server.quit()
        
        print(f"✅ Email sent to {user.email}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        import traceback
        traceback.print_exc()
        return False

# Telegram notification
def send_telegram_notification(user, properties):
    """Send Telegram notification with matching properties"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token or not user.telegram_id:
            print("Telegram bot token or user telegram_id not configured")
            return False
        
        message = f"🏠 <b>New Property Matches Found!</b>\n\n"
        message += f"We found {len(properties)} new properties matching your criteria:\n\n"
        
        for i, prop in enumerate(properties, 1):
            message += f"<b>{i}. {prop['title']}</b>\n"
            message += f"💰 Price: ${prop['price']:,}\n"
            message += f"📍 Address: {prop['address']}\n"
            message += f"📮 Zip: {prop['zip_code']}\n"
            if prop['property_type']:
                message += f"🏠 Type: {prop['property_type']}\n"
            if prop['bedrooms']:
                message += f"🛏️ Bedrooms: {prop['bedrooms']}\n"
            if prop['bathrooms']:
                message += f"🚿 Bathrooms: {prop['bathrooms']}\n"
            if prop['sqft']:
                message += f"📐 Sqft: {prop['sqft']}\n"
            if prop['url']:
                message += f"🔗 <a href=\"{prop['url']}\">View Property</a>\n"
            message += "\n"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': user.telegram_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print(f"Telegram message sent to {user.telegram_id}")
            return True
        else:
            print(f"Telegram API error: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        import traceback
        traceback.print_exc()
        return False

# Scheduled task to check for new properties
def check_and_notify_users():
    """Check all subscriptions and send notifications for matching properties"""
    print("Running scheduled property check...")
    with app.app_context():
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        subscriptions = SearchSubscription.query.all()
        for sub in subscriptions:
            # Check if subscription needs notification based on frequency
            should_notify = False
            
            if sub.notification_frequency == 'once':
                continue  # One-time subscriptions don't get recurring notifications
            elif sub.notification_frequency == 'daily':
                if not sub.last_notified or (now - sub.last_notified) >= timedelta(hours=24):
                    should_notify = True
            elif sub.notification_frequency == 'weekly':
                if not sub.last_notified or (now - sub.last_notified) >= timedelta(days=7):
                    should_notify = True
            elif sub.notification_frequency == 'monthly':
                if not sub.last_notified or (now - sub.last_notified) >= timedelta(days=30):
                    should_notify = True
            
            if should_notify:
                criteria = {
                    'min_price': sub.min_price,
                    'max_price': sub.max_price,
                    'zip_codes': sub.zip_codes,
                    'property_type': sub.property_type,
                    'bedrooms': sub.bedrooms,
                    'bathrooms': sub.bathrooms,
                    'min_sqft': sub.min_sqft
                }
                
                properties = search_properties(criteria)
                
                if properties:
                    user = sub.user
                    send_email_notification(user, properties)
                    send_telegram_notification(user, properties)
                    sub.last_notified = now
                    db.session.commit()

# API Routes
@app.route('/api/search', methods=['POST'])
def search():
    """One-time property search"""
    data = request.json
    try:
        # Find or create user
        user = User.query.filter_by(email=data.get('email')).first()
        if not user:
            user = User(
                email=data.get('email'),
                phone=data.get('phone'),
                telegram_id=data.get('telegram_id')
            )
            db.session.add(user)
            db.session.commit()
        
        # Search for properties
        criteria = {
            'min_price': data.get('min_price'),
            'max_price': data.get('max_price'),
            'zip_codes': data.get('zip_codes'),
            'property_type': data.get('property_type'),
            'bedrooms': data.get('bedrooms'),
            'bathrooms': data.get('bathrooms'),
            'min_sqft': data.get('min_sqft')
        }
        
        properties = search_properties(criteria)
        
        # Send notifications if properties found
        if properties:
            send_email_notification(user, properties)
            send_telegram_notification(user, properties)
        
        return jsonify({
            'success': True,
            'properties_found': len(properties),
            'properties': properties
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    """Create a subscription for recurring notifications"""
    data = request.json
    try:
        # Validate required fields
        if not data.get('email'):
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        # Validate price range
        min_price = data.get('min_price')
        max_price = data.get('max_price')
        if min_price is not None and max_price is not None:
            if min_price > max_price:
                return jsonify({'success': False, 'error': 'Min price cannot be greater than max price'}), 400
        
        # Validate zip codes for subscription
        if not data.get('zip_codes'):
            return jsonify({'success': False, 'error': 'At least one zip code is required for property subscription'}), 400
        
        # Validate notification frequency
        valid_frequencies = ['once', 'daily', 'weekly', 'monthly']
        frequency = data.get('notification_frequency', 'daily')
        if frequency not in valid_frequencies:
            return jsonify({'success': False, 'error': 'Invalid notification frequency'}), 400
        
        # Find or create user
        user = User.query.filter_by(email=data.get('email')).first()
        if not user:
            user = User(
                email=data.get('email'),
                phone=data.get('phone'),
                telegram_id=data.get('telegram_id')
            )
            db.session.add(user)
            db.session.commit()
        
        # Create subscription
        subscription = SearchSubscription(
            user_id=user.id,
            notification_frequency=frequency,
            min_price=data.get('min_price'),
            max_price=data.get('max_price'),
            zip_codes=data.get('zip_codes'),
            property_type=data.get('property_type'),
            bedrooms=data.get('bedrooms'),
            bathrooms=data.get('bathrooms'),
            min_sqft=data.get('min_sqft')
        )
        db.session.add(subscription)
        db.session.commit()
        
        # Send immediate notification if properties found
        criteria = {
            'min_price': subscription.min_price,
            'max_price': subscription.max_price,
            'zip_codes': subscription.zip_codes,
            'property_type': subscription.property_type,
            'bedrooms': subscription.bedrooms,
            'bathrooms': subscription.bathrooms,
            'min_sqft': subscription.min_sqft
        }
        
        properties = search_properties(criteria)
        
        if properties:
            send_email_notification(user, properties)
            send_telegram_notification(user, properties)
            subscription.last_notified = datetime.utcnow()
            db.session.commit()
        
        return jsonify({
            'success': True,
            'subscription_id': subscription.id,
            'properties_found': len(properties),
            'properties': properties
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/signup', methods=['POST'])
def signup():
    """Legacy signup endpoint - redirects to subscribe"""
    return subscribe()

@app.route('/api/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

@app.route('/api/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    return jsonify([prop.to_dict() for prop in properties])

@app.route('/api/properties', methods=['POST'])
def add_property():
    data = request.json
    try:
        property = Property(
            title=data.get('title'),
            price=data.get('price'),
            address=data.get('address'),
            zip_code=data.get('zip_code'),
            property_type=data.get('property_type'),
            bedrooms=data.get('bedrooms'),
            bathrooms=data.get('bathrooms'),
            sqft=data.get('sqft'),
            url=data.get('url'),
            description=data.get('description')
        )
        db.session.add(property)
        db.session.commit()
        return jsonify({'success': True, 'property': property.to_dict()}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/test-notification/<int:user_id>', methods=['POST'])
def test_notification(user_id):
    user = User.query.get_or_404(user_id)
    # Use broader criteria for testing
    criteria = {
        'min_price': None,  # Remove price filter for testing
        'max_price': None,
        'zip_codes': None,  # Remove zip code filter for testing
        'property_type': None,
        'bedrooms': None,
        'bathrooms': None,
        'min_sqft': None
    }
    print(f"Test notification for user {user_id} with criteria: {criteria}")
    properties = search_properties(criteria)
    print(f"Found {len(properties)} properties")
    
    if properties:
        email_sent = send_email_notification(user, properties)
        telegram_sent = send_telegram_notification(user, properties)
    else:
        email_sent = False
        telegram_sent = False
    
    return jsonify({
        'success': True,
        'email_sent': email_sent,
        'telegram_sent': telegram_sent,
        'properties_found': len(properties),
        'properties': properties
    })

@app.route('/api/quick-search', methods=['POST'])
def quick_search():
    """One-time property search"""
    data = request.json
    try:
        # Validate required fields
        if not data.get('email'):
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        # Validate price range
        min_price = data.get('min_price')
        max_price = data.get('max_price')
        if min_price is not None and max_price is not None:
            if min_price > max_price:
                return jsonify({'success': False, 'error': 'Min price cannot be greater than max price'}), 400
        
        # Validate zip codes for search
        if not data.get('zip_codes'):
            return jsonify({'success': False, 'error': 'At least one zip code is required for property search'}), 400
        
        # Find or create user
        user = User.query.filter_by(email=data.get('email')).first()
        if not user:
            user = User(
                email=data.get('email'),
                phone=data.get('phone'),
                telegram_id=data.get('telegram_id')
            )
            db.session.add(user)
            db.session.commit()
        
        # Search for properties
        criteria = {
            'min_price': data.get('min_price'),
            'max_price': data.get('max_price'),
            'zip_codes': data.get('zip_codes'),
            'property_type': data.get('property_type'),
            'bedrooms': data.get('bedrooms'),
            'bathrooms': data.get('bathrooms'),
            'min_sqft': data.get('min_sqft')
        }
        
        properties = search_properties(criteria)
        
        # Send notifications if properties found
        if properties:
            send_email_notification(user, properties)
            send_telegram_notification(user, properties)
        
        return jsonify({
            'success': True,
            'properties_found': len(properties),
            'properties': properties
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_and_notify_users, trigger="interval", hours=1)  # Check hourly
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

@app.route('/')
def home():
    return jsonify({
        'message': 'Property Notification API',
        'version': '1.0.0',
        'endpoints': {
            'signup': '/api/signup',
            'users': '/api/users',
            'properties': '/api/properties',
            'search': '/api/search',
            'test_notification': '/api/test-notification/<user_id>',
            'telegram_webhook': '/api/telegram/webhook'
        }
    })

# Telegram webhook endpoint
@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Handle incoming Telegram messages"""
    data = request.json
    message = data.get('message', {})
    
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '').strip()
    
    if not chat_id or not text:
        return jsonify({'ok': True})
    
    # Find user by telegram_id
    user = User.query.filter_by(telegram_id=str(chat_id)).first()
    
    # Handle commands
    if text == '/start':
        response = "🏠 Welcome to PropertyNoti Bot!\n\n"
        response += "Available commands:\n"
        response += "/search - Search for properties now\n"
        response += "/status - View your current search criteria\n"
        response += "/help - Show this help message\n\n"
        response += "To get started, sign up at the website and provide your Telegram ID."
        send_telegram_message(chat_id, response)
    
    elif text == '/help':
        response = "🏠 PropertyNoti Bot Commands:\n\n"
        response += "/search - Search for properties matching your criteria\n"
        response += "/status - View your current search criteria\n"
        response += "/help - Show this help message\n\n"
        response += "Note: You need to sign up at the website first with your Telegram ID."
        send_telegram_message(chat_id, response)
    
    elif text == '/status':
        if user:
            response = f"📋 Your Search Criteria:\n\n"
            response += f"Email: {user.email}\n"
            response += f"Price Range: ${user.min_price or 'Any'} - ${user.max_price or 'Any'}\n"
            response += f"Zip Codes: {user.zip_codes or 'Not specified'}\n"
            response += f"Property Type: {user.property_type or 'Any'}\n"
            response += f"Bedrooms: {user.bedrooms or 'Any'}\n"
            response += f"Bathrooms: {user.bathrooms or 'Any'}\n"
            response += f"Min Sqft: {user.min_sqft or 'Any'}\n"
            send_telegram_message(chat_id, response)
        else:
            response = "❌ No account found with your Telegram ID.\n"
            response += "Please sign up at the website and provide your Telegram ID."
            send_telegram_message(chat_id, response)
    
    elif text == '/search':
        if user:
            send_telegram_message(chat_id, "🔍 Searching for properties...")
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
            
            if properties:
                send_telegram_notification(user, properties)
            else:
                send_telegram_message(chat_id, "❌ No properties found matching your criteria.")
        else:
            response = "❌ No account found with your Telegram ID.\n"
            response += "Please sign up at the website and provide your Telegram ID."
            send_telegram_message(chat_id, response)
    
    else:
        response = "❓ Unknown command. Type /help for available commands."
        send_telegram_message(chat_id, response)
    
    return jsonify({'ok': True})

def send_telegram_message(chat_id, text, reply_markup=None):
    """Send a simple text message via Telegram"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            import json
            data['reply_markup'] = json.dumps(reply_markup)
        
        print(f"Sending message to chat_id: {chat_id}")
        print(f"Message text: {text[:100]}...")
        print(f"Reply markup: {reply_markup}")
        
        response = requests.post(url, data=data)
        print(f"Telegram API response: {response.status_code}")
        print(f"Response body: {response.text}")
        
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        import traceback
        traceback.print_exc()

def process_telegram_update(update):
    """Process a single Telegram update"""
    try:
        print(f"Processing update: {update}")
        
        # Handle callback queries from inline keyboards
        callback_query = update.get('callback_query')
        if callback_query:
            chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
            callback_data = callback_query.get('data')
            user = User.query.filter_by(telegram_id=str(chat_id)).first()
            
            print(f"Callback query: chat_id={chat_id}, data={callback_data}")
            
            if callback_data == 'search_now':
                # Start conversational search flow
                telegram_conversation_state[str(chat_id)] = {
                    'step': 'zip_codes',
                    'criteria': {}
                }
                response = "🔍 <b>New Property Search</b>\n\n"
                response += "Let's set up your search criteria step by step.\n\n"
                response += "First, what zip code(s) would you like to search in?\n"
                response += "You can enter multiple zip codes separated by commas."
                send_telegram_message(chat_id, response)
            
            # Handle skip button callbacks
            elif callback_data == 'skip_min_price':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'max_price'
                    state['criteria']['min_price'] = None
                    response = "What's your maximum price?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_max_price'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_max_price':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'bedrooms'
                    state['criteria']['max_price'] = None
                    response = "How many bedrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_bedrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_bedrooms':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'bathrooms'
                    state['criteria']['bedrooms'] = None
                    response = "How many bathrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_bathrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_bathrooms':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'property_type'
                    state['criteria']['bathrooms'] = None
                    response = "What property type are you looking for?\n\n"
                    response += "Options: house, apartment, condo, townhouse, land"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_property_type'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_property_type':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'min_sqft'
                    state['criteria']['property_type'] = None
                    response = "What's the minimum square footage?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_min_sqft'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_min_sqft':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['criteria']['min_sqft'] = None
                    # Execute search
                    del telegram_conversation_state[str(chat_id)]
                    
                    user = User.query.filter_by(telegram_id=str(chat_id)).first()
                    if not user:
                        user = User(
                            email=f"telegram_{chat_id}@temp.com",
                            telegram_id=str(chat_id)
                        )
                        db.session.add(user)
                        db.session.commit()
                    
                    send_telegram_message(chat_id, "🔍 Searching for properties...")
                    properties = search_properties(state['criteria'])
                    
                    if properties:
                        send_telegram_notification(user, properties)
                        send_telegram_message(chat_id, f"✅ Found {len(properties)} properties matching your criteria!")
                    else:
                        send_telegram_message(chat_id, "❌ No properties found matching your criteria.")
            
            # Handle subscription skip button callbacks
            elif callback_data == 'skip_sub_min_price':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'sub_max_price'
                    state['criteria']['min_price'] = None
                    response = "What's your maximum price?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_max_price'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_sub_max_price':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'sub_bedrooms'
                    state['criteria']['max_price'] = None
                    response = "How many bedrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_bedrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_sub_bedrooms':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'sub_bathrooms'
                    state['criteria']['bedrooms'] = None
                    response = "How many bathrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_bathrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_sub_bathrooms':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'sub_property_type'
                    state['criteria']['bathrooms'] = None
                    response = "What property type are you looking for?\n\n"
                    response += "Options: house, apartment, condo, townhouse, land"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_property_type'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_sub_property_type':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['step'] = 'sub_min_sqft'
                    state['criteria']['property_type'] = None
                    response = "What's the minimum square footage?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_min_sqft'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data == 'skip_sub_min_sqft':
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    state['criteria']['min_sqft'] = None
                    state['step'] = 'sub_frequency'
                    response = "How often would you like to receive notifications?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '📅 Daily', 'callback_data': 'freq_daily'}],
                            [{'text': '📆 Weekly', 'callback_data': 'freq_weekly'}],
                            [{'text': '🗓️ Monthly', 'callback_data': 'freq_monthly'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
            
            elif callback_data in ['freq_daily', 'freq_weekly', 'freq_monthly']:
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    frequency = callback_data.replace('freq_', '')
                    state['criteria']['notification_frequency'] = frequency
                    # Execute subscription creation
                    del telegram_conversation_state[str(chat_id)]
                    
                    user = User.query.filter_by(telegram_id=str(chat_id)).first()
                    if not user:
                        user = User(
                            email=f"telegram_{chat_id}@temp.com",
                            telegram_id=str(chat_id)
                        )
                        db.session.add(user)
                        db.session.commit()
                    
                    # Create subscription
                    subscription = SearchSubscription(
                        user_id=user.id,
                        notification_frequency=state['criteria']['notification_frequency'],
                        min_price=state['criteria'].get('min_price'),
                        max_price=state['criteria'].get('max_price'),
                        zip_codes=state['criteria'].get('zip_codes'),
                        property_type=state['criteria'].get('property_type'),
                        bedrooms=state['criteria'].get('bedrooms'),
                        bathrooms=state['criteria'].get('bathrooms'),
                        min_sqft=state['criteria'].get('min_sqft')
                    )
                    db.session.add(subscription)
                    db.session.commit()
                    
                    send_telegram_message(chat_id, f"✅ Subscription created successfully!\n\nYou will receive {frequency} notifications for properties matching your criteria.")
            elif callback_data == 'subscribe':
                # Start conversational subscription flow
                telegram_conversation_state[str(chat_id)] = {
                    'step': 'sub_zip_codes',
                    'criteria': {}
                }
                response = "📧 <b>Subscribe for Alerts</b>\n\n"
                response += "Let's set up your subscription step by step.\n\n"
                response += "First, what zip code(s) would you like to subscribe to?\n"
                response += "You can enter multiple zip codes separated by commas."
                send_telegram_message(chat_id, response)
            elif callback_data == 'status':
                if user:
                    subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                    if subscriptions:
                        response = f"📋 Your Subscriptions:\n\n"
                        for i, sub in enumerate(subscriptions, 1):
                            response += f"<b>{i}. ID: {sub.id} - {sub.notification_frequency.upper()}</b>\n"
                            response += f"Price: ${sub.min_price or 'Any'} - ${sub.max_price or 'Any'}\n"
                            response += f"Zip: {sub.zip_codes or 'Not specified'}\n"
                            response += f"Type: {sub.property_type or 'Any'}\n"
                            response += f"Beds: {sub.bedrooms or 'Any'} | Baths: {sub.bathrooms or 'Any'}\n"
                            response += f"Last notified: {sub.last_notified.strftime('%Y-%m-%d %H:%M') if sub.last_notified else 'Never'}\n\n"
                        response += "Use /delete <id> to remove a subscription"
                    else:
                        response = "❌ No subscriptions found.\n"
                        response += "Sign up at the website to create subscriptions."
                    send_telegram_message(chat_id, response)
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.")
            elif callback_data == 'delete':
                if user:
                    subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                    if subscriptions:
                        response = f"🗑️ <b>Delete Subscriptions</b>\n\n"
                        response += "Your subscriptions:\n\n"
                        for i, sub in enumerate(subscriptions, 1):
                            response += f"{i}. ID: {sub.id} - {sub.notification_frequency.upper()}\n"
                        response += "\nUse /delete <id> to remove a specific subscription\n"
                        response += "Use /deleteall to remove all subscriptions"
                        send_telegram_message(chat_id, response)
                    else:
                        send_telegram_message(chat_id, "❌ No subscriptions to delete.")
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.")
            
            # Answer the callback query
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
            requests.post(url, json={'callback_query_id': callback_query.get('id')})
            return
        
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        
        print(f"Message: chat_id={chat_id}, text={text}")
        print(f"Full message object: {message}")
        
        if not chat_id:
            print("No chat_id found in message")
            return
        
        if not text:
            print("No text found in message")
            return
        
        # Find user by telegram_id
        user = User.query.filter_by(telegram_id=str(chat_id)).first()
        print(f"User found: {user is not None}")
        
        # Handle commands
        if text == '/start':
            response = "🏠 Welcome to PropertyNoti Bot!\n\n"
            response += "What would you like to do?"
            
            # Create inline keyboard
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': '🔍 One-time Search', 'callback_data': 'search_now'},
                        {'text': '📧 Subscribe for Alerts', 'callback_data': 'subscribe'}
                    ],
                    [
                        {'text': '📋 View Subscriptions', 'callback_data': 'status'},
                        {'text': '🗑️ Delete Subscriptions', 'callback_data': 'delete'}
                    ]
                ]
            }
            
            print(f"Sending /start response to chat_id: {chat_id}")
            send_telegram_message(chat_id, response, keyboard)
            print(f"/start response sent")
        
        elif text == '/newsearch':
            response = "🔍 <b>New Property Search</b>\n\n"
            response += "Please provide your search criteria in this format:\n\n"
            response += "<code>zip_codes,min_price,max_price,bedrooms,bathrooms</code>\n\n"
            response += "Example: <code>28202,100000,500000,2,1</code>\n\n"
            response += "You can omit values you don't need: <code>28202,100000,500000</code>"
            send_telegram_message(chat_id, response)
        
        # Handle conversational search flow
        elif str(chat_id) in telegram_conversation_state:
            state = telegram_conversation_state[str(chat_id)]
            step = state['step']
            criteria = state['criteria']
            
            print(f"Conversational flow: chat_id={chat_id}, step={step}, text={text}")
            
            # Subscription flow
            if step.startswith('sub_'):
                if step == 'sub_zip_codes':
                    criteria['zip_codes'] = text.strip()
                    state['step'] = 'sub_min_price'
                    response = "Great! What's your minimum price?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_min_price'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_min_price':
                    if text.lower() != 'skip':
                        try:
                            criteria['min_price'] = int(text.strip())
                        except:
                            send_telegram_message(chat_id, "❌ Invalid price. Please enter a number or use the skip button.")
                            return
                    state['step'] = 'sub_max_price'
                    response = "What's your maximum price?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_max_price'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_max_price':
                    if text.lower() != 'skip':
                        try:
                            criteria['max_price'] = int(text.strip())
                        except:
                            send_telegram_message(chat_id, "❌ Invalid price. Please enter a number or use the skip button.")
                            return
                    
                    if criteria.get('min_price') and criteria.get('max_price') and criteria['min_price'] > criteria['max_price']:
                        send_telegram_message(chat_id, "❌ Invalid price range: Min price cannot be greater than max price. Please enter max price again.")
                        return
                    
                    state['step'] = 'sub_bedrooms'
                    response = "How many bedrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_bedrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_bedrooms':
                    if text.lower() != 'skip':
                        try:
                            criteria['bedrooms'] = int(text.strip())
                        except:
                            send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                            return
                    state['step'] = 'sub_bathrooms'
                    response = "How many bathrooms do you need?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_bathrooms'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_bathrooms':
                    if text.lower() != 'skip':
                        try:
                            criteria['bathrooms'] = float(text.strip())
                        except:
                            send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                            return
                    state['step'] = 'sub_property_type'
                    response = "What property type are you looking for?\n\n"
                    response += "Options: house, apartment, condo, townhouse, land"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_property_type'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_property_type':
                    if text.lower() != 'skip':
                        valid_types = ['house', 'apartment', 'condo', 'townhouse', 'land']
                        if text.lower() in valid_types:
                            criteria['property_type'] = text.lower()
                        else:
                            send_telegram_message(chat_id, f"❌ Invalid type. Choose from: {', '.join(valid_types)} or use the skip button.")
                            return
                    state['step'] = 'sub_min_sqft'
                    response = "What's the minimum square footage?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '⏭️ Skip', 'callback_data': 'skip_sub_min_sqft'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_min_sqft':
                    if text.lower() != 'skip':
                        try:
                            criteria['min_sqft'] = int(text.strip())
                        except:
                            send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                            return
                    
                    state['step'] = 'sub_frequency'
                    response = "How often would you like to receive notifications?"
                    keyboard = {
                        'inline_keyboard': [
                            [{'text': '📅 Daily', 'callback_data': 'freq_daily'}],
                            [{'text': '📆 Weekly', 'callback_data': 'freq_weekly'}],
                            [{'text': '🗓️ Monthly', 'callback_data': 'freq_monthly'}]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                return
            
            # Search flow
            if step == 'zip_codes':
                criteria['zip_codes'] = text.strip()
                state['step'] = 'min_price'
                response = "Great! What's your minimum price?"
                
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_min_price'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'min_price':
                if text.lower() != 'skip':
                    try:
                        criteria['min_price'] = int(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid price. Please enter a number or use the skip button.")
                        return
                state['step'] = 'max_price'
                response = "What's your maximum price?"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_max_price'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'max_price':
                if text.lower() != 'skip':
                    try:
                        criteria['max_price'] = int(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid price. Please enter a number or use the skip button.")
                        return
                
                # Validate price range
                if criteria.get('min_price') and criteria.get('max_price') and criteria['min_price'] > criteria['max_price']:
                    send_telegram_message(chat_id, "❌ Invalid price range: Min price cannot be greater than max price. Please enter max price again.")
                    return
                
                state['step'] = 'bedrooms'
                response = "How many bedrooms do you need?"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_bedrooms'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'bedrooms':
                if text.lower() != 'skip':
                    try:
                        criteria['bedrooms'] = int(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                        return
                state['step'] = 'bathrooms'
                response = "How many bathrooms do you need?"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_bathrooms'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'bathrooms':
                if text.lower() != 'skip':
                    try:
                        criteria['bathrooms'] = float(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                        return
                state['step'] = 'property_type'
                response = "What property type are you looking for?\n\n"
                response += "Options: house, apartment, condo, townhouse, land"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_property_type'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'property_type':
                if text.lower() != 'skip':
                    valid_types = ['house', 'apartment', 'condo', 'townhouse', 'land']
                    if text.lower() in valid_types:
                        criteria['property_type'] = text.lower()
                    else:
                        send_telegram_message(chat_id, f"❌ Invalid type. Choose from: {', '.join(valid_types)} or use the skip button.")
                        return
                state['step'] = 'min_sqft'
                response = "What's the minimum square footage?"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '⏭️ Skip', 'callback_data': 'skip_min_sqft'}]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'min_sqft':
                if text.lower() != 'skip':
                    try:
                        criteria['min_sqft'] = int(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                        return
                
                # Search is complete, execute it
                del telegram_conversation_state[str(chat_id)]
                
                # Find or create user
                if not user:
                    user = User(
                        email=f"telegram_{chat_id}@temp.com",
                        telegram_id=str(chat_id)
                    )
                    db.session.add(user)
                    db.session.commit()
                
                send_telegram_message(chat_id, "🔍 Searching for properties...")
                properties = search_properties(criteria)
                
                if properties:
                    send_telegram_notification(user, properties)
                    send_telegram_message(chat_id, f"✅ Found {len(properties)} properties matching your criteria!")
                else:
                    send_telegram_message(chat_id, "❌ No properties found matching your criteria.")
            
            return
        
        elif text.startswith('/delete '):
            # Delete specific subscription
            try:
                sub_id = int(text.split()[1])
                subscription = SearchSubscription.query.get(sub_id)
                if subscription and subscription.user_id == user.id:
                    db.session.delete(subscription)
                    db.session.commit()
                    send_telegram_message(chat_id, f"✅ Subscription {sub_id} deleted successfully.")
                else:
                    send_telegram_message(chat_id, "❌ Subscription not found or doesn't belong to you.")
            except:
                send_telegram_message(chat_id, "❌ Invalid command. Use /delete <subscription_id>")
        
        elif text == '/deleteall':
            if user:
                subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                count = len(subscriptions)
                for sub in subscriptions:
                    db.session.delete(sub)
                db.session.commit()
                send_telegram_message(chat_id, f"✅ Deleted {count} subscription(s).")
            else:
                send_telegram_message(chat_id, "❌ No account found with your Telegram ID.")
        
        elif text == '/help':
            response = "🏠 PropertyNoti Bot Commands:\n\n"
            response += "/start - Show main menu\n"
            response += "/newsearch - Start a new one-time search\n"
            response += "/search - Search properties using your subscriptions\n"
            response += "/status - View your current subscriptions\n"
            response += "/delete <id> - Delete specific subscription\n"
            response += "/deleteall - Delete all subscriptions\n"
            response += "/help - Show this help message\n\n"
            response += "For subscriptions, sign up at the website first with your Telegram ID."
            send_telegram_message(chat_id, response)
        
        elif text == '/status':
            if user:
                subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                if subscriptions:
                    response = f"📋 Your Subscriptions:\n\n"
                    for i, sub in enumerate(subscriptions, 1):
                        response += f"<b>{i}. ID: {sub.id} - {sub.notification_frequency.upper()}</b>\n"
                        response += f"Price: ${sub.min_price or 'Any'} - ${sub.max_price or 'Any'}\n"
                        response += f"Zip: {sub.zip_codes or 'Not specified'}\n"
                        response += f"Type: {sub.property_type or 'Any'}\n"
                        response += f"Beds: {sub.bedrooms or 'Any'} | Baths: {sub.bathrooms or 'Any'}\n"
                        response += f"Last notified: {sub.last_notified.strftime('%Y-%m-%d %H:%M') if sub.last_notified else 'Never'}\n\n"
                    response += "Use /delete <id> to remove a subscription"
                else:
                    response = "❌ No subscriptions found.\n"
                    response += "Sign up at the website to create subscriptions."
                send_telegram_message(chat_id, response)
            else:
                response = "❌ No account found with your Telegram ID.\n"
                response += "Please sign up at the website and provide your Telegram ID."
                send_telegram_message(chat_id, response)
        
        elif text == '/search':
            if user:
                subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                if subscriptions:
                    send_telegram_message(chat_id, f"🔍 Searching for {len(subscriptions)} subscription(s)...")
                    for sub in subscriptions:
                        criteria = {
                            'min_price': sub.min_price,
                            'max_price': sub.max_price,
                            'zip_codes': sub.zip_codes,
                            'property_type': sub.property_type,
                            'bedrooms': sub.bedrooms,
                            'bathrooms': sub.bathrooms,
                            'min_sqft': sub.min_sqft
                        }
                        properties = search_properties(criteria)
                        
                        if properties:
                            send_telegram_message(chat_id, f"📊 Found {len(properties)} properties for {sub.notification_frequency} subscription")
                            send_telegram_notification(user, properties)
                        else:
                            send_telegram_message(chat_id, f"❌ No properties found for {sub.notification_frequency} subscription")
                else:
                    send_telegram_message(chat_id, "❌ No subscriptions found. Sign up at the website first.")
            else:
                response = "❌ No account found with your Telegram ID.\n"
                response += "Please sign up at the website and provide your Telegram ID."
                send_telegram_message(chat_id, response)
        
        else:
            response = "❓ Unknown command. Type /help for available commands."
            send_telegram_message(chat_id, response)
    except Exception as e:
        print(f"Error processing update: {e}")
        import traceback
        traceback.print_exc()

def telegram_polling():
    """Poll for Telegram updates"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("Telegram bot token not configured, polling disabled")
        return
    
    # Clear any existing webhook first with drop_pending_updates
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        requests.get(url, params={'drop_pending_updates': True}, timeout=5)
        print("Webhook cleared with drop_pending_updates")
        import time
        time.sleep(3)  # Wait for webhook to clear
    except Exception as e:
        print(f"Error clearing webhook: {e}")
    
    offset = 0
    print("Starting Telegram polling...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            params = {'offset': offset, 'timeout': 20}
            response = requests.get(url, params=params, timeout=25)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    updates = data.get('result', [])
                    if updates:
                        print(f"Received {len(updates)} update(s)")
                        for update in updates:
                            print(f"Processing update: {update.get('update_id')}")
                            with app.app_context():
                                process_telegram_update(update)
                            offset = update.get('update_id', 0) + 1
                    else:
                        print("No updates received (timeout)")
                else:
                    print(f"Telegram API error: {data.get('description')}")
                    import time
                    time.sleep(5)
            elif response.status_code == 409:
                # Conflict error - clear webhook aggressively
                print("Telegram polling conflict (409), clearing webhook...")
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
                    requests.get(url, params={'drop_pending_updates': True}, timeout=5)
                    import time
                    time.sleep(5)  # Longer wait after clearing
                except:
                    pass
                offset = 0
                import time
                time.sleep(15)
            else:
                print(f"Telegram polling error: {response.status_code}")
                import time
                time.sleep(5)
                
        except Exception as e:
            print(f"Telegram polling error: {e}")
            import traceback
            traceback.print_exc()
            import time
            time.sleep(10)

if __name__ == '__main__':
    # Start Telegram polling in background thread (only in main process)
    import os
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        polling_thread = threading.Thread(target=telegram_polling, daemon=True)
        polling_thread.start()
        print("Starting Flask server with Telegram polling enabled")
    else:
        print("Starting Flask server (reloader - polling already running)")
    
    app.run(debug=False, port=5000)
