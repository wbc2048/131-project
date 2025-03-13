#!/usr/bin/env python3
"""
Proxy communication module for the server herd.
Handles inter-server connections, message flooding, and connection recovery.
"""
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
    """
    Handles connections and communication between servers in the herd
    """
    def __init__(self, server_id, logger):
        self.server_id = server_id
        self.logger = logger
        self.neighbors = SERVER_CONNECTIONS.get(server_id, [])
        self.connections = {}  # Store connections to other servers
        self.seen_messages = set()  # Track seen messages to prevent loops
        self.connection_tasks = {}  # Track connection tasks
    
    async def connect_to_all_neighbors(self):
        """Start connection tasks for all neighbors"""
        for neighbor in self.neighbors:
            if neighbor not in self.connection_tasks or self.connection_tasks[neighbor].done():
                self.connection_tasks[neighbor] = asyncio.create_task(self.connect_to_server(neighbor))
    
    async def connect_to_server(self, server_id):
        """Connect to another server in the herd with exponential backoff"""
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
        """Handle ongoing connection with another server"""
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode().strip()
                self.logger.command_received(f"server {server_id}", message)
                
                # Forward the message to the message handler
                yield message
                
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
    
    async def send_to_server(self, server_id, message):
        """Send a message to a specific server"""
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
        """
        Flood a message to all connected neighbors except those in exclude list
        
        Args:
            message: The message to send
            source_server: The server that sent us this message (to be excluded)
            exclude: Additional servers to exclude
        
        Returns:
            list: Servers that the message was successfully sent to
        """
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
        """
        Propagate client location to neighbor servers
        
        Args:
            client_info: Dictionary with client location details
            source_server: The server that sent us this info (to be excluded)
            
        Returns:
            list: Servers that the location was propagated to
        """
        # Generate message ID for deduplication
        message_id = generate_message_id(
            client_info['server_id'], 
            client_info['client_id'], 
            client_info['timestamp']
        )
        
        # Check if we've seen this message before to prevent loops
        if message_id in self.seen_messages:
            self.logger.info(f"Skipping propagation of already seen message {message_id}")
            return []
        
        # Add to seen messages
        self.seen_messages.add(message_id)
        
        # Format the message for propagation
        message = format_flood_message(client_info['server_id'], client_info)
        
        # Flood to neighbors
        exclude = [source_server] if source_server else []
        sent_to = await self.flood_message(message, exclude=exclude)
        
        if sent_to:
            self.logger.location_propagated(client_info['client_id'], sent_to)
        
        return sent_to
    
    def is_connected_to(self, server_id):
        """Check if we are currently connected to a specific server"""
        return server_id in self.connections
    
    def get_connection_status(self):
        """Get the connection status of all neighbors"""
        status = {}
        for neighbor in self.neighbors:
            status[neighbor] = neighbor in self.connections
        return status
    
    async def close_all_connections(self):
        """Close all open connections"""
        for server_id, (_, writer) in self.connections.items():
            self.logger.info(f"Closing connection to {server_id}")
            writer.close()
            await writer.wait_closed()
        
        # Cancel all connection tasks
        for task in self.connection_tasks.values():
            if not task.done():
                task.cancel()
        
        self.connections = {}