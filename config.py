#!/usr/bin/env python3

SERVER_IDS = ['Bailey', 'Bona', 'Campbell', 'Clark', 'Jaquez']

SERVER_PORTS = {
    'Bailey': 10000,
    'Bona': 10001,
    'Campbell': 10002,
    'Clark': 10003,
    'Jaquez': 10004
}

SERVER_CONNECTIONS = {
    # Clark talks with Jaquez and Bona
    'Clark': ['Jaquez', 'Bona'],
    
    # Campbell talks with everyone else but Clark
    'Campbell': ['Bailey', 'Bona', 'Jaquez'],
    
    # Bona talks with Bailey (plus Clark and Campbell from above)
    'Bona': ['Bailey', 'Clark', 'Campbell'],
    
    'Bailey': ['Bona', 'Campbell'],
    
    'Jaquez': ['Clark', 'Campbell']
}

# Network settings
HOST = '127.0.0.1'
CONNECTION_RETRY_INITIAL = 1
CONNECTION_RETRY_MAX = 60
CONNECTION_RETRY_FACTOR = 2

# Command validation
MAX_RADIUS_KM = 50
MAX_INFO_LIMIT = 20

# Message handling
MAX_SEEN_MESSAGES = 1000

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# Google Places API settings
PLACES_API_BASE_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_API_HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-FieldMask": "*"
}