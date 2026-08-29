"""
Telegram Bot for user registration
This bot allows users to register for property notifications via Telegram
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv('API_URL', 'http://localhost:5000/api')

# User registration state storage (in production, use a database)
user_registrations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    keyboard = [
        [InlineKeyboardButton("Register for Notifications", callback_data="register")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏠 Welcome to Property Notification Bot!\n\n"
        "I can help you sign up for real estate property notifications. "
        "You'll receive daily updates about properties that match your criteria.\n\n"
        "Click the button below to get started:",
        reply_markup=reply_markup
    )

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle registration button click"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user_registrations[user_id] = {
        'telegram_id': user_id,
        'step': 'email'
    }
    
    await query.edit_message_text(
        "Let's set up your property notifications!\n\n"
        "Step 1/8: Please enter your email address:"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages during registration"""
    user_id = str(update.message.from_user.id)
    
    if user_id not in user_registrations:
        await update.message.reply_text(
            "Please click /start to begin registration."
        )
        return
    
    registration = user_registrations[user_id]
    step = registration['step']
    
    if step == 'email':
        registration['email'] = update.message.text
        registration['step'] = 'phone'
        await update.message.reply_text(
            "Step 2/8: Please enter your phone number (or type 'skip' to skip):"
        )
    
    elif step == 'phone':
        phone = update.message.text
        registration['phone'] = phone if phone.lower() != 'skip' else None
        registration['step'] = 'min_price'
        await update.message.reply_text(
            "Step 3/8: Enter your minimum price (or type 'skip'):"
        )
    
    elif step == 'min_price':
        min_price = update.message.text
        registration['min_price'] = int(min_price) if min_price.lower() != 'skip' else None
        registration['step'] = 'max_price'
        await update.message.reply_text(
            "Step 4/8: Enter your maximum price (or type 'skip'):"
        )
    
    elif step == 'max_price':
        max_price = update.message.text
        registration['max_price'] = int(max_price) if max_price.lower() != 'skip' else None
        registration['step'] = 'zip_codes'
        await update.message.reply_text(
            "Step 5/8: Enter zip codes (comma-separated, or type 'skip'):"
        )
    
    elif step == 'zip_codes':
        zip_codes = update.message.text
        registration['zip_codes'] = zip_codes if zip_codes.lower() != 'skip' else None
        registration['step'] = 'property_type'
        
        keyboard = [
            [InlineKeyboardButton("House", callback_data="type_house")],
            [InlineKeyboardButton("Apartment", callback_data="type_apartment")],
            [InlineKeyboardButton("Condo", callback_data="type_condo")],
            [InlineKeyboardButton("Townhouse", callback_data="type_townhouse")],
            [InlineKeyboardButton("Any", callback_data="type_any")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Step 6/8: Select property type:",
            reply_markup=reply_markup
        )
    
    elif step == 'property_type':
        # This is handled by callback
        pass
    
    elif step == 'bedrooms':
        bedrooms = update.message.text
        registration['bedrooms'] = int(bedrooms) if bedrooms.lower() != 'skip' else None
        registration['step'] = 'bathrooms'
        await update.message.reply_text(
            "Step 8/8: Enter minimum bathrooms (or type 'skip'):"
        )
    
    elif step == 'bathrooms':
        bathrooms = update.message.text
        registration['bathrooms'] = float(bathrooms) if bathrooms.lower() != 'skip' else None
        registration['step'] = 'complete'
        
        # Submit registration
        await submit_registration(update, registration)

async def property_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle property type selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    if user_id not in user_registrations:
        return
    
    registration = user_registrations[user_id]
    type_choice = query.data.replace('type_', '')
    registration['property_type'] = type_choice if type_choice != 'any' else None
    registration['step'] = 'bedrooms'
    
    await query.edit_message_text(
        "Step 7/8: Enter minimum bedrooms (or type 'skip'):"
    )

async def submit_registration(update: Update, registration: dict):
    """Submit registration to API"""
    try:
        response = requests.post(f"{API_URL}/signup", json=registration)
        
        if response.status_code == 201:
            # Clean up registration data
            user_id = str(update.message.from_user.id)
            del user_registrations[user_id]
            
            await update.message.reply_text(
                "✅ Registration successful!\n\n"
                "You will now receive daily notifications about properties "
                "that match your criteria via Telegram and email.\n\n"
                "Use /help to see available commands."
            )
        else:
            await update.message.reply_text(
                f"❌ Registration failed: {response.json().get('error', 'Unknown error')}"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error connecting to server: {str(e)}"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🏠 Property Notification Bot Commands:

/start - Begin registration or see main menu
/help - Show this help message
/cancel - Cancel current registration

After registration, you'll receive daily property notifications.
"""
    await update.message.reply_text(help_text)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command"""
    user_id = str(update.message.from_user.id)
    
    if user_id in user_registrations:
        del user_registrations[user_id]
        await update.message.reply_text("Registration cancelled.")
    else:
        await update.message.reply_text("No registration in progress.")

def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file")
        return
    
    application = Application.builder().token(token).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(register_callback, pattern="^register$"))
    application.add_handler(CallbackQueryHandler(property_type_callback, pattern="^type_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Telegram bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
