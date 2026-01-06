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

        # Vote button polling settings
        self.vote_button_max_wait = int(os.getenv('VOTE_BUTTON_MAX_WAIT', '12'))  # seconds
        self.vote_button_poll_interval = int(os.getenv('VOTE_BUTTON_POLL_INTERVAL', '1000'))  # milliseconds

        # Browser automation settings
        self.automation_enabled = os.getenv('AUTOMATION_ENABLED', 'true').lower() == 'true'
        self.playwright_profile_base = os.getenv('PLAYWRIGHT_PROFILE_DIR',
            os.path.join(self.data_dir, 'playwright-profile'))

        # Chrome DevTools Protocol settings (for manual captcha solving)
        self.cdp_enabled = True
        self.cdp_base_port = int(os.getenv('CDP_BASE_PORT', '9222'))
        self.cdp_host = os.getenv('CDP_HOST', '0.0.0.0')  # Bind address (listen on all interfaces)
        self.cdp_public_host = os.getenv('CDP_PUBLIC_HOST', 'localhost')  # Public address for users to connect
        self.cdp_auth_token = os.getenv('CDP_AUTH_TOKEN') or self._generate_random_token()

        # Captcha handling settings
        self.captcha_timeout_seconds = int(os.getenv('CAPTCHA_TIMEOUT_SECONDS', '300'))

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

    def _generate_random_token(self) -> str:
        """Generate a secure random token for CDP authentication"""
        import secrets
        return secrets.token_urlsafe(32)
