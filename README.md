# Real Estate Property Notification Service

A full-stack web application that allows users to sign up for real estate property notifications via email and Telegram.

## Features

- **User Registration**: Sign up via website with contact information (email, phone, Telegram ID)
- **Search Criteria**: Specify property preferences (price range, zip codes, property type, bedrooms, bathrooms, square footage)
- **Property Search**: Automated search for properties matching user criteria
- **Email Notifications**: Receive daily email notifications with up to 5 matching properties
- **Telegram Notifications**: Receive Telegram messages with property matches
- **Scheduled Tasks**: Daily automated property search and notification system

## Tech Stack

### Backend
- Flask (Python web framework)
- SQLAlchemy (ORM)
- APScheduler (Scheduled tasks)
- python-telegram-bot (Telegram integration)
- SMTP (Email notifications)

### Frontend
- React
- Axios (HTTP client)

## Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js 16+
- npm

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

6. Configure your `.env` file with your SMTP and Telegram credentials:
```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

### Running the Application

1. Start the backend server (from backend directory):
```bash
python app.py
```
The backend will run on `http://localhost:5000`

2. Start the frontend development server (from frontend directory):
```bash
npm start
```
The frontend will run on `http://localhost:3000`

## API Endpoints

### User Registration
- `POST /api/signup` - Register a new user with search criteria
- `GET /api/users` - Get all registered users

### Properties
- `GET /api/properties` - Get all properties in database
- `POST /api/properties` - Add a new property (for testing)
- `POST /api/search` - Search properties based on criteria

### Notifications
- `POST /api/test-notification/<user_id>` - Send test notification to a user

## Adding Sample Data

To add sample properties for testing, you can use the API:

```bash
curl -X POST http://localhost:5000/api/properties \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Beautiful 3-Bedroom House",
    "price": 450000,
    "address": "123 Main Street",
    "zip_code": "10001",
    "property_type": "house",
    "bedrooms": 3,
    "bathrooms": 2,
    "sqft": 2000,
    "url": "https://example.com/property/123"
  }'
```

Or run the sample data script:
```bash
python add_sample_data.py
```

## Telegram Bot Setup

### Creating a Telegram Bot

1. Open Telegram and search for @BotFather
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token provided by BotFather
5. Add the token to your `.env` file as `TELEGRAM_BOT_TOKEN`

### Getting Your Telegram ID

1. Search for @userinfobot in Telegram
2. Start the bot and it will send you your user ID
3. Use this ID when registering on the website

## Email Configuration

### Gmail Setup

1. Go to your Google Account settings
2. Enable 2-factor authentication
3. Generate an App Password:
   - Go to Security > App passwords
   - Create a new app password for "Mail"
   - Copy the generated password
4. Use the app password in your `.env` file as `SMTP_PASSWORD`

## Scheduled Tasks

The application runs a scheduled task every 24 hours to:
1. Check all registered users
2. Search for properties matching their criteria
3. Send email and Telegram notifications

You can modify the schedule in `app.py` by changing the `trigger="interval"` parameter.

## Future Enhancements

- [ ] Telegram bot for user registration
- [ ] Real-time property API integration (Zillow, Redfin, etc.)
- [ ] User dashboard to manage preferences
- [ ] Property bookmarking
- [ ] Notification frequency customization
- [ ] Price drop alerts
- [ ] Property image display in notifications

## License

MIT License
