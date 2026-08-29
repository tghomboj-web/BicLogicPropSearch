"""
Script to add sample property data to the database for testing
"""
from app import app, db, Property

sample_properties = [
    {
        "title": "Modern 3-Bedroom House in Brooklyn",
        "price": 450000,
        "address": "123 Oak Street, Brooklyn",
        "zip_code": "11201",
        "property_type": "house",
        "bedrooms": 3,
        "bathrooms": 2,
        "sqft": 1800,
        "url": None,
        "description": "Beautiful modern house with open floor plan, updated kitchen, and backyard."
    },
    {
        "title": "Cozy 2-Bedroom Apartment in Manhattan",
        "price": 325000,
        "address": "456 Park Avenue, Manhattan",
        "zip_code": "10022",
        "property_type": "apartment",
        "bedrooms": 2,
        "bathrooms": 1,
        "sqft": 900,
        "url": None,
        "description": "Renovated apartment in prime location with great city views."
    },
    {
        "title": "Luxury Condo with View in Manhattan",
        "price": 750000,
        "address": "789 Fifth Avenue, Manhattan",
        "zip_code": "10028",
        "property_type": "condo",
        "bedrooms": 2,
        "bathrooms": 2,
        "sqft": 1200,
        "url": None,
        "description": "High-end condo with stunning views, doorman, and amenities."
    },
    {
        "title": "Spacious 4-Bedroom Family Home in Queens",
        "price": 550000,
        "address": "321 Maple Drive, Queens",
        "zip_code": "11375",
        "property_type": "house",
        "bedrooms": 4,
        "bathrooms": 3,
        "sqft": 2500,
        "url": None,
        "description": "Perfect family home with large backyard, garage, and modern appliances."
    },
    {
        "title": "Studio Apartment in SoHo",
        "price": 275000,
        "address": "555 Broadway, SoHo",
        "zip_code": "10012",
        "property_type": "apartment",
        "bedrooms": 1,
        "bathrooms": 1,
        "sqft": 550,
        "url": None,
        "description": "Charming studio in the heart of SoHo, walking distance to everything."
    },
    {
        "title": "Victorian Townhouse in Carroll Gardens",
        "price": 890000,
        "address": "888 Carroll Gardens, Brooklyn",
        "zip_code": "11231",
        "property_type": "townhouse",
        "bedrooms": 3,
        "bathrooms": 2.5,
        "sqft": 2200,
        "url": None,
        "description": "Beautifully restored Victorian townhouse with original details and modern updates."
    },
    {
        "title": "Penthouse with Central Park View",
        "price": 1200000,
        "address": "100 Central Park West, Manhattan",
        "zip_code": "10024",
        "property_type": "condo",
        "bedrooms": 3,
        "bathrooms": 3,
        "sqft": 2800,
        "url": None,
        "description": "Stunning penthouse with private rooftop terrace and Central Park views."
    },
    {
        "title": "Suburban Family Home in Westchester",
        "price": 380000,
        "address": "222 Suburban Lane, Westchester",
        "zip_code": "10583",
        "property_type": "house",
        "bedrooms": 4,
        "bathrooms": 2,
        "sqft": 2100,
        "url": None,
        "description": "Great family home in excellent school district with large yard."
    },
    {
        "title": "Downtown Loft in Financial District",
        "price": 425000,
        "address": "333 Wall Street, Manhattan",
        "zip_code": "10005",
        "property_type": "apartment",
        "bedrooms": 2,
        "bathrooms": 1,
        "sqft": 1100,
        "url": None,
        "description": "Industrial-style loft with high ceilings, exposed brick, and modern finishes."
    },
    {
        "title": "Beach House in Rockaway Beach",
        "price": 650000,
        "address": "444 Ocean Drive, Rockaway Beach",
        "zip_code": "11693",
        "property_type": "house",
        "bedrooms": 3,
        "bathrooms": 2,
        "sqft": 1600,
        "url": None,
        "description": "Charming beach house with ocean views, deck, and direct beach access."
    }
]

if __name__ == "__main__":
    with app.app_context():
        # Clear existing properties
        Property.query.delete()
        
        # Add sample properties
        for prop_data in sample_properties:
            property = Property(**prop_data)
            db.session.add(property)
        
        db.session.commit()
        print(f"Added {len(sample_properties)} sample properties to the database!")
