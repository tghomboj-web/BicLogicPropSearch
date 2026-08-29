import os
from dotenv import load_dotenv
import requests

load_dotenv()

searchapi_key = os.getenv('SEARCHAPI_API_KEY')

print("Testing 28202 - WITH vs WITHOUT filters...")
print(f"API Key: {searchapi_key}")

if not searchapi_key or searchapi_key == "your-searchapi-api-key-here":
    print("❌ Searchapi.io API key not configured")
    exit(1)

zip_code = '28202'

# Test WITHOUT filters
print("\n--- TEST 1: Without filters ---")
url = "https://www.searchapi.io/api/v1/search"
params = {
    'engine': 'zillow',
    'api_key': searchapi_key,
    'q': zip_code,
    'num': 5
}

response = requests.get(url, params=params)
print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    properties = data.get('properties', [])
    print(f"Total properties: {len(properties)}")
    
    zip_counts = {}
    for prop in properties:
        zip_result = prop.get('zipcode', 'unknown')
        zip_counts[zip_result] = zip_counts.get(zip_result, 0) + 1
    
    print(f"Zip code distribution: {zip_counts}")
    if properties:
        print(f"First property: {properties[0].get('address')} - {properties[0].get('city', 'N/A')}, {properties[0].get('state', 'N/A')}")

# Test WITH filters
print("\n--- TEST 2: With filters ---")
params_with_filters = {
    'engine': 'zillow',
    'api_key': searchapi_key,
    'q': zip_code,
    'num': 5,
    'price_min': 100000,
    'price_max': 600000,
    'beds_min': 1,
    'baths_min': 1
}

response2 = requests.get(url, params=params_with_filters)
print(f"Status Code: {response2.status_code}")

if response2.status_code == 200:
    data = response2.json()
    properties = data.get('properties', [])
    print(f"Total properties: {len(properties)}")
    
    zip_counts = {}
    for prop in properties:
        zip_result = prop.get('zipcode', 'unknown')
        zip_counts[zip_result] = zip_counts.get(zip_result, 0) + 1
    
    print(f"Zip code distribution: {zip_counts}")
    if properties:
        print(f"First property: {properties[0].get('address')} - {properties[0].get('city', 'N/A')}, {properties[0].get('state', 'N/A')}")
