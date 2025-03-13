#!/usr/bin/env python3
#!/usr/bin/env python3
import asyncio
import sys
import logging
import json
import time
from datetime import datetime
from utils import (
    parse_at_message, validate_iamat_command, validate_whatsat_command,
    format_flood_message, has_seen_message, generate_message_id
)
from config import (
    SERVER_IDS, SERVER_PORTS, SERVER_CONNECTIONS, HOST, 
    CONNECTION_RETRY_INITIAL, CONNECTION_RETRY_MAX, CONNECTION_RETRY_FACTOR,
    MAX_RADIUS_KM, MAX_INFO_LIMIT, MAX_SEEN_MESSAGES, LOG_FORMAT, LOG_LEVEL
)

# Store client locations
client_locations = {}

# Set up logging
def setup_logging(server_id):
    logger = logging.getLogger(server_id)
    log_level = getattr(logging, LOG_LEVEL)
    logger.setLevel(log_level)
    
    # Log to file
    file_handler = logging.FileHandler(f"{server_id}.log")
    file_formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)
    
    return logger

class ProxyServer:
    def __init__(self, server_id, port, logger):
        self.server_id = server_id
        self.port = port
        self.logger = logger
        self.neighbors = SERVER_CONNECTIONS.get(server_id, [])
        self.server_connections = {}  # Store connections to other servers
        self.seen_messages = set()    # Track seen messages to prevent loops

    async def start(self):
        """Start the server and connect to neighbors"""
        self.logger.info(f"Starting server {self.server_id} on port {self.port}")
        
        # Start listening for client connections
        server = await asyncio.start_server(
            self.handle_client_connection, '127.0.0.1', self.port)
        
        # Connect to neighbor servers
        for neighbor in self.neighbors:
            asyncio.create_task(self.connect_to_server(neighbor))
        
        async with server:
            await server.serve_forever()
    
    async def connect_to_server(self, server_id):
        """Connect to another server in the herd"""
        if server_id not in SERVER_PORTS:
            self.logger.error(f"Unknown server ID: {server_id}")
            return
        
        port = SERVER_PORTS[server_id]
        retry_delay = CONNECTION_RETRY_INITIAL
        
        while True:
            try:
                self.logger.info(f"Connecting to {server_id} on port {port}")
                reader, writer = await asyncio.open_connection(HOST, port)
                self.server_connections[server_id] = (reader, writer)
                self.logger.info(f"Connected to {server_id}")
                
                # Handle the connection
                await self.handle_server_connection(server_id, reader, writer)
                
            except (ConnectionRefusedError, ConnectionResetError, ConnectionError) as e:
                self.logger.warning(f"Connection to {server_id} failed: {e}")
                if server_id in self.server_connections:
                    del self.server_connections[server_id]
                
                # Exponential backoff for retry
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * CONNECTION_RETRY_FACTOR, CONNECTION_RETRY_MAX)
    
    async def handle_client_connection(self, reader, writer):
        """Handle incoming client connections"""
        addr = writer.get_extra_info('peername')
        self.logger.info(f"New client connection from {addr}")
        
        while True:
            try:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode().strip()
                self.logger.info(f"Received from client {addr}: {message}")
                
                # Process the command
                response = await self.process_command(message)
                
                # Send response back to client
                self.logger.debug(f"Sending response to client {addr}: {response}")
                writer.write(response.encode() + b'\n')
                await writer.drain()
                
            except (ConnectionResetError, ConnectionError) as e:
                self.logger.warning(f"Client connection error: {e}")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error handling client: {e}")
                break
        
        writer.close()
        await writer.wait_closed()
        self.logger.info(f"Closed client connection from {addr}")
    
    async def handle_server_connection(self, server_id, reader, writer):
        """Handle connections with other servers"""
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode().strip()
                self.logger.info(f"Received from server {server_id}: {message}")
                
                # Process server message
                await self.process_server_message(server_id, message)
                
        except (ConnectionResetError, ConnectionError) as e:
            self.logger.warning(f"Server connection error with {server_id}: {e}")
        finally:
            if server_id in self.server_connections:
                del self.server_connections[server_id]
            writer.close()
            await writer.wait_closed()
            self.logger.info(f"Closed connection with server {server_id}")
            
            # Try to reconnect
            asyncio.create_task(self.connect_to_server(server_id))
    
    async def process_command(self, command):
        """Process client commands (IAMAT, WHATSAT)"""
        parts = command.split()
        
        if not parts:
            return "? "
        
        cmd_type = parts[0]
        
        if cmd_type == "IAMAT":
            if not validate_iamat_command(parts):
                return f"? {command}"
            
            client_id, location, timestamp = parts[1], parts[2], parts[3]
            
            try:
                client_time = float(timestamp)
                server_time = time.time()
                time_diff = server_time - client_time
                
                # Store client location
                client_info = {
                    'client_id': client_id,
                    'location': location,
                    'timestamp': timestamp,
                    'server_id': self.server_id,
                    'time_diff': time_diff
                }
                client_locations[client_id] = client_info
                
                # Generate a message ID for loop prevention
                message_id = generate_message_id(self.server_id, client_id, timestamp)
                self.seen_messages.add(message_id)
                
                # Propagate to other servers
                await self.propagate_location(client_info)
                
                # Format response
                return f"AT {self.server_id} {'+' if time_diff >= 0 else ''}{time_diff} {client_id} {location} {timestamp}"
                
            except ValueError:
                return f"? {command}"
        
        elif cmd_type == "WHATSAT":
            if len(parts) != 4:
                return f"? {command}"
            
            client_id, radius, limit = parts[1], parts[2], parts[3]
            
            try:
                radius_km = int(radius)
                info_limit = int(limit)
                
                if radius_km > 50 or info_limit > 20:
                    return f"? {command}"
                
                if client_id not in client_locations:
                    return f"? No information available for {client_id}"
                
                client_info = client_locations[client_id]
                at_response = f"AT {client_info['server_id']} {'+' if client_info['time_diff'] >= 0 else ''}{client_info['time_diff']} {client_info['client_id']} {client_info['location']} {client_info['timestamp']}"
                
                # Parse location from the stored client information
                from api import parse_location, get_nearby_places
                location_str = client_info['location']
                latitude, longitude = parse_location(location_str)
                
                # Get places information from Google Places API
                places_info = await get_nearby_places(latitude, longitude, radius_km, info_limit)
                
                return f"{at_response}\n{places_info}\n\n"
                
            except ValueError:
                return f"? {command}"
        
        else:
            return f"? {command}"
    
    async def process_server_message(self, server_id, message):
        """Process messages from other servers"""
        self.logger.info(f"Processing server message from {server_id}: {message}")
        
        # Check if it's an AT message (location propagation)
        if message.startswith("AT "):
            client_info = parse_at_message(message)
            
            if client_info:
                client_id = client_info['client_id']
                source_server = client_info['server_id']
                timestamp = client_info['timestamp']
                
                # Generate message ID for deduplication
                message_id = generate_message_id(source_server, client_id, timestamp)
                
                # Check if we've seen this message before to prevent loops
                if has_seen_message(message_id, self.seen_messages):
                    self.logger.info(f"Ignoring duplicate message {message_id}")
                    return
                
                # Add to seen messages
                self.seen_messages.add(message_id)
                
                # Update our local storage of client locations
                if client_id not in client_locations or float(client_locations[client_id]['timestamp']) < float(timestamp):
                    self.logger.info(f"Updating location for {client_id} from server {source_server}")
                    client_locations[client_id] = client_info
                    
                    # Propagate to other neighbors (except the one who sent it to us)
                    await self.propagate_location(client_info, exclude=[server_id])
    
    async def propagate_location(self, client_info, exclude=None):
        """
        Propagate client location to neighbor servers
        
        Args:
            client_info: Dictionary with client location details
            exclude: List of server IDs to exclude (e.g., the server that sent us this info)
        """
        if exclude is None:
            exclude = []
            
        message = format_flood_message(client_info['server_id'], client_info)
        
        for neighbor in self.neighbors:
            # Skip excluded servers
            if neighbor in exclude:
                continue
                
            if neighbor in self.server_connections:
                _, writer = self.server_connections[neighbor]
                try:
                    writer.write(message.encode() + b'\n')
                    await writer.drain()
                    self.logger.info(f"Propagated location to {neighbor}")
                except (ConnectionResetError, ConnectionError) as e:
                    self.logger.warning(f"Failed to propagate to {neighbor}: {e}")

async def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} SERVER_ID")
        print(f"Valid server IDs: {', '.join(SERVER_IDS)}")
        sys.exit(1)
    
    server_id = sys.argv[1]
    
    if server_id not in SERVER_IDS:
        print(f"Error: Unknown server ID: {server_id}")
        print(f"Valid server IDs: {', '.join(SERVER_IDS)}")
        sys.exit(1)
    
    logger = setup_logging(server_id)
    logger.info(f"Starting {server_id} server with {LOG_LEVEL} log level")
    
    server = ProxyServer(server_id, SERVER_PORTS[server_id], logger)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server shutting down")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())