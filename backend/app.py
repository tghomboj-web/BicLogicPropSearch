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
import logging
import sys

# Telegram polling state
telegram_conversation_state = {}  # Store conversation state for each user

load_dotenv()

# Configure logging for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

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

class TelegramConnectionCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    telegram_id = db.Column(db.String(50), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref=db.backref('connection_codes', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'user_id': self.user_id,
            'telegram_id': self.telegram_id,
            'expires_at': self.expires_at.isoformat(),
            'created_at': self.created_at.isoformat(),
            'used': self.used
        }
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
    logger.info("!!! SEARCH PROPERTIES FUNCTION CALLED !!!")
    searchapi_key = os.getenv('SEARCHAPI_API_KEY')
    
    logger.info(f"=== SEARCH PROPERTIES START ===")
    logger.info(f"Search criteria: {criteria}")
    logger.info(f"Searchapi.io API Key configured: {bool(searchapi_key)}")
    logger.info(f"API Key first 4 chars: {searchapi_key[:4] if searchapi_key else 'None'}")
    
    # Fall back to database search if API credentials not configured
    if not searchapi_key:
        logger.info("Searchapi.io API key not configured, using database search")
        return search_properties_database(criteria)
    
    # Build location query
    location = ""
    if criteria.get('zip_codes'):
        zip_list = [z.strip() for z in criteria['zip_codes'].split(',')]
        location = zip_list[0]  # Use first zip code for search
        logger.info(f"Searching in location: {location}")
    else:
        location = "United States"  # Default to broad search
        logger.info(f"Searching in location: {location} (default)")
    
    try:
        url = "https://www.searchapi.io/api/v1/search"
        params = {
            'engine': 'zillow',
            'api_key': searchapi_key,
            'q': location,
            'num': 20  # Get more results to filter locally
        }
        
        logger.info(f"Making API request to: {url}")
        logger.info(f"Parameters: engine=zillow, q={location}, num=20")
        
        response = requests.get(url, params=params, timeout=15)
        
        logger.info(f"API Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API Response data keys: {data.keys()}")
            logger.info(f"Number of properties from API: {len(data.get('properties', []))}")
            
            properties = []
            
            # Get requested zip codes for filtering
            requested_zips = []
            if criteria.get('zip_codes'):
                requested_zips = [z.strip() for z in criteria['zip_codes'].split(',')]
            
            for item in data.get('properties', []):
                item_zip = item.get('zipcode', '')
                logger.info(f"Processing property: {item.get('address')}, zip: {item_zip}")
                
                # Apply zip code filtering
                if requested_zips and item_zip not in requested_zips:
                    logger.info(f"  Skipping: zip {item_zip} not in requested {requested_zips}")
                    continue
                
                # Extract property data
                price = int(item.get('extracted_price', 0))
                beds = item.get('beds')
                baths = item.get('baths')
                sqft = item.get('sqft')
                home_type = item.get('home_type', '')
                
                logger.info(f"  Property details: price={price}, beds={beds}, baths={baths}, sqft={sqft}, type={home_type}")
                
                # Apply price filtering
                if criteria.get('min_price') and price > 0 and price < criteria['min_price']:
                    logger.info(f"  Skipping: price {price} < min_price {criteria['min_price']}")
                    continue
                if criteria.get('max_price') and price > 0 and price > criteria['max_price']:
                    logger.info(f"  Skipping: price {price} > max_price {criteria['max_price']}")
                    continue
                
                # Apply bedroom filtering
                if criteria.get('bedrooms') and beds and beds < criteria['bedrooms']:
                    logger.info(f"  Skipping: beds {beds} < min_bedrooms {criteria['bedrooms']}")
                    continue
                
                # Apply bathroom filtering
                if criteria.get('bathrooms') and baths and baths < criteria['bathrooms']:
                    logger.info(f"  Skipping: baths {baths} < min_bathrooms {criteria['bathrooms']}")
                    continue
                
                # Apply sqft filtering
                if criteria.get('min_sqft') and sqft and sqft < criteria['min_sqft']:
                    logger.info(f"  Skipping: sqft {sqft} < min_sqft {criteria['min_sqft']}")
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
                        logger.info(f"  Skipping: type {home_type} != expected {expected_type}")
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
                
                logger.info(f"  ✓ Property matched: {property_data['title']}")
                properties.append(property_data)
                
                if len(properties) >= 5:
                    break
            
            # Log results
            if requested_zips:
                logger.info(f"Found {len(properties)} properties in exact zip codes {requested_zips}")
                if len(properties) == 0:
                    logger.info(f"No properties found in exact zip codes {requested_zips}")
                    logger.info("Falling back to database search")
                    return search_properties_database(criteria)
            else:
                logger.info(f"Found {len(properties)} properties via Searchapi.io (no zip filter)")
            
            logger.info(f"=== SEARCH PROPERTIES END ===")
            return properties
        else:
            logger.info(f"Searchapi.io error: {response.status_code} - {response.text}")
            logger.info("Falling back to database search")
            return search_properties_database(criteria)
            
    except Exception as e:
        logger.info(f"Error searching Searchapi.io: {e}")
        import traceback
        traceback.print_exc()
        logger.info("Falling back to database search")
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
def send_email_notification(user, properties, criteria=None):
    """Send property notification email"""
    logger.info("=== EMAIL NOTIFICATION START ===")
    try:
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        logger.info(f"Email notification attempt:")
        logger.info(f"  To: {user.email}")
        logger.info(f"  Properties found: {len(properties) if properties else 0}")
        logger.info(f"  SMTP server: {smtp_server}")
        logger.info(f"  SMTP port: {smtp_port}")
        logger.info(f"  SMTP username: {smtp_username}")
        logger.info(f"  SMTP password configured: {bool(smtp_password)}")
        
        if not smtp_username or not smtp_password:
            logger.info("SMTP credentials not configured")
            return False
        
        msg = MIMEMultipart('alternative')
        
        if properties:
            msg['Subject'] = 'New Property Matches Found!'
        else:
            msg['Subject'] = 'No Properties Found - Search Results'
            
        # Use verified sender identity email for SendGrid
        from_email = os.getenv('FROM_EMAIL', smtp_username)
        msg['From'] = from_email
        msg['To'] = user.email
        
        # Build search criteria section
        criteria_section = ""
        if criteria:
            criteria_section = """
            <div style="background-color: #f0f4ff; border-left: 4px solid #667eea; padding: 15px; margin: 20px 0; border-radius: 5px;">
                <h3 style="margin: 0 0 10px 0; color: #333; font-size: 16px;">🔍 Your Search Criteria:</h3>
                <ul style="margin: 0; padding-left: 20px; color: #555; font-size: 14px;">
            """
            # Show all criteria, using "Any" for skipped fields
            criteria_section += f"<li><strong>Zip Codes:</strong> {criteria.get('zip_codes', 'Not specified')}</li>"
            
            min_price = criteria.get('min_price')
            max_price = criteria.get('max_price')
            if min_price or max_price:
                price_range = f"${min_price:,}" if min_price else "Any"
                price_range += f" - ${max_price:,}" if max_price else " - Any"
                criteria_section += f"<li><strong>Price Range:</strong> {price_range}</li>"
            else:
                criteria_section += f"<li><strong>Price Range:</strong> Any</li>"
            
            criteria_section += f"<li><strong>Bedrooms:</strong> {criteria.get('bedrooms', 'Any')} or more</li>"
            criteria_section += f"<li><strong>Bathrooms:</strong> {criteria.get('bathrooms', 'Any')} or more</li>"
            criteria_section += f"<li><strong>Property Type:</strong> {criteria.get('property_type', 'Any')}</li>"
            criteria_section += f"<li><strong>Min Sqft:</strong> {criteria.get('min_sqft', 'Any')}+</li>"
            criteria_section += "</ul></div>"
        
        if properties:
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background-color: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background-color: #ffffff;
                        border-radius: 10px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                    }}
                    .header h1 {{
                        margin: 0;
                        font-size: 28px;
                        font-weight: 600;
                    }}
                    .header p {{
                        margin: 10px 0 0 0;
                        font-size: 16px;
                        opacity: 0.9;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .property-card {{
                        background-color: #f9f9f9;
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;
                        padding: 20px;
                        margin: 15px 0;
                        transition: box-shadow 0.3s ease;
                    }}
                    .property-card:hover {{
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    }}
                    .property-title {{
                        color: #333;
                        font-size: 20px;
                        font-weight: 600;
                        margin: 0 0 15px 0;
                    }}
                    .property-price {{
                        color: #667eea;
                        font-size: 24px;
                        font-weight: 700;
                        margin: 10px 0;
                    }}
                    .property-details {{
                        color: #555;
                        font-size: 14px;
                        line-height: 1.6;
                    }}
                    .property-details strong {{
                        color: #333;
                    }}
                    .view-button {{
                        display: inline-block;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: 600;
                        margin-top: 15px;
                    }}
                    .footer {{
                        background-color: #f5f5f5;
                        padding: 20px;
                        text-align: center;
                        color: #666;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🏠 New Property Matches</h1>
                        <p>We found {len(properties)} new properties matching your criteria</p>
                    </div>
                    <div class="content">
                        {criteria_section}
            """
            
            for prop in properties:
                html_content += f"""
                        <div class="property-card">
                            <h3 class="property-title">{prop['title']}</h3>
                            <p class="property-price">${prop['price']:,}</p>
                            <div class="property-details">
                                <p><strong>📍 Address:</strong> {prop['address']}</p>
                                <p><strong>📮 Zip Code:</strong> {prop['zip_code']}</p>
                                <p><strong>🏠 Type:</strong> {prop['property_type'] or 'N/A'}</p>
                                <p><strong>🛏️ Bedrooms:</strong> {prop['bedrooms'] or 'N/A'}</p>
                                <p><strong>🚿 Bathrooms:</strong> {prop['bathrooms'] or 'N/A'}</p>
                                <p><strong>📐 Sqft:</strong> {prop['sqft'] or 'N/A'}</p>
                                <p><strong>📝 Description:</strong> {prop['description']}</p>
                            </div>
                            {f'<a href="{prop["url"]}" class="view-button">View Property →</a>' if prop['url'] else ''}
                        </div>
                """
            
            html_content += """
                    </div>
                    <div class="footer">
                        <p>Best regards,<br><strong>Property Notification Team</strong></p>
                        <p style="margin-top: 10px; font-size: 12px;">You're receiving this email because you subscribed to property alerts.</p>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            # No properties found email
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background-color: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background-color: #ffffff;
                        border-radius: 10px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                        color: white;
                        padding: 30px;
                        text-align: center;
                    }}
                    .header h1 {{
                        margin: 0;
                        font-size: 28px;
                        font-weight: 600;
                    }}
                    .header p {{
                        margin: 10px 0 0 0;
                        font-size: 16px;
                        opacity: 0.9;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .no-results {{
                        background-color: #fff3cd;
                        border: 1px solid #ffc107;
                        border-radius: 8px;
                        padding: 20px;
                        margin: 20px 0;
                        text-align: center;
                    }}
                    .no-results h2 {{
                        color: #856404;
                        margin: 0 0 10px 0;
                    }}
                    .no-results p {{
                        color: #856404;
                        margin: 0;
                    }}
                    .footer {{
                        background-color: #f5f5f5;
                        padding: 20px;
                        text-align: center;
                        color: #666;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔍 Search Results</h1>
                        <p>No properties found matching your criteria</p>
                    </div>
                    <div class="content">
                        {criteria_section}
                        <div class="no-results">
                            <h2>😕 No Properties Found</h2>
                            <p>We couldn't find any properties that match your search criteria. Try adjusting your filters or expanding your search area.</p>
                        </div>
                    </div>
                    <div class="footer">
                        <p>Best regards,<br><strong>Property Notification Team</strong></p>
                        <p style="margin-top: 10px; font-size: 12px;">You're receiving this email because you requested a property search.</p>
                    </div>
                </div>
            </body>
            </html>
            """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        # Try different connection methods for SendGrid
        try:
            # Try SSL on port 465 first (most reliable for SendGrid)
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
                server.login(smtp_username, smtp_password)
            else:
                # Try TLS on port 587 or 2525
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                server.starttls()
                server.login(smtp_username, smtp_password)
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {user.email}")
            return True
        except Exception as e:
            logger.info(f"SMTP connection failed: {e}")
            # Try fallback to different port
            logger.info("Trying fallback port 2525...")
            try:
                server = smtplib.SMTP(smtp_server, 2525, timeout=10)
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
                server.quit()
                logger.info(f"Email sent successfully to {user.email} via fallback port")
                return True
            except Exception as fallback_error:
                logger.info(f"Fallback also failed: {fallback_error}")
                raise
    except Exception as e:
        logger.info(f"Error sending email: {e}")
        import traceback
        traceback.print_exc()
        return False

# Telegram notification
def send_telegram_notification(user, properties):
    """Send Telegram notification with matching properties"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token or not user.telegram_id:
            logger.info("Telegram bot token or user telegram_id not configured")
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
            logger.info(f"Telegram message sent to {user.telegram_id}")
            return True
        else:
            logger.info(f"Telegram API error: {response.text}")
            return False
    except Exception as e:
        logger.info(f"Error sending Telegram notification: {e}")
        import traceback
        traceback.print_exc()
        return False

# Scheduled task to check for new properties
def check_and_notify_users():
    """Check all subscriptions and send notifications for matching properties"""
    logger.info("Running scheduled property check...")
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
                user = sub.user
                
                # Send email notification (always sent, with criteria)
                send_email_notification(user, properties, criteria)
                
                if properties:
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
        
        # Send notifications (email always sent, telegram only if properties found)
        send_email_notification(user, properties, criteria)
        if properties:
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
        
        logger.info(f"=== WEBSITE SUBSCRIPTION ===")
        logger.info(f"User: {user.email}")
        logger.info(f"Criteria: {criteria}")
        
        properties = search_properties(criteria)
        logger.info(f"Properties found: {len(properties)}")
        
        # Send immediate notification (email always sent, telegram only if properties found)
        logger.info("Calling send_email_notification...")
        try:
            send_email_notification(user, properties, criteria)
            logger.info("send_email_notification completed successfully")
        except Exception as e:
            logger.info(f"Email notification failed: {e}")
            import traceback
            traceback.print_exc()
        
        if properties:
            send_telegram_notification(user, properties)
            subscription.last_notified = datetime.now()
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
    logger.info(f"=== TEST NOTIFICATION ENDPOINT ===")
    user = User.query.get_or_404(user_id)
    logger.info(f"User: {user.email}")
    
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
    logger.info(f"Test notification for user {user_id} with criteria: {criteria}")
    properties = search_properties(criteria)
    logger.info(f"Found {len(properties)} properties")
    
    if properties:
        logger.info("Sending email notification...")
        email_sent = send_email_notification(user, properties)
        logger.info(f"Email sent result: {email_sent}")
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

@app.route('/api/test-email', methods=['POST'])
def test_email_endpoint():
    """Test email sending directly"""
    logger.info(f"=== TEST EMAIL ENDPOINT ===")
    data = request.json
    email = data.get('email', 'test@example.com')
    
    # Create a temporary user for testing
    from datetime import datetime
    test_user = User(
        email=email,
        phone=None,
        telegram_id=None
    )
    
    # Test with empty properties
    criteria = {'test': True}
    logger.info(f"Testing email to: {email}")
    result = send_email_notification(test_user, [], criteria)
    logger.info(f"Email test result: {result}")
    
    return jsonify({
        'success': True,
        'email_sent': result,
        'email': email
    })

@app.route('/api/check-api-config', methods=['GET'])
def check_api_config():
    """Check if Searchapi.io API key is configured"""
    searchapi_key = os.getenv('SEARCHAPI_API_KEY')
    google_api_key = os.getenv('GOOGLE_API_KEY')
    
    return jsonify({
        'searchapi_configured': bool(searchapi_key),
        'google_api_configured': bool(google_api_key),
        'searchapi_key_prefix': searchapi_key[:4] + '...' if searchapi_key else None,
        'google_key_prefix': google_api_key[:4] + '...' if google_api_key else None
    })

@app.route('/api/generate-telegram-code', methods=['POST'])
def generate_telegram_code():
    """Generate a unique code for Telegram account linking"""
    logger.info("=== GENERATE TELEGRAM CODE ENDPOINT ===")
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    
    try:
        # Find or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email)
            db.session.add(user)
            db.session.commit()
            logger.info(f"Created new user with email: {email}")
        else:
            logger.info(f"Found existing user: {email}, telegram_id: {user.telegram_id}")
        
        # Check if user already has Telegram linked
        if user.telegram_id:
            logger.info(f"User {email} already has Telegram ID linked: {user.telegram_id}")
            return jsonify({
                'success': True,
                'already_connected': True,
                'message': 'Your Telegram account is already connected'
            })
        
        # Delete any existing unused codes for this user
        TelegramConnectionCode.query.filter_by(user_id=user.id, used=False).delete()
        
        # Generate a unique 6-character code
        import random
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not TelegramConnectionCode.query.filter_by(code=code).first():
                break
        
        # Create connection code that expires in 5 minutes
        from datetime import timedelta
        expires_at = datetime.now() + timedelta(minutes=5)
        connection_code = TelegramConnectionCode(
            code=code,
            user_id=user.id,
            expires_at=expires_at
        )
        db.session.add(connection_code)
        db.session.commit()
        
        logger.info(f"Generated code {code} for user {email}, expires at {expires_at}")
        
        return jsonify({
            'success': True,
            'code': code,
            'expires_at': expires_at.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error generating Telegram code: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/quick-search', methods=['POST'])
def quick_search():
    """One-time property search"""
    logger.info("!!! QUICK SEARCH ENDPOINT CALLED !!!")
    logger.info(f"=== QUICK SEARCH START ===")
    data = request.json
    logger.info(f"Search request data: {data}")
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
        
        logger.info(f"User: {user.email}")
        
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
        
        logger.info(f"Search criteria: {criteria}")
        properties = search_properties(criteria)
        logger.info(f"Properties found: {len(properties)}")
        
        # Send notifications if properties found
        if properties:
            logger.info("Sending notifications...")
            send_email_notification(user, properties)
            send_telegram_notification(user, properties)
        else:
            logger.info("No properties found, skipping notifications")
        
        return jsonify({
            'success': True,
            'properties_found': len(properties),
            'properties': properties
        })
    except Exception as e:
        logger.info(f"Error in quick search: {e}")
        import traceback
        traceback.print_exc()
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
        'version': '1.0.1',
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
        response += "/help - Show this help message\n"
        response += "/connect <code> - Connect your account using a code from the website\n\n"
        response += "💡 Use the button menu below for easier navigation."
        send_telegram_message(chat_id, response, get_main_menu_keyboard())
    
    elif text == '/help':
        response = "🏠 PropertyNoti Bot Commands:\n\n"
        response += "/search - Search for properties matching your criteria\n"
        response += "/status - View your current search criteria\n"
        response += "/help - Show this help message\n\n"
        response += "Note: You need to sign up at the website first with your Telegram ID."
        send_telegram_message(chat_id, response, get_main_menu_keyboard())
    
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
            send_telegram_message(chat_id, response, get_main_menu_keyboard())
        else:
            response = "❌ No account found with your Telegram ID.\n"
            response += "Please sign up at the website and provide your Telegram ID."
            send_telegram_message(chat_id, response, get_main_menu_keyboard())
    
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
                send_telegram_message(chat_id, "✅ Properties found! Check your email for details.", get_main_menu_keyboard())
            else:
                send_telegram_message(chat_id, "❌ No properties found matching your criteria.", get_main_menu_keyboard())
        else:
            response = "❌ No account found with your Telegram ID.\n"
            response += "Please sign up at the website and provide your Telegram ID."
            send_telegram_message(chat_id, response, get_main_menu_keyboard())
    
    else:
        response = "❓ Unknown command. Type /help for available commands."
        send_telegram_message(chat_id, response, get_main_menu_keyboard())
    
    return jsonify({'ok': True})

def get_main_menu_keyboard():
    """Return the main menu keyboard with all options"""
    return {
        'inline_keyboard': [
            [
                {'text': '🔍 One-time Search', 'callback_data': 'search_now'},
                {'text': '📧 Subscribe for Alerts', 'callback_data': 'subscribe'}
            ],
            [
                {'text': '📋 View Subscriptions', 'callback_data': 'status'},
                {'text': '🗑️ Delete Subscriptions', 'callback_data': 'delete'}
            ],
            [
                {'text': '🔗 Connect Account', 'callback_data': 'connect_account'}
            ]
        ]
    }

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
        
        response = requests.post(url, data=data)
        
        if response.status_code != 200:
            logger.info(f"Telegram API error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.info(f"Error sending Telegram message: {e}")

def process_telegram_update(update):
    """Process a single Telegram update"""
    try:
        # Handle callback queries from inline keyboards
        callback_query = update.get('callback_query')
        if callback_query:
            chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
            callback_data = callback_query.get('data')
            user = User.query.filter_by(telegram_id=str(chat_id)).first()
            
            if callback_data == 'search_now':
                # Start conversational search flow
                telegram_conversation_state[str(chat_id)] = {
                    'step': 'email',
                    'criteria': {}
                }
                response = "🔍 <b>New Property Search</b>\n\n"
                response += "Let's set up your search criteria step by step.\n\n"
                response += "First, what's your email address for receiving results?"
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
                    response = "What property type are you looking for?"
                    keyboard = {
                        'inline_keyboard': [
                            [
                                {'text': '🏠 House', 'callback_data': 'type_house'},
                                {'text': '🏢 Apartment', 'callback_data': 'type_apartment'}
                            ],
                            [
                                {'text': '🏙️ Condo', 'callback_data': 'type_condo'},
                                {'text': '🏘️ Townhouse', 'callback_data': 'type_townhouse'}
                            ],
                            [
                                {'text': '🌳 Land', 'callback_data': 'type_land'},
                                {'text': '⏭️ Skip', 'callback_data': 'skip_property_type'}
                            ]
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
            
            elif callback_data in ['type_house', 'type_apartment', 'type_condo', 'type_townhouse', 'type_land']:
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    property_type = callback_data.replace('type_', '')
                    state['criteria']['property_type'] = property_type
                    state['step'] = 'min_sqft'
                    response = f"Selected: {property_type.capitalize()}\n\nWhat's the minimum square footage?"
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
                        send_telegram_message(chat_id, f"✅ Found {len(properties)} properties matching your criteria!", get_main_menu_keyboard())
                    else:
                        send_telegram_message(chat_id, "❌ No properties found matching your criteria.", get_main_menu_keyboard())
            
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
                    response = "What property type are you looking for?"
                    keyboard = {
                        'inline_keyboard': [
                            [
                                {'text': '🏠 House', 'callback_data': 'sub_type_house'},
                                {'text': '🏢 Apartment', 'callback_data': 'sub_type_apartment'}
                            ],
                            [
                                {'text': '🏙️ Condo', 'callback_data': 'sub_type_condo'},
                                {'text': '🏘️ Townhouse', 'callback_data': 'sub_type_townhouse'}
                            ],
                            [
                                {'text': '🌳 Land', 'callback_data': 'sub_type_land'},
                                {'text': '⏭️ Skip', 'callback_data': 'skip_sub_property_type'}
                            ]
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
            
            elif callback_data in ['sub_type_house', 'sub_type_apartment', 'sub_type_condo', 'sub_type_townhouse', 'sub_type_land']:
                state = telegram_conversation_state.get(str(chat_id))
                if state:
                    property_type = callback_data.replace('sub_type_', '')
                    state['criteria']['property_type'] = property_type
                    state['step'] = 'sub_min_sqft'
                    response = f"Selected: {property_type.capitalize()}\n\nWhat's the minimum square footage?"
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
                logger.info(f"Frequency button clicked: {callback_data} for chat_id: {chat_id}")
                
                state = telegram_conversation_state.get(str(chat_id))
                logger.info(f"Conversation state: {state}")
                
                if state:
                    try:
                        frequency = callback_data.replace('freq_', '')
                        state['criteria']['notification_frequency'] = frequency
                        logger.info(f"Creating subscription with frequency: {frequency}")
                        # Execute subscription creation
                        del telegram_conversation_state[str(chat_id)]
                        
                        # Find or create user with email from conversation
                        email = state['criteria'].get('email')
                        user = User.query.filter_by(email=email).first() if email else None
                        if not user:
                            user = User(
                                email=email or f"telegram_{chat_id}@temp.com",
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
                        logger.info(f"Subscription created successfully: {subscription.id}")
                        
                        # Send immediate response to user first
                        send_telegram_message(chat_id, f"✅ Subscription created successfully!\n\nWe'll send you {frequency} notifications at {email}.", get_main_menu_keyboard())
                        
                        # Answer the callback query immediately
                        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                        requests.post(url, json={'callback_query_id': callback_query.get('id')}, timeout=5)
                        
                        # Send email notification in background thread to avoid blocking
                        def send_background_email():
                            try:
                                with app.app_context():
                                    criteria = {
                                        'min_price': state['criteria'].get('min_price'),
                                        'max_price': state['criteria'].get('max_price'),
                                        'zip_codes': state['criteria'].get('zip_codes'),
                                        'property_type': state['criteria'].get('property_type'),
                                        'bedrooms': state['criteria'].get('bedrooms'),
                                        'bathrooms': state['criteria'].get('bathrooms'),
                                        'min_sqft': state['criteria'].get('min_sqft')
                                    }
                                    properties = search_properties(criteria)
                                    send_email_notification(user, properties, criteria)
                                    
                                    if properties:
                                        send_telegram_notification(user, properties)
                            except Exception as e:
                                logger.info(f"Error in background email sending: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        import threading
                        email_thread = threading.Thread(target=send_background_email)
                        email_thread.start()
                        
                    except Exception as e:
                        logger.info(f"Error creating subscription: {e}")
                        import traceback
                        traceback.print_exc()
                        send_telegram_message(chat_id, f"❌ Error creating subscription: {str(e)}", get_main_menu_keyboard())
                else:
                    logger.info(f"No conversation state found for chat_id: {chat_id}")
                    send_telegram_message(chat_id, "❌ Session expired. Please start subscription again with /start", get_main_menu_keyboard())
                    
                    # Answer the callback query
                    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                    requests.post(url, json={'callback_query_id': callback_query.get('id')}, timeout=5)
            elif callback_data == 'subscribe':
                # Start conversational subscription flow
                telegram_conversation_state[str(chat_id)] = {
                    'step': 'sub_email',
                    'criteria': {}
                }
                response = "📧 <b>Subscribe for Alerts</b>\n\n"
                response += "Let's set up your subscription step by step.\n\n"
                response += "First, what's your email address for receiving notifications?"
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
                        
                        # Add inline buttons for each subscription
                        keyboard = []
                        for sub in subscriptions:
                            keyboard.append([{'text': f'🗑️ Delete {sub.id} ({sub.notification_frequency})', 'callback_data': f'delete_sub_{sub.id}'}])
                        keyboard.append([{'text': '🗑️ Delete All', 'callback_data': 'delete_all'}])
                        keyboard.append([{'text': '🔙 Back to Menu', 'callback_data': 'back_to_menu'}])
                        
                        send_telegram_message(chat_id, response, {'inline_keyboard': keyboard})
                    else:
                        response = "❌ No subscriptions found.\n"
                        response += "Sign up at the website to create subscriptions."
                        send_telegram_message(chat_id, response, get_main_menu_keyboard())
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.", get_main_menu_keyboard())
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
                        send_telegram_message(chat_id, response, get_main_menu_keyboard())
                    else:
                        send_telegram_message(chat_id, "❌ No subscriptions to delete.", get_main_menu_keyboard())
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.", get_main_menu_keyboard())

            elif callback_data == 'connect_account':
                response = "🔗 <b>Connect Your Account</b>\n\n"
                response += "To connect your Telegram account to the website:\n\n"
                response += "1. Go to the website: https://tghomboj-web.github.io/BicLogicPropSearch/\n"
                response += "2. Enter your email address\n"
                response += "3. Click 'Connect Telegram' button\n"
                response += "4. Copy the 6-digit code shown\n"
                response += "5. Send the code here (just the code, no command needed)\n\n"
                response += "Example: ABC123"
                send_telegram_message(chat_id, response)
            
            elif callback_data.startswith('delete_sub_'):
                # Handle delete specific subscription
                if user:
                    try:
                        sub_id = int(callback_data.replace('delete_sub_', ''))
                        subscription = SearchSubscription.query.get(sub_id)
                        if subscription and subscription.user_id == user.id:
                            db.session.delete(subscription)
                            db.session.commit()
                            send_telegram_message(chat_id, f"✅ Subscription {sub_id} deleted successfully.", get_main_menu_keyboard())
                        else:
                            send_telegram_message(chat_id, "❌ Subscription not found or doesn't belong to you.", get_main_menu_keyboard())
                    except Exception as e:
                        send_telegram_message(chat_id, f"❌ Error deleting subscription: {str(e)}", get_main_menu_keyboard())
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.", get_main_menu_keyboard())
            
            elif callback_data == 'delete_all':
                # Handle delete all subscriptions
                if user:
                    try:
                        subscriptions = SearchSubscription.query.filter_by(user_id=user.id).all()
                        count = len(subscriptions)
                        for sub in subscriptions:
                            db.session.delete(sub)
                        db.session.commit()
                        send_telegram_message(chat_id, f"✅ Deleted {count} subscription(s).", get_main_menu_keyboard())
                    except Exception as e:
                        send_telegram_message(chat_id, f"❌ Error deleting subscriptions: {str(e)}", get_main_menu_keyboard())
                else:
                    send_telegram_message(chat_id, "❌ No account found. Please sign up at the website first.", get_main_menu_keyboard())
            
            elif callback_data == 'back_to_menu':
                send_telegram_message(chat_id, "🏠 Welcome to PropertyNoti Bot!\n\nWhat would you like to do?", get_main_menu_keyboard())
            
            # Answer the callback query immediately for faster response
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
            requests.post(url, json={'callback_query_id': callback_query.get('id')}, timeout=5)
            return
        
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        
        if not chat_id or not text:
            return
        
        # Find user by telegram_id
        user = User.query.filter_by(telegram_id=str(chat_id)).first()
        
        # Handle commands
        if text == '/start':
            response = "🏠 Welcome to PropertyNoti Bot!\n\n"
            response += "What would you like to do?\n\n"
            response += "💡 <b>New here?</b> Start by connecting your account using the 'Connect Account' button below."
            send_telegram_message(chat_id, response, get_main_menu_keyboard())
        
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
            
            # Subscription flow
            if step.startswith('sub_'):
                if step == 'sub_email':
                    email = text.strip()
                    # Basic email validation
                    if '@' not in email or '.' not in email:
                        send_telegram_message(chat_id, "❌ Invalid email address. Please enter a valid email.")
                        return
                    criteria['email'] = email
                    state['step'] = 'sub_zip_codes'
                    response = "Great! What zip code(s) would you like to subscribe to?\n"
                    response += "You can enter multiple zip codes separated by commas."
                    send_telegram_message(chat_id, response)
                
                elif step == 'sub_zip_codes':
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
                    response = "What property type are you looking for?"
                    keyboard = {
                        'inline_keyboard': [
                            [
                                {'text': '🏠 House', 'callback_data': 'sub_type_house'},
                                {'text': '🏢 Apartment', 'callback_data': 'sub_type_apartment'}
                            ],
                            [
                                {'text': '🏙️ Condo', 'callback_data': 'sub_type_condo'},
                                {'text': '🏘️ Townhouse', 'callback_data': 'sub_type_townhouse'}
                            ],
                            [
                                {'text': '🌳 Land', 'callback_data': 'sub_type_land'},
                                {'text': '⏭️ Skip', 'callback_data': 'skip_sub_property_type'}
                            ]
                        ]
                    }
                    send_telegram_message(chat_id, response, keyboard)
                
                elif step == 'sub_property_type':
                    # Property type is now handled via buttons, ignore text input
                    send_telegram_message(chat_id, "Please use the buttons above to select a property type or skip.")
                    return
                
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
            if step == 'email':
                email = text.strip()
                # Basic email validation
                if '@' not in email or '.' not in email:
                    send_telegram_message(chat_id, "❌ Invalid email address. Please enter a valid email.")
                    return
                criteria['email'] = email
                state['step'] = 'zip_codes'
                response = "Great! What zip code(s) would you like to search in?\n"
                response += "You can enter multiple zip codes separated by commas."
                send_telegram_message(chat_id, response)
            
            elif step == 'zip_codes':
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
                response = "What property type are you looking for?"
                keyboard = {
                    'inline_keyboard': [
                        [
                            {'text': '🏠 House', 'callback_data': 'type_house'},
                            {'text': '🏢 Apartment', 'callback_data': 'type_apartment'}
                        ],
                        [
                            {'text': '🏙️ Condo', 'callback_data': 'type_condo'},
                            {'text': '🏘️ Townhouse', 'callback_data': 'type_townhouse'}
                        ],
                        [
                            {'text': '🌳 Land', 'callback_data': 'type_land'},
                            {'text': '⏭️ Skip', 'callback_data': 'skip_property_type'}
                        ]
                    ]
                }
                send_telegram_message(chat_id, response, keyboard)
            
            elif step == 'property_type':
                # Property type is now handled via buttons, ignore text input
                send_telegram_message(chat_id, "Please use the buttons above to select a property type or skip.")
                return
            
            elif step == 'min_sqft':
                if text.lower() != 'skip':
                    try:
                        criteria['min_sqft'] = int(text.strip())
                    except:
                        send_telegram_message(chat_id, "❌ Invalid number. Please enter a number or use the skip button.")
                        return
                
                # Search is complete, execute it
                del telegram_conversation_state[str(chat_id)]
                
                # Find or create user with email from conversation
                email = criteria.get('email')
                user = User.query.filter_by(email=email).first() if email else None
                if not user:
                    user = User(
                        email=email or f"telegram_{chat_id}@temp.com",
                        telegram_id=str(chat_id)
                    )
                    db.session.add(user)
                    db.session.commit()
                
                send_telegram_message(chat_id, "🔍 Searching for properties...")
                properties = search_properties(criteria)
                
                # Send email notification (always sent, with criteria)
                send_email_notification(user, properties, criteria)
                
                if properties:
                    send_telegram_notification(user, properties)
                    send_telegram_message(chat_id, f"✅ Found {len(properties)} properties matching your criteria! Results sent to {email}")
                else:
                    send_telegram_message(chat_id, f"❌ No properties found matching your criteria. Results sent to {email}")
            
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
            response += "/connect <code> - Connect your account (or just send the code)\n"
            response += "/help - Show this help message\n\n"
            response += "For subscriptions, sign up at the website first."
            send_telegram_message(chat_id, response)
        
        elif text.startswith('/connect '):
            # Handle Telegram account connection via code
            code = text.split()[1].strip().upper()
            logger.info(f"=== CONNECT COMMAND ===")
            logger.info(f"User {chat_id} attempting to connect with code: {code}")

            # Find the connection code
            connection_code = TelegramConnectionCode.query.filter_by(code=code, used=False).first()

            if not connection_code:
                send_telegram_message(chat_id, "❌ Invalid or expired code. Please generate a new code from the website.")
                return

            # Check if code is expired
            if connection_code.expires_at < datetime.now():
                send_telegram_message(chat_id, "❌ Code has expired. Please generate a new code from the website.")
                return

            # Get the user associated with this code
            user = User.query.get(connection_code.user_id)
            if not user:
                send_telegram_message(chat_id, "❌ User not found. Please try again.")
                return

            # Update user's Telegram ID
            user.telegram_id = str(chat_id)
            connection_code.telegram_id = str(chat_id)
            connection_code.used = True
            db.session.commit()

            logger.info(f"Successfully connected user {user.email} to Telegram ID {chat_id}")

            send_telegram_message(chat_id, f"✅ Successfully connected!\n\nYour Telegram account is now linked to {user.email}.\n\nYou can now receive property notifications via Telegram.", get_main_menu_keyboard())

        # Handle bare code input (without /connect prefix)
        elif len(text) == 6 and text.isalnum():
            # This might be a connection code without the /connect prefix
            code = text.strip().upper()
            logger.info(f"=== BARE CODE INPUT ===")
            logger.info(f"User {chat_id} sent potential code: {code}")

            # Find the connection code
            connection_code = TelegramConnectionCode.query.filter_by(code=code, used=False).first()

            if connection_code:
                # Treat it as a connection code
                # Check if code is expired
                if connection_code.expires_at < datetime.now():
                    send_telegram_message(chat_id, "❌ Code has expired. Please generate a new code from the website.")
                    return

                # Get the user associated with this code
                user = User.query.get(connection_code.user_id)
                if not user:
                    send_telegram_message(chat_id, "❌ User not found. Please try again.")
                    return

                # Update user's Telegram ID
                user.telegram_id = str(chat_id)
                connection_code.telegram_id = str(chat_id)
                connection_code.used = True
                db.session.commit()

                logger.info(f"Successfully connected user {user.email} to Telegram ID {chat_id} via bare code")

                send_telegram_message(chat_id, f"✅ Successfully connected!\n\nYour Telegram account is now linked to {user.email}.\n\nYou can now receive property notifications via Telegram.", get_main_menu_keyboard())
            else:
                # Not a valid code, treat as unknown command
                send_telegram_message(chat_id, "❓ Unknown command. Type /help for available commands.", get_main_menu_keyboard())
        
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
        logger.info(f"Error processing update: {e}")
        import traceback
        traceback.print_exc()

def telegram_polling():
    """Poll for Telegram updates"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.info("Telegram bot token not configured, polling disabled")
        return
    
    # Clear any existing webhook first with drop_pending_updates
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        requests.get(url, params={'drop_pending_updates': True}, timeout=5)
        logger.info("Webhook cleared with drop_pending_updates")
        import time
        time.sleep(3)  # Wait for webhook to clear
    except Exception as e:
        logger.info(f"Error clearing webhook: {e}")
    
    offset = 0
    logger.info("Starting Telegram polling...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            params = {'offset': offset, 'timeout': 10}  # Reduced timeout for faster response
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    updates = data.get('result', [])
                    if updates:
                        logger.info(f"Received {len(updates)} update(s)")
                        for update in updates:
                            logger.info(f"Processing update: {update.get('update_id')}")
                            with app.app_context():
                                process_telegram_update(update)
                            offset = update.get('update_id', 0) + 1
                else:
                    logger.info(f"Telegram API error: {data.get('description')}")
                    import time
                    time.sleep(2)
            elif response.status_code == 409:
                # Conflict error - clear webhook aggressively
                logger.info("Telegram polling conflict (409), clearing webhook...")
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
                    requests.get(url, params={'drop_pending_updates': True}, timeout=5)
                    import time
                    time.sleep(3)
                except:
                    pass
                offset = 0
                import time
                time.sleep(10)
            else:
                logger.info(f"Telegram polling error: {response.status_code}")
                import time
                time.sleep(2)
        
        except Exception as e:
            logger.info(f"Telegram polling error: {e}")
            import traceback
            traceback.print_exc()
            import time
            time.sleep(5)

if __name__ == '__main__':
    # Start Telegram polling in background thread (only in main process and if enabled)
    import os
    enable_telegram_polling = os.environ.get('ENABLE_TELEGRAM_POLLING', 'true').lower() == 'true'
    
    if enable_telegram_polling and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        polling_thread = threading.Thread(target=telegram_polling, daemon=True)
        polling_thread.start()
        logger.info("Starting Flask server with Telegram polling enabled")
    else:
        logger.info("Starting Flask server (polling disabled or already running)")
    
    # Use PORT environment variable for Render deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
