#!/usr/bin/env python3
import asyncio
import sys
import time
from config import (
    SERVER_IDS, SERVER_PORTS, HOST, MAX_RADIUS_KM, MAX_INFO_LIMIT
)
from utils import (
    parse_at_message, validate_iamat_command, validate_whatsat_command,
    generate_message_id, format_time_diff, parse_location
)
from logger import ServerLogger
from proxy import ServerProxy
from api import get_nearby_places

# Store client locations (shared between all instances)
client_locations = {}

class ProxyServer:
    def __init__(self, server_id):
        self.server_id = server_id
        self.port = SERVER_PORTS[server_id]
        self.logger = ServerLogger(server_id)
        self.proxy = ServerProxy(server_id, self.logger)
        self.server = None  # Will hold the asyncio server instance
        
        # Register message handler
        self.proxy.register_message_handler(self.process_server_message)
    
    async def start(self):
        """Start the server and connect to neighbors"""
        self.logger.startup()
        
        # Start listening for client connections
        self.server = await asyncio.start_server(
            self.handle_client_connection, HOST, self.port)
        
        # Connect to neighbor servers
        await self.proxy.connect_to_all_neighbors()
        
        # Start the server
        async with self.server:
            await self.server.serve_forever()
    
    async def stop(self):
        """Stop the server gracefully"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        await self.proxy.close_all_connections()
        self.logger.shutdown()
    
    async def handle_client_connection(self, reader, writer):
        """Handle incoming client connections"""
        addr = writer.get_extra_info('peername')
        self.logger.client_connected(addr)
        
        while True:
            try:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode().strip()
                self.logger.command_received(f"client {addr}", message)
                
                # Process the command
                response = await self.process_command(message)
                
                # Send response back to client
                writer.write(response.encode() + b'\n')
                await writer.drain()
                
            except (ConnectionResetError, ConnectionError) as e:
                self.logger.warning(f"Client connection error: {e}")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error handling client: {e}", exc_info=True)
                break
        
        writer.close()
        await writer.wait_closed()
        self.logger.client_disconnected(addr)
    
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
                
                # Propagate to other servers
                await self.proxy.propagate_location(client_info)
                
                # Format response
                time_diff_str = format_time_diff(time_diff)
                return f"AT {self.server_id} {time_diff_str} {client_id} {location} {timestamp}"
                
            except ValueError:
                return f"? {command}"
        
        elif cmd_type == "WHATSAT":
            if not validate_whatsat_command(parts):
                return f"? {command}"
            
            client_id, radius_str, limit_str = parts[1], parts[2], parts[3]
            
            try:
                radius_km = int(radius_str)
                info_limit = int(limit_str)
                
                if client_id not in client_locations:
                    return f"? No information available for {client_id}"
                
                client_info = client_locations[client_id]
                time_diff = client_info['time_diff']
                time_diff_str = format_time_diff(time_diff)
                
                at_response = f"AT {client_info['server_id']} {time_diff_str} {client_info['client_id']} {client_info['location']} {client_info['timestamp']}"
                
                # Parse location
                location_str = client_info['location']
                latitude, longitude = parse_location(location_str)
                
                # Get places information from Google Places API
                self.logger.api_request(latitude, longitude, radius_km)
                places_info = await get_nearby_places(latitude, longitude, radius_km, info_limit)
                
                return f"{at_response}\n{places_info}\n\n"
                
            except ValueError as e:
                self.logger.error(f"Error processing WHATSAT: {str(e)}")
                return f"? {command}"
        
        else:
            return f"? {command}"
    
    async def process_server_message(self, server_id, message):
        """Process messages from other servers"""
        if message.startswith("AT "):
            client_info = parse_at_message(message)
            
            if client_info:
                client_id = client_info['client_id']
                timestamp = client_info['timestamp']
                
                # Update our local storage of client locations
                if (client_id not in client_locations or 
                    float(client_locations[client_id]['timestamp']) < float(timestamp)):
                    
                    self.logger.info(f"Updating location for {client_id} from server {client_info['server_id']}")
                    client_locations[client_id] = client_info
                    
                    # Propagate to other neighbors
                    await self.proxy.propagate_location(client_info, source_server=server_id)
        else:
            self.logger.warning(f"Received unexpected message type from {server_id}: {message}")

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
    
    server = ProxyServer(server_id)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        print(f"Shutting down {server_id} server...")
        await server.stop()
    except Exception as e:
        print(f"Error: {e}")
        await server.stop()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())