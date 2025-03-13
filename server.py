#!/usr/bin/env python3
import asyncio
import sys
import time
import json
from config import (
    SERVER_IDS, SERVER_PORTS, SERVER_CONNECTIONS, HOST,
    MAX_SEEN_MESSAGES
)
from utils import (
    parse_at_message, validate_iamat_command, validate_whatsat_command,
    parse_location, generate_message_id, has_seen_message
)
from logger import ServerLogger
from api import get_nearby_places

client_locations = {}

class ProxyServer:
    def __init__(self, server_id):
        self.server_id = server_id
        self.port = SERVER_PORTS[server_id]
        self.logger = ServerLogger(server_id)
        self.neighbors = SERVER_CONNECTIONS.get(server_id, [])
        self.server = None
        self.seen_messages = set()
    
    async def start(self):
        self.logger.startup()
        
        self.server = await asyncio.start_server(
            self.handle_client_connection, HOST, self.port)
        
        self.logger.info(f"Server {self.server_id} listening on {HOST}:{self.port}")
        async with self.server:
            await self.server.serve_forever()
    
    async def handle_client_connection(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.logger.client_connected(addr)
        
        try:
            data = await reader.readline()
            if data:
                message = data.decode().strip()
                self.logger.command_received(f"client {addr}", message)
                
                response = await self.process_command(message)
                
                if response:
                    writer.write(response.encode() + b'\n')
                    await writer.drain()
                    self.logger.command_processed(message, response)
        except Exception as e:
            self.logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            writer.close()
            await writer.wait_closed()
            self.logger.client_disconnected(addr)
    
    async def process_command(self, command):
        parts = command.split()
        
        if not parts:
            return "? "
        
        cmd_type = parts[0]
        
        if cmd_type == "IAMAT":
            return await self.handle_iamat(command, parts)
        elif cmd_type == "WHATSAT":
            return await self.handle_whatsat(command, parts)
        elif cmd_type == "AT":
            await self.handle_at_message(command)
            return None
        else:
            return f"? {command}"
    
    async def handle_iamat(self, command, parts):
        if not validate_iamat_command(parts):
            return f"? {command}"
        
        client_id, location, timestamp = parts[1], parts[2], parts[3]
        
        try:
            client_time = float(timestamp)
            server_time = time.time()
            time_diff = server_time - client_time
            
            time_diff_str = f"+{time_diff}" if time_diff >= 0 else f"{time_diff}"
            
            client_info = {
                'client_id': client_id,
                'location': location,
                'timestamp': timestamp,
                'server_id': self.server_id,
                'time_diff': time_diff
            }
            client_locations[client_id] = client_info
            
            response = f"AT {self.server_id} {time_diff_str} {client_id} {location} {timestamp}"
            
            client_locations[client_id]['msg'] = response
            
            await self.propagate_location(response)
            
            return response
            
        except ValueError:
            return f"? {command}"
    
    async def handle_whatsat(self, command, parts):
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
            
            location_str = client_info['location']
            latitude, longitude = parse_location(location_str)
            
            self.logger.api_request(latitude, longitude, radius_km)
            places_info = await get_nearby_places(latitude, longitude, radius_km, info_limit)
            
            places_info = places_info.rstrip('\n')
            
            return f"{at_response}\n{places_info}\n\n"
            
        except ValueError as e:
            self.logger.error(f"Error processing WHATSAT: {str(e)}")
            return f"? {command}"
    
    async def propagate_location(self, at_message):
        parts = at_message.split()
        if len(parts) < 6:
            self.logger.error(f"Invalid AT message format for propagation: {at_message}")
            return
            
        client_id = parts[3]
        timestamp = parts[5]
        
        message_id = generate_message_id(self.server_id, client_id, timestamp)
        
        if has_seen_message(message_id, self.seen_messages, MAX_SEEN_MESSAGES):
            self.logger.info(f"Already seen message for {client_id}, not propagating")
            return
        
        self.seen_messages.add(message_id)
        
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
        parts = at_message.split()
        if len(parts) < 6 or parts[0] != "AT":
            self.logger.error(f"Invalid AT message format: {at_message}")
            return
        
        server_id = parts[1]
        time_diff_str = parts[2]
        client_id = parts[3]
        location = parts[4]
        timestamp = parts[5]
        
        try:
            if time_diff_str.startswith('+'):
                time_diff = float(time_diff_str[1:])
            else:
                time_diff = float(time_diff_str)
        except ValueError:
            self.logger.error(f"Invalid time difference in AT message: {time_diff_str}")
            return
        
        update_client = False
        
        if client_id not in client_locations:
            update_client = True
        elif float(timestamp) > float(client_locations[client_id].get('timestamp', 0)):
            update_client = True
            
        if update_client:
            client_info = {
                'server_id': server_id,
                'client_id': client_id,
                'location': location,
                'timestamp': timestamp,
                'time_diff': time_diff,
                'msg': at_message
            }
            
            self.logger.info(f"Updating location for {client_id} from {server_id}")
            client_locations[client_id] = client_info
            
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