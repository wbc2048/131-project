#!/usr/bin/env python3
import asyncio
import sys
import time
from config import (
    SERVER_IDS, SERVER_PORTS, SERVER_CONNECTIONS, HOST
)
from utils import (
    parse_at_message, validate_iamat_command, validate_whatsat_command
)
from logger import ServerLogger
from api import parse_location, get_nearby_places

# Store client locations (shared between all instances)
client_locations = {}

class ProxyServer:
    def __init__(self, server_id):
        self.server_id = server_id
        self.port = SERVER_PORTS[server_id]
        self.logger = ServerLogger(server_id)
        self.neighbors = SERVER_CONNECTIONS.get(server_id, [])
        self.server = None  # Will hold the asyncio server instance
    
    async def start(self):
        """Start the server"""
        self.logger.startup()
        
        # Start listening for client connections
        self.server = await asyncio.start_server(
            self.handle_client_connection, HOST, self.port)
        
        # Start the server
        async with self.server:
            await self.server.serve_forever()
    
    async def handle_client_connection(self, reader, writer):
        """Handle a single client command"""
        addr = writer.get_extra_info('peername')
        self.logger.client_connected(addr)
        
        try:
            data = await reader.readline()
            if data:
                message = data.decode().strip()
                self.logger.command_received(f"client {addr}", message)
                
                # Process the command
                response = await self.process_command(message)
                
                # Send response back to client
                writer.write(response.encode() + b'\n')
                await writer.drain()
        except Exception as e:
            self.logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
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
                
                # Format time difference with + sign if positive
                time_diff_str = f"+{time_diff}" if time_diff >= 0 else f"{time_diff}"
                
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
                response = f"AT {self.server_id} {time_diff_str} {client_id} {location} {timestamp}"
                await self.propagate_location(response)
                
                return response
                
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
                
                at_response = client_info.get('msg', None)
                if not at_response:
                    time_diff = client_info['time_diff']
                    time_diff_str = f"+{time_diff}" if time_diff >= 0 else f"{time_diff}"
                    at_response = f"AT {client_info['server_id']} {time_diff_str} {client_info['client_id']} {client_info['location']} {client_info['timestamp']}"
                
                # Parse location
                location_str = client_info['location']
                latitude, longitude = parse_location(location_str)
                
                # Get places information from Google Places API
                self.logger.api_request(latitude, longitude, radius_km)
                places_info = await get_nearby_places(latitude, longitude, radius_km, info_limit)
                
                # Ensure places_info doesn't already have trailing newlines
                places_info = places_info.rstrip('\n')
                
                # Format with exactly two newlines at the end
                return f"{at_response}\n{places_info}\n\n"
                
            except ValueError as e:
                self.logger.error(f"Error processing WHATSAT: {str(e)}")
                return f"? {command}"
        
        else:
            return f"? {command}"
    
    async def propagate_location(self, at_message):
        """Simple propagation method like in the working code"""
        parts = at_message.split()
        client_id = parts[3]
        
        for neighbor in self.neighbors:
            try:
                self.logger.info(f"Propagating to {neighbor}: {at_message}")
                reader, writer = await asyncio.open_connection(HOST, SERVER_PORTS[neighbor])
                
                writer.write((at_message + '\n').encode())
                await writer.drain()
                
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                self.logger.warning(f"Failed to propagate to {neighbor}: {e}")
    
    async def handle_at_message(self, at_message):
        """Process an AT message from another server"""
        parts = at_message.split()
        if len(parts) < 6 or parts[0] != "AT":
            return
        
        server_id = parts[1]
        client_id = parts[3]
        timestamp = parts[5]
        
        # Only update if we don't have info or the timestamp is newer
        if (client_id not in client_locations or 
            float(client_locations[client_id].get('timestamp', 0)) < float(timestamp)):
            
            client_info = {
                'server_id': server_id,
                'client_id': client_id,
                'location': parts[4],
                'timestamp': timestamp,
                'time_diff': float(parts[2].replace('+', '')),
                'msg': at_message
            }
            
            self.logger.info(f"Updating location for {client_id} from {server_id}")
            client_locations[client_id] = client_info
            
            # Propagate to other neighbors
            await self.propagate_location(at_message)
        else:
            self.logger.info(f"Ignoring older update for {client_id}")

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
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())