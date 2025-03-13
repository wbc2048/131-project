#!/usr/bin/env python3
import asyncio
import time
from config import (
    SERVER_PORTS, SERVER_CONNECTIONS, HOST,
    CONNECTION_RETRY_INITIAL, CONNECTION_RETRY_MAX, CONNECTION_RETRY_FACTOR
)
from utils import (
    format_flood_message, has_seen_message, generate_message_id
)

class ServerProxy:
    def __init__(self, server_id, logger):
        self.server_id = server_id
        self.logger = logger
        self.neighbors = SERVER_CONNECTIONS.get(server_id, [])
        self.connections = {}  # Store connections to other servers
        self.seen_messages = set()  # Track seen messages to prevent loops
        self.connection_tasks = {}  # Track connection tasks
        self.message_handlers = []  # Callbacks for message handling
    
    async def connect_to_all_neighbors(self):
        for neighbor in self.neighbors:
            if neighbor not in self.connection_tasks or self.connection_tasks[neighbor].done():
                self.connection_tasks[neighbor] = asyncio.create_task(self.connect_to_server(neighbor))
    
    async def connect_to_server(self, server_id):
        if server_id not in SERVER_PORTS:
            self.logger.error(f"Unknown server ID: {server_id}")
            return
        
        port = SERVER_PORTS[server_id]
        retry_delay = CONNECTION_RETRY_INITIAL
        
        while True:
            try:
                self.logger.info(f"Connecting to {server_id} on port {port}")
                reader, writer = await asyncio.open_connection(HOST, port)
                self.connections[server_id] = (reader, writer)
                self.logger.server_connected(server_id)
                
                # Handle the connection
                await self.handle_server_connection(server_id, reader, writer)
                
            except (ConnectionRefusedError, ConnectionResetError, ConnectionError) as e:
                self.logger.warning(f"Connection to {server_id} failed: {e}")
                if server_id in self.connections:
                    del self.connections[server_id]
                
                # Exponential backoff for retry
                self.logger.info(f"Retrying connection to {server_id} in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * CONNECTION_RETRY_FACTOR, CONNECTION_RETRY_MAX)
    
    async def handle_server_connection(self, server_id, reader, writer):
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode().strip()
                self.logger.command_received(f"server {server_id}", message)
                
                # Forward the message to all registered handlers
                for handler in self.message_handlers:
                    await handler(server_id, message)
                
        except (ConnectionResetError, ConnectionError) as e:
            self.logger.warning(f"Server connection error with {server_id}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error with server {server_id}: {e}", exc_info=True)
        finally:
            if server_id in self.connections:
                del self.connections[server_id]
            writer.close()
            await writer.wait_closed()
            self.logger.server_disconnected(server_id)
            
            # Try to reconnect
            self.connection_tasks[server_id] = asyncio.create_task(self.connect_to_server(server_id))
    
    def register_message_handler(self, handler):
        self.message_handlers.append(handler)
    
    async def send_to_server(self, server_id, message):
        if server_id not in self.connections:
            self.logger.warning(f"Cannot send to {server_id}: not connected")
            return False
        
        try:
            _, writer = self.connections[server_id]
            writer.write(message.encode() + b'\n')
            await writer.drain()
            self.logger.debug(f"Sent to {server_id}: {message}")
            return True
        except (ConnectionResetError, ConnectionError) as e:
            self.logger.warning(f"Failed to send to {server_id}: {e}")
            return False
    
    async def flood_message(self, message, source_server=None, exclude=None):
        if exclude is None:
            exclude = []
        
        if source_server:
            exclude.append(source_server)
        
        sent_to = []
        for neighbor in self.neighbors:
            if neighbor in exclude:
                continue
            
            success = await self.send_to_server(neighbor, message)
            if success:
                sent_to.append(neighbor)
        
        return sent_to
    
    async def propagate_location(self, client_info, source_server=None):
        # Generate message ID for deduplication
        message_id = generate_message_id(
            client_info['server_id'], 
            client_info['client_id'], 
            client_info['timestamp']
        )
        
        # Check if we've seen this message before to prevent loops
        if has_seen_message(message_id, self.seen_messages):
            self.logger.info(f"Skipping propagation of already seen message {message_id}")
            return []
        
        # Format the message for propagation
        message = format_flood_message(client_info['server_id'], client_info)
        
        # Flood to neighbors
        exclude = [source_server] if source_server else []
        sent_to = await self.flood_message(message, exclude=exclude)
        
        if sent_to:
            self.logger.location_propagated(client_info['client_id'], sent_to)
        
        return sent_to
    
    def is_connected_to(self, server_id):
        return server_id in self.connections
    
    def get_connection_status(self):
        status = {}
        for neighbor in self.neighbors:
            status[neighbor] = neighbor in self.connections
        return status
    
    async def close_all_connections(self):
        for server_id, (_, writer) in self.connections.items():
            self.logger.info(f"Closing connection to {server_id}")
            writer.close()
            await writer.wait_closed()
        
        # Cancel all connection tasks
        for task in self.connection_tasks.values():
            if not task.done():
                task.cancel()
        
        self.connections = {}