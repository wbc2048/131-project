#!/usr/bin/env python3
import logging
import os
import time
from config import LOG_FORMAT, LOG_LEVEL

def setup_logger(name):
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(name)
    log_level = getattr(logging, LOG_LEVEL)
    logger.setLevel(log_level)
    
    if not logger.handlers:
        log_file = os.path.join(log_dir, f"{name}.log")
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(LOG_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        logger.addHandler(console_handler)
    
    return logger

class ServerLogger:
    def __init__(self, server_id):
        self.logger = setup_logger(server_id)
        self.server_id = server_id
    
    def startup(self):
        self.logger.info(f"Server {self.server_id} starting up")
    
    def shutdown(self):
        self.logger.info(f"Server {self.server_id} shutting down")
    
    def client_connected(self, addr):
        self.logger.info(f"New client connection from {addr}")
    
    def client_disconnected(self, addr):
        self.logger.info(f"Client disconnected: {addr}")
    
    def server_connected(self, server_id):
        self.logger.info(f"Connected to server {server_id}")
    
    def server_disconnected(self, server_id):
        self.logger.info(f"Disconnected from server {server_id}")
    
    def command_received(self, source, command):
        self.logger.info(f"Received from {source}: {command}")
    
    def command_processed(self, command, response):
        self.logger.info(f"Processed command {command} with response: {response}")
    
    def location_propagated(self, client_id, target_servers):
        self.logger.info(f"Propagated location for {client_id} to servers: {', '.join(target_servers)}")
    
    def api_request(self, latitude, longitude, radius):
        self.logger.info(f"Requesting places data for ({latitude}, {longitude}) with radius {radius}km")
    
    def error(self, message, exc_info=False):
        self.logger.error(message, exc_info=exc_info)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def debug(self, message):
        self.logger.debug(message)
    
    def info(self, message):
        self.logger.info(message)