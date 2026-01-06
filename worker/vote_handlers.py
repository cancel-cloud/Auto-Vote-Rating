"""
Site-Specific Vote Handlers for Auto-Vote-Rating.
Implements custom voting logic for different voting sites.
"""
import logging
import time
from typing import Dict, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class BaseVoteHandler:
    """Base class for site-specific vote handlers"""

    # Override these in subclasses
    VOTE_SELECTORS = []
    SUCCESS_INDICATORS = []

    def attempt_vote(self, page: Page, project: Dict) -> bool:
        """
        Attempt to click the vote button on the page.

        Args:
            page: Playwright Page object
            project: Project dictionary

        Returns:
            True if vote button was clicked, False otherwise
        """
        raise NotImplementedError

    def verify_success(self, page: Page) -> bool:
        """
        Check if vote was successful by looking for success indicators.

        Args:
            page: Playwright Page object

        Returns:
            True if success detected, False otherwise
        """
        raise NotImplementedError


class DefaultHandler(BaseVoteHandler):
    """
    Default handler for unknown sites.
    Uses common patterns to find vote buttons.
    """

    COOKIE_CONSENT_SELECTORS = [
        # Common cookie consent buttons - English
        'button:has-text("Accept")',
        'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("ACCEPT")',
        'a:has-text("Accept")',
        'a:has-text("Accept All")',

        # German translations
        'button:has-text("Akzeptieren")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Zustimmen")',

        # Common class names
        '.cookie-accept',
        '.cookie-consent-accept',
        '.accept-cookies',
        '.cookie-accept-all',
        'button.accept-all',
        '.cookie-banner button',

        # Common IDs
        '#accept-cookies',
        '#cookie-accept',
        '#acceptAllCookies',
        '#acceptCookies',

        # Common data attributes
        '[data-cookie-accept]',
        '[data-accept-cookies]',
        '[data-cookie-consent-accept]',

        # GDPR/Privacy dialogs
        'div[role="dialog"] button:has-text("Accept")',
        'div[role="dialog"] button:has-text("OK")',
        'div[role="dialog"] button:has-text("Akzeptieren")',
        '.gdpr-accept',
        '.privacy-accept',
        '.consent-accept',

        # Modal dialogs
        '.modal button:has-text("Accept")',
        '.modal-footer button:has-text("Accept")',
    ]

    VOTE_SELECTORS = [
        # Button elements with "vote" text
        'button:has-text("Vote")',
        'button:has-text("vote")',
        'button:has-text("VOTE")',

        # Link elements with "vote" text
        'a:has-text("Vote")',
        'a:has-text("vote")',
        'a:has-text("VOTE")',

        # Input submit buttons
        'input[type="submit"][value*="vote" i]',
        'input[type="submit"][value*="Vote"]',

        # Common class names
        'button.vote-button',
        'button.vote-btn',
        'a.vote-btn',
        'a.vote-button',
        '.vote-btn',
        '.vote-button',

        # Common IDs
        '#vote-button',
        '#vote-btn',
        '#voteBtn',
        '#vote',
    ]

    SUCCESS_INDICATORS = [
        # Text-based success messages
        'text=voted successfully',
        'text=thank you for voting',
        'text=vote recorded',
        'text=successfully voted',
        'text=Thanks for voting',
        'text=Vote successful',
        'text=/vote.*success/i',

        # Common success class names
        '.success-message',
        '.vote-success',
        '.alert-success',
        '.success',

        # Common success IDs
        '#success-message',
        '#vote-success',
    ]

    def dismiss_cookie_consent(self, page: Page, max_attempts: int = 3) -> bool:
        """
        Attempt to dismiss cookie consent popups/modals.

        Tries multiple selectors and polls for appearance.
        Returns True if consent was dismissed or not present.

        Args:
            page: Playwright Page object
            max_attempts: Maximum number of attempts to find consent dialog (default: 3)

        Returns:
            True if consent was dismissed or not present, False on error
        """
        logger.info("Checking for cookie consent dialogs...")

        for attempt in range(max_attempts):
            for selector in self.COOKIE_CONSENT_SELECTORS:
                try:
                    # Short timeout - cookie buttons should be immediately visible
                    element = page.wait_for_selector(
                        selector,
                        state='visible',
                        timeout=2000  # 2 seconds
                    )

                    if element:
                        logger.info(f"Found cookie consent button: {selector}")
                        element.scroll_into_view_if_needed()
                        page.wait_for_timeout(300)
                        element.click()

                        # Wait for dialog to dismiss
                        page.wait_for_timeout(1000)
                        logger.info("Cookie consent dismissed")
                        return True

                except PlaywrightTimeout:
                    continue
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue

            # If first attempt found nothing, likely no consent dialog
            if attempt == 0:
                logger.info("No cookie consent dialog detected")
                return True

            # Wait before retrying (dialog might appear after interaction)
            page.wait_for_timeout(1000)

        logger.info("No cookie consent to dismiss")
        return True

    def wait_for_vote_button_with_polling(
        self,
        page: Page,
        max_wait_seconds: int = 12,
        poll_interval_ms: int = 1000
    ) -> Tuple[bool, Optional[str]]:
        """
        Wait for vote button to appear with periodic checking.

        Polls page every 1 second for up to 12 seconds to find vote button.
        Also re-checks for cookie consent during polling.

        Args:
            page: Playwright Page object
            max_wait_seconds: Maximum seconds to poll (default: 12)
            poll_interval_ms: Milliseconds between polls (default: 1000)

        Returns:
            Tuple of (found: bool, selector: str) - Whether button was found and which selector matched
        """
        logger.info(f"Polling for vote button (up to {max_wait_seconds}s)...")

        start_time = time.time()
        iterations = 0

        while (time.time() - start_time) < max_wait_seconds:
            iterations += 1
            elapsed = int(time.time() - start_time)
            logger.debug(f"Poll iteration {iterations} (elapsed: {elapsed}s)")

            # Re-check for cookie consent (might appear after initial page load)
            if iterations % 3 == 0:  # Every 3 seconds
                logger.debug("Re-checking for cookie consent...")
                self.dismiss_cookie_consent(page, max_attempts=1)

            # Try to find vote button
            for selector in self.VOTE_SELECTORS:
                try:
                    element = page.wait_for_selector(
                        selector,
                        state='visible',
                        timeout=poll_interval_ms
                    )

                    if element:
                        logger.info(f"Vote button found after {elapsed}s: {selector}")
                        return True, selector

                except PlaywrightTimeout:
                    continue
                except Exception as e:
                    logger.debug(f"Error checking selector {selector}: {e}")
                    continue

            # Wait before next poll iteration
            page.wait_for_timeout(poll_interval_ms)

        logger.warning(f"Vote button not found after {max_wait_seconds}s polling")
        return False, None

    def attempt_vote(self, page: Page, project: Dict) -> bool:
        """
        Attempt to find and click the vote button.

        New flow:
        1. Dismiss cookie consent
        2. Poll for vote button (10-12 seconds with periodic checks)
        3. Click when found

        Args:
            page: Playwright Page object
            project: Project dictionary

        Returns:
            True if vote button was clicked, False otherwise
        """
        logger.info(f"Attempting vote for {project.get('key')}")

        # STEP 1: Dismiss cookie consent
        self.dismiss_cookie_consent(page)

        # STEP 2: Wait for page to fully settle
        page.wait_for_timeout(2000)

        # STEP 3: Poll for vote button with dynamic waits
        found, selector = self.wait_for_vote_button_with_polling(
            page,
            max_wait_seconds=12,
            poll_interval_ms=1000
        )

        if not found:
            logger.error("Vote button not found after polling")
            return False

        # STEP 4: Click the vote button
        try:
            element = page.query_selector(selector)
            if not element:
                logger.error(f"Element no longer present: {selector}")
                return False

            element.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            element.click()

            logger.info(f"Clicked vote button: {selector}")
            return True

        except Exception as e:
            logger.error(f"Error clicking vote button: {e}")
            return False

    def verify_success(self, page: Page) -> bool:
        """Check for success indicators"""
        for indicator in self.SUCCESS_INDICATORS:
            try:
                element = page.query_selector(indicator)
                if element:
                    logger.info(f"Success indicator found: {indicator}")
                    return True
            except Exception as e:
                logger.debug(f"Indicator {indicator} check failed: {e}")
                continue

        # If no explicit success indicator, check if we're still on the same page
        # or if the vote button disappeared (common pattern)
        try:
            # Vote button should disappear after successful vote
            for selector in self.VOTE_SELECTORS[:3]:  # Check first few selectors
                if page.query_selector(selector):
                    logger.debug("Vote button still present - might not have succeeded")
                    return False
        except Exception:
            pass

        logger.info("No explicit success indicator, assuming success")
        return True


