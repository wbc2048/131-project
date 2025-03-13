#!/usr/bin/env python3
import re
import json
import logging
from datetime import datetime
from config import MAX_RADIUS_KM, MAX_INFO_LIMIT, MAX_SEEN_MESSAGES

def parse_at_message(message):
    """Parse an AT message from another server"""
    parts = message.split()
    
    if len(parts) < 6 or parts[0] != "AT":
        return None
    
    try:
        server_id = parts[1]
        time_diff_str = parts[2]
        client_id = parts[3]
        location = parts[4]
        timestamp = parts[5]
        
        # Parse time difference (handle the + or - prefix)
        time_diff = parse_time_diff(time_diff_str)
        
        return {
            'server_id': server_id,
            'time_diff': time_diff,
            'client_id': client_id,
            'location': location,
            'timestamp': timestamp
        }
    except (ValueError, IndexError):
        return None

def validate_iamat_command(parts):
    """Validate an IAMAT command format"""
    if len(parts) != 4:
        return False
    
    # Validate client_id (no whitespace)
    if any(c.isspace() for c in parts[1]):
        return False
    
    # Validate location format (should match ISO 6709, like +34.068930-118.445127)
    if not validate_location_format(parts[2]):
        return False
    
    # Validate timestamp (should be a valid float)
    try:
        float(parts[3])
        return True
    except ValueError:
        return False

def validate_location_format(location_str):
    """Validate location string in ISO 6709 format"""
    location_pattern = r'^[+-]\d+\.\d+[+-]\d+\.\d+$'
    return bool(re.match(location_pattern, location_str))
    
def validate_whatsat_command(parts):
    """Validate a WHATSAT command format"""
    if len(parts) != 4:
        return False
    
    # Validate client_id (no whitespace)
    if any(c.isspace() for c in parts[1]):
        return False
    
    # Validate radius and limit (should be integers)
    try:
        radius = int(parts[2])
        limit = int(parts[3])
        
        # Check constraints
        if radius < 0 or radius > MAX_RADIUS_KM or limit < 0 or limit > MAX_INFO_LIMIT:
            return False
        
        return True
    except ValueError:
        return False

def format_time_diff(time_diff):
    """Format time difference with appropriate sign"""
    return f"+{time_diff}" if time_diff >= 0 else f"{time_diff}"

def parse_time_diff(time_diff_str):
    """Parse time difference string to float"""
    if time_diff_str.startswith('+'):
        return float(time_diff_str[1:])
    else:
        return float(time_diff_str)

def format_flood_message(server_id, client_info):
    """Format a message for flooding to other servers"""
    time_diff_str = format_time_diff(client_info['time_diff'])
    
    return (f"AT {server_id} {time_diff_str} {client_info['client_id']} "
            f"{client_info['location']} {client_info['timestamp']}")

def has_seen_message(message_id, seen_messages, max_seen=MAX_SEEN_MESSAGES):
    """Check if we've seen this message before (to prevent loops)"""
    if message_id in seen_messages:
        return True
    
    # Add to seen messages, limit size to prevent memory issues
    seen_messages.add(message_id)
    if len(seen_messages) > max_seen:
        # Remove oldest messages (this is simplified; in production you might want a more sophisticated approach)
        seen_messages.pop()
    
    return False

def generate_message_id(server_id, client_id, timestamp):
    """Generate a unique ID for a message to prevent loops in propagation"""
    return f"{server_id}:{client_id}:{timestamp}"

def parse_location(location_str):
    """
    Parse location string in ISO 6709 format (e.g., +34.068930-118.445127)
    
    Args:
        location_str (str): Location string in ISO 6709 format
    
    Returns:
        tuple: (latitude, longitude) as floats
    """
    # Check for valid format
    if not validate_location_format(location_str):
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