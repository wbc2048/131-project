#!/usr/bin/env python3
import aiohttp
import json
import re
from logger import setup_logger
from config import (
    MAX_RADIUS_KM, MAX_INFO_LIMIT, 
    PLACES_API_BASE_URL, PLACES_API_HEADERS
)
from utils import parse_location

# Import API key from separate file (not in version control)
try:
    from api_key import API_KEY
except ImportError:
    logger = setup_logger("api")
    logger.error("API key file not found! Please create api_key.py with your Google Places API key.")
    API_KEY = "YOUR_API_KEY_GOES_HERE"  # This will cause API requests to fail

async def get_nearby_places(latitude, longitude, radius_km, limit):
    """
    Query the Google Places API for nearby places using the v1 API
    
    Args:
        latitude (float): Latitude in decimal degrees
        longitude (float): Longitude in decimal degrees
        radius_km (int): Radius in kilometers (max 50)
        limit (int): Maximum number of results to return (max 20)
    
    Returns:
        str: JSON response from Google Places API
    """
    # Convert km to meters for the API
    radius_m = min(radius_km, MAX_RADIUS_KM) * 1000
    
    # Ensure limit is respected
    limit = min(limit, MAX_INFO_LIMIT)
    
    logger = setup_logger('places_api')
    logger.debug(f"Requesting places data with radius={radius_km}km, limit={limit}")
    
    # Prepare the request body for the API
    request_body = {
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius_m
            }
        },
        "maxResultCount": limit
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # API requires a POST request with JSON body
            headers = PLACES_API_HEADERS.copy()
            headers["X-Goog-Api-Key"] = API_KEY
            
            async with session.post(
                PLACES_API_BASE_URL,
                json=request_body,
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.error(f"API request failed with status {response.status}")
                    error_text = await response.text()
                    return json.dumps({
                        "error": "Failed to retrieve data from Google Places API", 
                        "status": response.status,
                        "details": error_text
                    })
                
                data = await response.json()
                
                # Format the JSON with indentation for readability
                json_str = json.dumps(data, indent=3)
                
                # Replace multiple newlines with a single newline as required
                json_str = re.sub(r'\n{2,}', '\n', json_str)
                
                # Remove trailing newlines
                json_str = json_str.rstrip("\n")
                
                return json_str
    
    except Exception as e:
        logger.error(f"Error accessing Google Places API: {str(e)}")
        return json.dumps({"error": f"Error accessing Google Places API: {str(e)}"})