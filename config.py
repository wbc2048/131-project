#!/usr/bin/env python3
"""
Configuration settings for the proxy herd server application.
Centralizes all constants and configuration variables.
"""

# Server information
SERVER_IDS = ['Bailey', 'Bona', 'Campbell', 'Clark', 'Jaquez']

# Port assignments for each server
SERVER_PORTS = {
    'Bailey': 12027,
    'Bona': 12058,
    'Campbell': 12089,
    'Clark': 12120,
    'Jaquez': 12151
}

# Server communication topology as specified in the project
SERVER_CONNECTIONS = {
    # Clark talks with Jaquez and Bona
    'Clark': ['Jaquez', 'Bona'],
    
    # Campbell talks with everyone else but Clark
    'Campbell': ['Bailey', 'Bona', 'Jaquez'],
    
    # Bona talks with Bailey (plus Clark and Campbell from above)
    'Bona': ['Bailey', 'Clark', 'Campbell'],
    
    # Bailey's connections (derived from above rules)
    'Bailey': ['Bona', 'Campbell'],
    
    # Jaquez's connections (derived from above rules)
    'Jaquez': ['Clark', 'Campbell']
}

# Network settings
HOST = '127.0.0.1'  # Local host for development
CONNECTION_RETRY_INITIAL = 1  # Initial retry delay in seconds
CONNECTION_RETRY_MAX = 60     # Maximum retry delay in seconds
CONNECTION_RETRY_FACTOR = 2   # Exponential backoff factor

# Command validation
MAX_RADIUS_KM = 50   # Maximum radius for WHATSAT command
MAX_INFO_LIMIT = 20  # Maximum info limit for WHATSAT command

# Message handling
MAX_SEEN_MESSAGES = 1000  # Maximum number of seen messages to store (prevents memory leaks)

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Google Places API settings
PLACES_API_BASE_URL = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'