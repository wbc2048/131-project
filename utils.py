#!/usr/bin/env python3
import re
import json
import logging
from datetime import datetime
from config import MAX_RADIUS_KM, MAX_INFO_LIMIT, MAX_SEEN_MESSAGES

def parse_at_message(message):
    parts = message.split()
    
    if len(parts) < 6 or parts[0] != "AT":
        return None
    
    try:
        server_id = parts[1]
        time_diff_str = parts[2]
        client_id = parts[3]
        location = parts[4]
        timestamp = parts[5]
        
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
    if len(parts) != 4:
        return False
    
    if any(c.isspace() for c in parts[1]):
        return False
    
    if not validate_location_format(parts[2]):
        return False
    
    try:
        float(parts[3])
        return True
    except ValueError:
        return False

def validate_location_format(location_str):
    location_pattern = r'^[+-]\d+\.\d+[+-]\d+\.\d+$'
    return bool(re.match(location_pattern, location_str))
    
def validate_whatsat_command(parts):
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
    return f"+{time_diff}" if time_diff >= 0 else f"{time_diff}"

def parse_time_diff(time_diff_str):
    if time_diff_str.startswith('+'):
        return float(time_diff_str[1:])
    else:
        return float(time_diff_str)

def format_flood_message(server_id, client_info):
    time_diff_str = format_time_diff(client_info['time_diff'])
    
    return (f"AT {server_id} {time_diff_str} {client_info['client_id']} "
            f"{client_info['location']} {client_info['timestamp']}")

def has_seen_message(message_id, seen_messages, max_seen=MAX_SEEN_MESSAGES):
    if message_id in seen_messages:
        return True
    
    # Add to seen messages, limit size to prevent memory issues
    seen_messages.add(message_id)
    if len(seen_messages) > max_seen:
        # Remove oldest messages (this is simplified; in production you might want a more sophisticated approach)
        seen_messages.pop()
    
    return False

def generate_message_id(server_id, client_id, timestamp):
    return f"{server_id}:{client_id}:{timestamp}"

def parse_location(location_str):
    if not validate_location_format(location_str):
        raise ValueError(f"Invalid location format: {location_str}")

    lat_end = 0
    for i in range(1, len(location_str)):
        if location_str[i] in ('+', '-'):
            lat_end = i
            break
    
    if lat_end == 0:
        raise ValueError(f"Cannot parse location: {location_str}")
    
    latitude = float(location_str[:lat_end])
    longitude = float(location_str[lat_end:])
    
    return latitude, longitude