"""
Configuration management for Auto-Vote-Rating worker.
"""
import os
from pathlib import Path


class Config:
    """Configuration class for worker"""
    
    def __init__(self):
        # Data directory
        self.data_dir = os.getenv('DATA_DIR', '/app/data')
        
        # Dashboard settings
        self.dashboard_host = os.getenv('DASHBOARD_HOST', '0.0.0.0')
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', '8080'))
        
        # Timezone
        self.timezone = os.getenv('TZ', 'UTC')
        
        # Debug mode
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        
        # Browser settings for Playwright
        self.headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        self.browser_timeout = int(os.getenv('BROWSER_TIMEOUT', '30000'))
