"""
Browser Context Manager for Auto-Vote-Rating.
Manages persistent Playwright browser contexts with CDP support for manual intervention.
"""
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    sync_playwright,
    Playwright,
)

logger = logging.getLogger(__name__)


class BrowserContextManager:
    """
    Manages persistent browser contexts per project.

    Each project gets an isolated browser profile stored in:
    {config.playwright_profile_base}/{project_key}/

    Supports:
    - Persistent contexts (cookies/sessions survive restarts)
    - Headful browsers with CDP for manual captcha solving
    - Context reuse for efficiency
    - Profile cleanup for inactive projects
    """

    def __init__(self, config):
        self.config = config
        self.playwright: Optional[Playwright] = None

        # Active persistent contexts (project_key -> BrowserContext)
        self.contexts: Dict[str, BrowserContext] = {}

        # Active headful browsers (project_key -> BrowserContext)
        self.manual_browsers: Dict[str, BrowserContext] = {}

        # Lifecycle information for manual browsers
        # project_key -> {"status": "launching"|"ready"|"error", "cdp_url": str, "error": Optional[str]}
        self.manual_browser_states: Dict[str, Dict[str, Optional[str]]] = {}

        # Ensure profile base directory exists
        Path(self.config.playwright_profile_base).mkdir(parents=True, exist_ok=True)
        logger.info(f"Browser profiles directory: {self.config.playwright_profile_base}")

    def _ensure_playwright(self):
        """Ensure Playwright is initialized"""
        if not self.playwright:
            self.playwright = sync_playwright().start()
            logger.info("Playwright initialized")

    def _sanitize_project_key(self, project_key: str) -> str:
        """
        Sanitize project key for safe filesystem usage.
        Replaces unsafe characters with hyphens.
        """
        # Keep alphanumeric, hyphens, underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', project_key)
        return sanitized

    def _get_profile_path(self, project_key: str) -> Path:
        """Get the profile directory path for a project"""
        safe_key = self._sanitize_project_key(project_key)
        return Path(self.config.playwright_profile_base) / safe_key

    def get_or_create_context(
        self,
        project_key: str,
        headless: bool = True
    ) -> Tuple[BrowserContext, Page]:
        """
        Get existing persistent context or create new one.

        Returns (BrowserContext, new Page).
        The context is reused across calls for the same project.
        Browser profile persists across container restarts.

        IMPORTANT: Cannot create context if manual browser is active for this project
        (profile directory would be locked).

        Args:
            project_key: Unique project identifier
            headless: Run in headless mode (default: True)

        Returns:
            Tuple of (context, page)
        """
        self._ensure_playwright()

        # Check if manual browser is active
        if project_key in self.manual_browsers:
            raise RuntimeError(
                f"Cannot create automated context for {project_key} - "
                "manual browser is active. Close manual browser first."
            )

        # Check if context already exists in memory
        if project_key in self.contexts:
            logger.debug(f"[{project_key}] Reusing existing browser context")
            context = self.contexts[project_key]
            page = context.new_page()
            return context, page

        # Create new persistent context
        profile_path = self._get_profile_path(project_key)
        profile_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{project_key}] Creating persistent browser context")
        logger.info(f"[{project_key}] Profile path: {profile_path}")

        # Launch persistent context with Chromium
        context = self.playwright.chromium.launch_persistent_context(
            str(profile_path),
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',  # Reduce memory usage
            ],
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )

        # Log profile info
        profile_size = sum(f.stat().st_size for f in profile_path.rglob('*') if f.is_file())
        profile_size_mb = profile_size / (1024 * 1024)
        logger.info(f"[{project_key}] Profile size: {profile_size_mb:.2f} MB")

        # Store in cache
        self.contexts[project_key] = context

        # Create new page
        page = context.new_page()

        return context, page

    def launch_headful_with_cdp(
        self,
        project_key: str,
        initial_url: Optional[str] = None,
    ) -> Tuple[Optional[BrowserContext], str]:
        """
        Launch a headless browser with CDP enabled for manual captcha solving.

        Uses the same persistent profile as the automated context,
        but with remote debugging (CDP) enabled so users can access it remotely.

        NOTE: Browser runs in headless mode (no GUI) since Docker containers don't
        have displays, but CDP allows full remote control via Chrome DevTools.

        IMPORTANT: This launches the browser in a background thread to avoid blocking.
        The method returns immediately with the CDP URL, while the browser starts
        in the background.

        Args:
            project_key: Unique project identifier

        Returns:
            Tuple of (None, cdp_url)
            Example: (None, "http://0.0.0.0:9222")
        """
        self._ensure_playwright()

        # Close existing persistent context if active (can't have both)
        if project_key in self.contexts:
            logger.info(f"[{project_key}] Closing automated context to launch headful browser")
            try:
                self.contexts[project_key].close()
            except Exception as e:
                logger.warning(f"[{project_key}] Error closing context: {e}")
            finally:
                del self.contexts[project_key]

            # Add small delay to ensure profile is fully released
            import time
            time.sleep(0.5)

        # Close existing manual browser if already running
        if project_key in self.manual_browsers:
            logger.info(f"[{project_key}] Closing existing manual browser")
            try:
                self.manual_browsers[project_key].close()
            except Exception as e:
                logger.warning(f"[{project_key}] Error closing browser: {e}")
            finally:
                del self.manual_browsers[project_key]

        profile_path = self._get_profile_path(project_key)
        profile_path.mkdir(parents=True, exist_ok=True)

        cdp_port = self.config.cdp_base_port
        # Use public host for user-facing URL (localhost or actual IP)
        # but browser will bind to cdp_host (0.0.0.0) to listen on all interfaces
        cdp_url = f"http://{self.config.cdp_public_host}:{cdp_port}"

        # Track launching state so worker can update UI
        self.manual_browser_states[project_key] = {
            "status": "launching",
            "cdp_url": cdp_url,
            "error": None,
            "initial_url": initial_url,
        }

        logger.info(f"[{project_key}] Launching browser with CDP in background thread (headless mode)")
        logger.info(f"[{project_key}] CDP URL: {cdp_url}")
        logger.info(f"[{project_key}] Profile path: {profile_path}")

        # Launch browser in background thread to avoid blocking
        def _launch_browser_background():
            """Background thread function to launch the browser"""
            try:
                logger.info(f"[{project_key}] Background thread: Starting browser launch")

                # Create a new Playwright instance for this thread (Playwright is not thread-safe)
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    # Launch persistent context with remote debugging enabled
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_path),
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            f'--remote-debugging-address=0.0.0.0',
                            f'--remote-debugging-port={cdp_port}',
                        ],
                        viewport={'width': 1280, 'height': 720},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    )

                    self.manual_browsers[project_key] = context

                    # Pre-open the vote page if provided so the user sees it immediately
                    if initial_url:
                        try:
                            page = context.new_page()
                            logger.info(f"[{project_key}] Background thread: Navigating manual browser to {initial_url}")
                            page.goto(initial_url, wait_until="load", timeout=self.config.browser_timeout)
                            logger.info(f"[{project_key}] Background thread: Manual browser page loaded")
                        except Exception as nav_err:
                            logger.warning(f"[{project_key}] Background thread: Failed to load {initial_url}: {nav_err}")
                    state = self.manual_browser_states.get(project_key) or {}
                    state["status"] = "ready"
                    state["cdp_url"] = cdp_url
                    state["error"] = None
                    self.manual_browser_states[project_key] = state

                    logger.info(f"[{project_key}] Background thread: Browser launched successfully")
                    logger.info(f"[{project_key}] Background thread: User can access at: {cdp_url}")

                    # Keep the thread alive by waiting for the browser to be closed
                    # The browser will stay open as long as this context manager is active
                    # This blocks the background thread but NOT the main worker thread
                    import time
                    while project_key in self.manual_browsers:
                        time.sleep(1)  # Check every second if browser should be closed

                    logger.info(f"[{project_key}] Background thread: Browser close requested, exiting")

            except Exception as e:
                logger.error(f"[{project_key}] Background thread: Failed to launch browser: {e}")
                if project_key in self.manual_browsers:
                    del self.manual_browsers[project_key]
                state = self.manual_browser_states.get(project_key) or {}
                state["status"] = "error"
                state["error"] = str(e)
                self.manual_browser_states[project_key] = state

        # Start the browser in a background thread
        import threading
        browser_thread = threading.Thread(
            target=_launch_browser_background,
            name=f"ManualBrowser-{project_key}",
            daemon=True  # Daemon thread will not prevent program exit
        )
        browser_thread.start()

        # Return immediately with CDP URL (browser will be ready in a few seconds)
        # We return None for the browser object since it's not yet available
        logger.info(f"[{project_key}] Browser launch initiated in background thread")
        logger.info(f"[{project_key}] Returning immediately - browser will be ready in 2-5 seconds")

        return None, cdp_url

    def get_manual_browser_status(self, project_key: str) -> Optional[Dict[str, Optional[str]]]:
        """Return the latest launch state for the manual browser."""
        state = self.manual_browser_states.get(project_key)
        return dict(state) if state else None

    def clear_manual_browser_status(self, project_key: str):
        """Clear launch state tracking for a manual browser."""
        if project_key in self.manual_browser_states:
            del self.manual_browser_states[project_key]

    def close_manual_browser(self, project_key: str):
        """
        Close the headful manual intervention browser.

        The browser profile persists, so cookies/session remain.

        Args:
            project_key: Unique project identifier
        """
        if project_key not in self.manual_browsers:
            logger.warning(f"[{project_key}] No manual browser to close")
            return

        logger.info(f"[{project_key}] Closing manual browser")

        try:
            self.manual_browsers[project_key].close()
            logger.info(f"[{project_key}] Manual browser closed successfully")
        except Exception as e:
            logger.error(f"[{project_key}] Error closing manual browser: {e}")
        finally:
            del self.manual_browsers[project_key]
            self.clear_manual_browser_status(project_key)

    def cleanup_project_context(self, project_key: str):
        """
        Clean up all resources for a specific project.

        Closes contexts and browsers but does NOT delete the profile.
        Use cleanup_old_profiles() to delete profile directories.

        Args:
            project_key: Unique project identifier
        """
        logger.info(f"[{project_key}] Cleaning up browser resources")

        # Close manual browser if active
        if project_key in self.manual_browsers:
            try:
                self.manual_browsers[project_key].close()
            except Exception as e:
                logger.warning(f"[{project_key}] Error closing manual browser: {e}")
            finally:
                del self.manual_browsers[project_key]

        # Close automated context if active
        if project_key in self.contexts:
            try:
                self.contexts[project_key].close()
            except Exception as e:
                logger.warning(f"[{project_key}] Error closing context: {e}")
            finally:
                del self.contexts[project_key]

        logger.info(f"[{project_key}] Browser resources cleaned up")

    def cleanup_old_profiles(self, days_threshold: int = 30):
        """
        Delete browser profiles for projects inactive for >days_threshold.

        This helps manage disk space by removing profiles that haven't
        been used recently. Profiles will be recreated if needed.

        Args:
            days_threshold: Delete profiles older than this many days (default: 30)
        """
        logger.info(f"Cleaning up profiles inactive for >{days_threshold} days")

        profile_base = Path(self.config.playwright_profile_base)
        if not profile_base.exists():
            logger.warning("Profile base directory does not exist")
            return

        now = datetime.now(timezone.utc)
        cleaned = 0
        total_size_freed = 0

        for profile_dir in profile_base.iterdir():
            if not profile_dir.is_dir():
                continue

            # Get last modified time
            try:
                last_modified = datetime.fromtimestamp(
                    profile_dir.stat().st_mtime,
                    tz=timezone.utc
                )
                age_days = (now - last_modified).days

                if age_days > days_threshold:
                    # Calculate size before deletion
                    size = sum(f.stat().st_size for f in profile_dir.rglob('*') if f.is_file())
                    size_mb = size / (1024 * 1024)

                    logger.info(f"Deleting old profile: {profile_dir.name} (age: {age_days} days, size: {size_mb:.2f} MB)")
                    shutil.rmtree(profile_dir)

                    cleaned += 1
                    total_size_freed += size

            except Exception as e:
                logger.error(f"Error cleaning profile {profile_dir.name}: {e}")

        if cleaned > 0:
            total_mb_freed = total_size_freed / (1024 * 1024)
            logger.info(f"Cleaned up {cleaned} old profiles, freed {total_mb_freed:.2f} MB")
        else:
            logger.info("No old profiles to clean up")

    def cleanup_all(self):
        """
        Clean up all browser resources.

        Closes all contexts and browsers but does NOT delete profiles.
        Call this on worker shutdown.
        """
        logger.info("Cleaning up all browser resources")

        # Close all manual browsers
        for project_key in list(self.manual_browsers.keys()):
            try:
                self.manual_browsers[project_key].close()
            except Exception as e:
                logger.warning(f"Error closing manual browser for {project_key}: {e}")
        self.manual_browsers.clear()

        # Close all automated contexts
        for project_key in list(self.contexts.keys()):
            try:
                self.contexts[project_key].close()
            except Exception as e:
                logger.warning(f"Error closing context for {project_key}: {e}")
        self.contexts.clear()

        # Stop Playwright
        if self.playwright:
            try:
                self.playwright.stop()
                logger.info("Playwright stopped")
            except Exception as e:
                logger.warning(f"Error stopping Playwright: {e}")
            finally:
                self.playwright = None

        logger.info("All browser resources cleaned up")
