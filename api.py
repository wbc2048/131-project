#!/usr/bin/env python3
import aiohttp
import json
import re
import logging
from config import PLACES_API_BASE_URL, MAX_RADIUS_KM, MAX_INFO_LIMIT

# Import API key from separate file (not in version control)
try:
    from api_key import API_KEY
except ImportError:
    logging.error("API key file not found! Please create api_key.py with your Google Places API key.")
    API_KEY = "YOUR_API_KEY_GOES_HERE"  # This will cause API requests to fail

async def get_nearby_places(latitude, longitude, radius_km, limit):
    """
    Query the Google Places API for nearby places
    
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
    
    logger = logging.getLogger('places_api')
    
    # Construct the URL
    url = (
        f"{PLACES_API_BASE_URL}"
        f"?location={latitude},{longitude}"
        f"&radius={radius_m}"
        f"&key={API_KEY}"
    )
    
    logger.debug(f"Requesting places data with radius={radius_km}km, limit={limit}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"API request failed with status {response.status}")
                    return json.dumps({
                        "error": "Failed to retrieve data from Google Places API", 
                        "status": response.status
                    })
                
                data = await response.json()
                
                # Limit the number of results
                if "results" in data and len(data["results"]) > limit:
                    data["results"] = data["results"][:limit]
                
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

def parse_location(location_str):
    """
    Parse location string in ISO 6709 format (e.g., +34.068930-118.445127)
    
    Args:
        location_str (str): Location string in ISO 6709 format
    
    Returns:
        tuple: (latitude, longitude) as floats
    """
    # Check for valid format
    import re
    if not re.match(r'^[+-]\d+\.\d+[+-]\d+\.\d+
, location_str):
        raise ValueError(f"Invalid location format: {location_str}")
    
    # Determine where the longitude starts by finding the sign after the first digit
    lat_end = 0
    for i in range(1, len(location_str)):
        if location_str[i] in ('+', '-'):
            lat_end = i
            break
    
    if lat_end == 0:
        raise ValueError(f"Cannot parse location: {location_str}")
    
    # Extract latitude and longitude
    latitude = float(location_str[:lat_end])
    longitude = float(location_str[lat_end:])
    
    return latitude, longitude