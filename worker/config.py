"""
Configuration management for Auto-Vote-Rating worker.
"""
import os
from pathlib import Path


class Config:
    """Configuration class for worker"""
    
    def __init__(self):
        # Data directory (shared between worker + dashboard)
        self.data_dir = self._resolve_data_dir()
        
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

    def _resolve_data_dir(self) -> str:
        """
        Determine the canonical data directory.
        Prefers DATA_DIR env or /app/data inside the container.
        Falls back to repo-local data/ when running outside Docker.
        """
        env_dir = os.getenv('DATA_DIR')
        if env_dir:
            path = Path(env_dir).expanduser()
        else:
            default_container_path = Path('/app/data')
            if default_container_path.exists():
                path = default_container_path
            else:
                repo_root = Path(__file__).resolve().parents[1]
                path = repo_root / 'data'
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
