import os
from dotenv import load_dotenv
import requests
import time

load_dotenv()

api_key = os.getenv('GOOGLE_API_KEY')
search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

print("Testing Google Custom Search API...")
print(f"API Key: {api_key}")
print(f"Search Engine ID: {search_engine_id}")

# Test with different queries
test_queries = ['test', 'real estate', 'property for sale']

for query in test_queries:
    print(f"\n--- Testing query: '{query}' ---")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': search_engine_id,
        'q': query,
        'num': 1
    }

    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Found {len(data.get('items', []))} results")
            if data.get('items'):
                print(f"First result: {data['items'][0].get('title')}")
            break  # Success, no need to try more queries
        else:
            print(f"Response: {response.text}")
            print("❌ Failed, trying next query...")
            time.sleep(1)  # Small delay between requests
            
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(1)
