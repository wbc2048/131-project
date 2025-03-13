#!/usr/bin/env python3
"""
Enhanced logging module for the proxy herd server application.
Provides consistent logging across all server components.
"""
import logging
import os
import time
from config import LOG_FORMAT, LOG_LEVEL

def setup_logger(server_id):
    """
    Set up a logger for the specified server ID.
    
    Args:
        server_id (str): The ID of the server
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure the logger
    logger = logging.getLogger(server_id)
    log_level = getattr(logging, LOG_LEVEL)
    logger.setLevel(log_level)
    
    # Prevent duplicate handlers when the function is called multiple times
    if not logger.handlers:
        # Log to file with rotation
        log_file = os.path.join(log_dir, f"{server_id}.log")
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(LOG_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Also log to console for debugging
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        logger.addHandler(console_handler)
    
    return logger

class ServerLogger:
    """
    Server logger class with specialized methods for server events
    """
    def __init__(self, server_id):
        self.logger = setup_logger(server_id)
        self.server_id = server_id
    
    def startup(self):
        """Log server startup"""
        self.logger.info(f"Server {self.server_id} starting up")
    
    def shutdown(self):
        """Log server shutdown"""
        self.logger.info(f"Server {self.server_id} shutting down")
    
    def client_connected(self, addr):
        """Log client connection"""
        self.logger.info(f"New client connection from {addr}")
    
    def client_disconnected(self, addr):
        """Log client disconnection"""
        self.logger.info(f"Client disconnected: {addr}")
    
    def server_connected(self, server_id):
        """Log server connection"""
        self.logger.info(f"Connected to server {server_id}")
    
    def server_disconnected(self, server_id):
        """Log server disconnection"""
        self.logger.info(f"Disconnected from server {server_id}")
    
    def command_received(self, source, command):
        """Log received command"""
        self.logger.info(f"Received from {source}: {command}")
    
    def command_processed(self, command, response):
        """Log processed command"""
        self.logger.info(f"Processed command {command} with response: {response}")
    
    def location_propagated(self, client_id, target_servers):
        """Log location propagation"""
        self.logger.info(f"Propagated location for {client_id} to servers: {', '.join(target_servers)}")
    
    def api_request(self, latitude, longitude, radius):
        """Log API request"""
        self.logger.info(f"Requesting places data for ({latitude}, {longitude}) with radius {radius}km")
    
    def error(self, message, exc_info=False):
        """Log error"""
        self.logger.error(message, exc_info=exc_info)
    
    def warning(self, message):
        """Log warning"""
        self.logger.warning(message)
    
    def debug(self, message):
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message):
        """Log info message"""
        self.logger.info(message)