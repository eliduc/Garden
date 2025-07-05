#!/usr/bin/env python3
"""
Garden Service Manager
Manages both the API server and sensor logger as separate processes
with health monitoring and automatic restart capabilities
"""

import subprocess
import threading
import time
import signal
import sys
import os
import logging
from datetime import datetime
import psutil
import configparser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('garden_services.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ServiceManager')

class ServiceManager:
    def __init__(self):
        self.services = {
            'api_server': {
                'command': [sys.executable, 'garden_api_server.py'],
                'process': None,
                'restart_count': 0,
                'last_restart': None,
                'name': 'API Server'
            },
            'db_logger': {
                'command': [sys.executable, 'garden_db_logger.py'],
                'process': None,
                'restart_count': 0,
                'last_restart': None,
                'name': 'Database Logger'
            }
        }
        self.running = True
        self.max_restart_attempts = 5
        self.restart_delay = 10  # seconds
        
    def start_service(self, service_name):
        """Start a service"""
        service = self.services[service_name]
        try:
            logger.info(f"Starting {service['name']}...")
            service['process'] = subprocess.Popen(
                service['command'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            service['last_restart'] = datetime.now()
            logger.info(f"{service['name']} started with PID {service['process'].pid}")
            return True
        except Exception as e:
            logger.error(f"Failed to start {service['name']}: {e}")
            return False
    
    def stop_service(self, service_name):
        """Stop a service gracefully"""
        service = self.services[service_name]
        if service['process'] and service['process'].poll() is None:
            logger.info(f"Stopping {service['name']}...")
            service['process'].terminate()
            try:
                service['process'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(f"{service['name']} didn't stop gracefully, forcing...")
                service['process'].kill()
            logger.info(f"{service['name']} stopped")
    
    def check_service_health(self, service_name):
        """Check if a service is healthy"""
        service = self.services[service_name]
        
        # Check if process exists
        if service['process'] is None:
            return False
        
        # Check if process is still running
        if service['process'].poll() is not None:
            return False
        
        # Additional health checks
        if service_name == 'api_server':
            # Check if API server responds to health endpoint
            try:
                import requests
                response = requests.get('http://localhost:5000/api/health', timeout=5)
                return response.status_code == 200
            except:
                return True  # Assume healthy if can't check
        
        return True
    
    def monitor_services(self):
        """Monitor services and restart if needed"""
        while self.running:
            for service_name, service in self.services.items():
                if not self.check_service_health(service_name):
                    logger.warning(f"{service['name']} is not healthy")
                    
                    # Check restart attempts
                    if service['restart_count'] >= self.max_restart_attempts:
                        logger.error(f"{service['name']} exceeded max restart attempts")
                        continue
                    
                    # Restart service
                    logger.info(f"Attempting to restart {service['name']}...")
                    self.stop_service(service_name)
                    time.sleep(self.restart_delay)
                    
                    if self.start_service(service_name):
                        service['restart_count'] += 1
                    else:
                        logger.error(f"Failed to restart {service['name']}")
            
            time.sleep(30)  # Check every 30 seconds
    
    def start_all(self):
        """Start all services"""
        for service_name in self.services:
            self.start_service(service_name)
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_services)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_all(self):
        """Stop all services"""
        self.running = False
        for service_name in self.services:
            self.stop_service(service_name)
    
    def get_status(self):
        """Get status of all services"""
        status = {}
        for service_name, service in self.services.items():
            is_healthy = self.check_service_health(service_name)
            status[service_name] = {
                'name': service['name'],
                'healthy': is_healthy,
                'pid': service['process'].pid if service['process'] else None,
                'restart_count': service['restart_count'],
                'last_restart': service['last_restart'].isoformat() if service['last_restart'] else None
            }
        return status

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal")
    manager.stop_all()
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start service manager
    manager = ServiceManager()
    
    logger.info("Starting Garden Service Manager")
    manager.start_all()
    
    # Keep main thread alive and show status
    try:
        while True:
            time.sleep(60)
            status = manager.get_status()
            logger.info("Service Status:")
            for service_name, info in status.items():
                logger.info(f"  {info['name']}: {'Healthy' if info['healthy'] else 'Unhealthy'} "
                          f"(PID: {info['pid']}, Restarts: {info['restart_count']})")
    except KeyboardInterrupt:
        pass
    
    logger.info("Shutting down Garden Service Manager")
    manager.stop_all()