class MinecraftServerListNetHandler(DefaultHandler):
    """
    Handler for minecraft-serverlist.net with error detection

    URL pattern: https://minecraft-serverlist.net/vote/<serverid>
    """

    VOTE_SELECTORS = [
        # Site-specific selectors
        'button.btn-success',
        'button.btn.btn-success.btn-lg',
        'button[type="submit"].btn-success',
        '#vote-button',
        'button.vote-btn',
        'button[type="submit"]',
        'a.btn-vote',
        'button:has-text("Vote")',
        'button:has-text("Abstimmen")',  # German
        'a:has-text("Vote for this server")',

        # Form submit
        'form[action*="vote"] button[type="submit"]',
        'form[action*="vote"] input[type="submit"]',
        'form button[type="submit"]',
    ]

    SUCCESS_INDICATORS = [
        'text=successfully voted',
        'text=voted successfully',
        'text=Thank you for voting',
        'text=Your vote has been recorded',
        '.success-message',
        '.vote-success',
        '.alert-success',
    ]

    def attempt_vote(self, page: Page, project: Dict) -> bool:
        """
        minecraft-serverlist.net specific voting with nickname handling.
        Checks for error messages before attempting vote.
        """
        logger.info(f"[minecraft-serverlist.net] Attempting vote for {project.get('key')}")

        # Wait for page to settle
        page.wait_for_timeout(1000)

        # Check for error messages BEFORE attempting vote
        try:
            error = page.query_selector('div.alert.alert-danger')
            if error and error.is_visible():
                error_text = error.text_content()
                logger.warning(f"[minecraft-serverlist.net] Error message detected: {error_text[:100]}")

                # Check for "already voted" cooldown
                if 'Du hast bereits' in error_text or 'already voted' in error_text.lower():
                    logger.info("[minecraft-serverlist.net] Already voted - cooldown active")
                    return False

                # Check for captcha requirement
                if 'captcha' in error_text.lower():
                    logger.info("[minecraft-serverlist.net] Captcha required")
                    return False

                # Generic error
                logger.warning("[minecraft-serverlist.net] Generic error detected on page")
                return False
        except Exception as e:
            logger.debug(f"[minecraft-serverlist.net] Error checking failed: {e}")

        # Dismiss cookie consent
        logger.info("[minecraft-serverlist.net] Checking for cookie consent...")
        self.dismiss_cookie_consent(page)

        # Wait for page to settle after dismissing cookies
        page.wait_for_timeout(1000)

        # Fill nickname field if present
        try:
            nick_field = page.query_selector('#mcname')
            if nick_field and nick_field.is_visible():
                nick = project.get('nick', '')
                if nick:
                    logger.info(f"[minecraft-serverlist.net] Filling nickname field: {nick}")
                    nick_field.fill(nick)
                    page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"[minecraft-serverlist.net] No nickname field or error filling: {e}")

        # Poll for vote button
        logger.info("[minecraft-serverlist.net] Polling for vote button...")
        found, selector = self.wait_for_vote_button_with_polling(
            page,
            max_wait_seconds=10,
            poll_interval_ms=1000
        )

        if not found:
            logger.warning("[minecraft-serverlist.net] Vote button not found after polling")
            return False

        # Click vote button
        try:
            element = page.query_selector(selector)
            if not element:
                logger.error(f"[minecraft-serverlist.net] Element disappeared: {selector}")
                return False

            element.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            element.click()

            logger.info("[minecraft-serverlist.net] Vote button clicked")
            return True

        except Exception as e:
            logger.error(f"[minecraft-serverlist.net] Error clicking vote button: {e}")
            return False

    def verify_success(self, page: Page) -> bool:
        """Verify vote success for minecraft-serverlist.net"""
        # Wait a bit for success message to appear
        page.wait_for_timeout(2000)

        for indicator in self.SUCCESS_INDICATORS:
            try:
                element = page.query_selector(indicator)
                if element:
                    logger.info(f"[minecraft-serverlist.net] Success: {indicator}")
                    return True
            except Exception as e:
                logger.debug(f"[minecraft-serverlist.net] Indicator failed: {indicator} - {e}")
                continue

        # Check for URL change (some sites redirect after vote)
        current_url = page.url
        if 'success' in current_url.lower() or 'thanks' in current_url.lower():
            logger.info("[minecraft-serverlist.net] Success detected in URL")
            return True

        logger.info("[minecraft-serverlist.net] No explicit success indicator")
        return False


class MinecraftServerEUHandler(DefaultHandler):
    """
    Handler for minecraft-server.eu with dialog detection

    URL pattern: https://minecraft-server.eu/vote/index/<serverid>/
    """

    # Site-specific cookie consent selectors (in addition to defaults)
    COOKIE_CONSENT_SELECTORS = [
        # Site-specific dialog selectors
        'div[role="dialog"] button',
        'div[role="dialog"] button:has-text("OK")',
        'div[role="dialog"] button:has-text("Accept")',
        'div[role="dialog"] button:has-text("Akzeptieren")',
        '.modal-footer button',
        '.modal button.btn-primary',
        '.modal-content button',
    ] + DefaultHandler.COOKIE_CONSENT_SELECTORS

    VOTE_SELECTORS = [
        # voteBox selectors (primary voting area)
        '#voteBox button',
        '#voteBox input[type="submit"]',
        '#voteBox button[type="submit"]',

        # Common vote button patterns
        'button.vote-button',
        'button[type="submit"]',
        'a.btn-vote',
        '#vote-btn',
        'button:has-text("Vote")',
        'button:has-text("Submit Vote")',
        'button:has-text("Abstimmen")',  # German

        # Form selectors
        'form[method="post"] button[type="submit"]',
        'form[action*="vote"] button',
    ]

    SUCCESS_INDICATORS = [
        'text=successfully voted',
        'text=vote successful',
        'text=Thank you',
        'text=Your vote has been counted',
        '.success',
        '.vote-success',
        '.alert-success',
        '#success-message',
    ]

    def attempt_vote(self, page: Page, project: Dict) -> bool:
        """
        minecraft-server.eu specific voting with dialog handling.
        Implements polling pattern from reference JS.
        """
        logger.info(f"[minecraft-server.eu] Attempting vote for {project.get('key')}")

        # Check for redirect to forum (error condition)
        if '/forum' in page.url:
            logger.warning("[minecraft-server.eu] Redirected to forum - invalid vote URL")
            return False

        # Dismiss cookie/TOS dialog (site-specific selectors)
        logger.info("[minecraft-server.eu] Checking for dialogs/consent...")
        self.dismiss_cookie_consent(page, max_attempts=3)

        # Wait for page to settle
        page.wait_for_timeout(2000)

        # Check if nickname field needs to be filled
        try:
            nick_input = page.query_selector('#voteBox input[type="text"]')
            if nick_input and nick_input.is_visible():
                nick = project.get('nick', '')
                if nick:
                    logger.info(f"[minecraft-server.eu] Filling nickname field: {nick}")
                    nick_input.fill(nick)
                    page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"[minecraft-server.eu] No nickname field or error filling: {e}")

        # Poll for vote box/button (may take time to appear)
        logger.info("[minecraft-server.eu] Polling for vote button...")
        found, selector = self.wait_for_vote_button_with_polling(
            page,
            max_wait_seconds=12,
            poll_interval_ms=1000
        )

        if not found:
            logger.warning("[minecraft-server.eu] Vote button not found after polling")
            return False

        # Click vote button
        try:
            element = page.query_selector(selector)
            if not element:
                logger.error(f"[minecraft-server.eu] Element disappeared: {selector}")
                return False

            element.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            element.click()

            logger.info("[minecraft-server.eu] Vote button clicked")
            return True

        except Exception as e:
            logger.error(f"[minecraft-server.eu] Error clicking vote button: {e}")
            return False

    def verify_success(self, page: Page) -> bool:
        """Verify vote success for minecraft-server.eu"""
        # Wait for success message
        page.wait_for_timeout(2000)

        for indicator in self.SUCCESS_INDICATORS:
            try:
                element = page.query_selector(indicator)
                if element:
                    logger.info(f"[minecraft-server.eu] Success: {indicator}")
                    return True
            except Exception as e:
                logger.debug(f"[minecraft-server.eu] Indicator failed: {indicator} - {e}")
                continue

        # Check URL for success indicators
        current_url = page.url
        if 'success' in current_url.lower() or 'thanks' in current_url.lower():
            logger.info("[minecraft-server.eu] Success detected in URL")
            return True

        logger.info("[minecraft-server.eu] No explicit success indicator")
        return False


class VoteHandlerRegistry:
    """
    Registry of site-specific vote handlers.
    Maps site keys to handler instances.
    """

    def __init__(self):
        self.handlers = {
            'minecraft-serverlist.net': MinecraftServerListNetHandler(),
            'minecraft-server.eu': MinecraftServerEUHandler(),
            'default': DefaultHandler(),
        }

        logger.info(f"Vote handler registry initialized with {len(self.handlers) - 1} site-specific handlers")

    def get_handler(self, site_key: str) -> BaseVoteHandler:
        """
        Get the appropriate handler for a site.

        Args:
            site_key: Site identifier (e.g., 'minecraft-server.eu')

        Returns:
            Handler instance (site-specific or default)
        """
        handler = self.handlers.get(site_key, self.handlers['default'])

        if site_key not in self.handlers and site_key != 'default':
            logger.info(f"No specific handler for '{site_key}', using default handler")

        return handler

    def add_handler(self, site_key: str, handler: BaseVoteHandler):
        """
        Add or update a handler for a site.

        Args:
            site_key: Site identifier
            handler: Handler instance
        """
        self.handlers[site_key] = handler
        logger.info(f"Added handler for '{site_key}'")
