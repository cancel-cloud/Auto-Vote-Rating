"""
Voter class that handles the actual voting operations using Playwright.
Supports automated voting with persistent browser contexts and captcha detection.
"""
import logging
from typing import Dict, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from sites import build_vote_url
from browser_manager import BrowserContextManager
from vote_handlers import VoteHandlerRegistry

logger = logging.getLogger(__name__)


class Voter:
    """
    Handles voting operations using browser automation with persistent contexts.
    Supports automated voting, captcha detection, and manual intervention.
    """

    def __init__(self, db, config):
        self.db = db
        self.config = config

        # Initialize browser context manager (handles persistent contexts)
        self.browser_manager = BrowserContextManager(config)

        # Initialize vote handler registry (site-specific voting logic)
        self.vote_handler_registry = VoteHandlerRegistry()

        logger.info("Voter initialized with automated voting support")
    
    def vote(self, project: Dict) -> Dict:
        """
        Execute automated voting with persistent browser context.

        Process:
        1. Load persistent context (reuses cookies/session from previous runs)
        2. Navigate to vote page
        3. Detect captcha immediately
        4. If no captcha → attempt automated vote
        5. Verify success

        Returns dict with:
        - success: bool - True if vote succeeded
        - needs_captcha: bool - True if captcha detected
        - captcha_type: str - Type of captcha ('recaptcha-v2', 'hcaptcha', etc.)
        - automated: bool - True if vote completed automatically
        - error: str - Error message if failed
        - message: str - Human-readable result message
        """
        project_key = project.get('key')
        site_key = project.get('rating')

        logger.info(f"[{project_key}] Starting vote attempt for {site_key}")

        try:
            # Get persistent browser context (reuses existing cookies/session)
            context, page = self.browser_manager.get_or_create_context(
                project_key,
                headless=self.config.headless
            )

            try:
                # Get vote URL
                vote_url = self._get_vote_url(project)
                if not vote_url:
                    return {
                        'success': False,
                        'error': 'Could not determine vote URL'
                    }

                logger.info(f"[{project_key}] Navigating to {vote_url}")

                # Navigate to vote page
                page.goto(
                    vote_url,
                    wait_until='networkidle',
                    timeout=self.config.browser_timeout
                )

                # Log page details for debugging
                logger.info(f"[{project_key}] Page loaded: {page.url}")
                logger.info(f"[{project_key}] Page title: {page.title()}")

                # Wait for page to settle (reduced since handler does dynamic polling)
                page.wait_for_timeout(1000)

                # STEP 1: Detect captcha immediately after page load
                captcha_type = self._detect_captcha(page)
                if captcha_type:
                    logger.warning(f"[{project_key}] Captcha detected: {captcha_type}")
                    return {
                        'success': False,
                        'needs_captcha': True,
                        'captcha_type': captcha_type,
                        'message': f'Captcha detected: {captcha_type}. Manual intervention required.'
                    }

                # STEP 2: Attempt automated vote (if automation enabled)
                if self.config.automation_enabled:
                    logger.info(f"[{project_key}] Attempting automated vote with site: {site_key}")

                    # Get appropriate handler for this site
                    handler = self.vote_handler_registry.get_handler(site_key)
                    handler_name = handler.__class__.__name__
                    logger.info(f"[{project_key}] Using handler: {handler_name}")

                    # Attempt to click vote button
                    clicked = handler.attempt_vote(page, project)

                    if not clicked:
                        logger.warning(f"[{project_key}] Could not find vote button")
                        return {
                            'success': False,
                            'error': 'Vote button not found',
                            'message': 'Could not locate vote button on page'
                        }

                    # Wait for vote to process
                    page.wait_for_timeout(2000)

                    # Check if captcha appeared after clicking
                    post_click_captcha = self._detect_captcha(page)
                    if post_click_captcha:
                        logger.warning(f"[{project_key}] Captcha appeared after click: {post_click_captcha}")
                        return {
                            'success': False,
                            'needs_captcha': True,
                            'captcha_type': post_click_captcha,
                            'message': f'Captcha appeared after clicking: {post_click_captcha}'
                        }

                    # Verify success
                    success = handler.verify_success(page)

                    if success:
                        logger.info(f"[{project_key}] ✓ Automated vote successful")
                        return {
                            'success': True,
                            'automated': True,
                            'message': 'Vote completed automatically'
                        }
                    else:
                        logger.warning(f"[{project_key}] Vote may have failed - no success indicator")
                        return {
                            'success': False,
                            'error': 'Vote verification failed',
                            'message': 'Vote button clicked but success not confirmed'
                        }

                else:
                    # Automation disabled - reminder mode fallback
                    logger.info(f"[{project_key}] Automation disabled - opening page only")
                    page.wait_for_timeout(5000)
                    return {
                        'success': True,
                        'message': 'Vote page opened - please complete manually (automation disabled)'
                    }

            except PlaywrightTimeout:
                logger.error(f"[{project_key}] Timeout while loading vote page")
                return {
                    'success': False,
                    'error': 'Page load timeout'
                }
            except Exception as e:
                logger.error(f"[{project_key}] Error during vote: {e}", exc_info=True)
                return {
                    'success': False,
                    'error': str(e)
                }
            finally:
                # Close page but keep context alive for reuse
                page.close()

        except RuntimeError as e:
            # Handle case where manual browser is active
            if "manual browser is active" in str(e):
                logger.warning(f"[{project_key}] Cannot vote - manual browser is active")
                return {
                    'success': False,
                    'needs_manual': True,
                    'error': 'Manual browser is active',
                    'message': 'Waiting for manual captcha solve'
                }
            # Re-raise if it's a different RuntimeError
            raise

        except Exception as e:
            logger.error(f"[{project_key}] Fatal error in vote method: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Fatal error: {str(e)}'
            }
    
    def _get_vote_url(self, project: Dict) -> Optional[str]:
        """Get the voting URL for a project"""
        if project.get('voteUrl'):
            return project['voteUrl']
        if project.get('voteUrlNormalized'):
            return project['voteUrlNormalized']
        if project.get('responseURL'):
            return project['responseURL']
        rating = project.get('rating')
        project_id = project.get('id')
        return build_vote_url(rating, project_id)
    
    def _detect_captcha(self, page: Page) -> Optional[str]:
        """
        Detect if a captcha is present on the page.

        Checks for:
        - reCAPTCHA v2 (visible challenge)
        - reCAPTCHA v3 (invisible badge)
        - hCaptcha
        - Cloudflare Turnstile
        - Generic challenge forms

        Returns:
            Captcha type string if detected, None otherwise
        """
        # reCAPTCHA v2 (visible challenge with iframe)
        if page.query_selector('iframe[src*="recaptcha/api2"]'):
            return 'recaptcha-v2'

        # reCAPTCHA v3 (invisible - shows badge in corner)
        if page.query_selector('.grecaptcha-badge'):
            # v3 is invisible, might not need manual solving
            # Only flag if there's also a visible challenge
            if page.query_selector('iframe[src*="recaptcha"]'):
                return 'recaptcha-v3'

        # reCAPTCHA - generic check
        if page.query_selector('iframe[src*="google.com/recaptcha"]'):
            return 'recaptcha'

        # hCaptcha
        if page.query_selector('iframe[src*="hcaptcha.com"]') or page.query_selector('.h-captcha'):
            return 'hcaptcha'

        # Cloudflare Turnstile
        if page.query_selector('iframe[src*="cloudflare"]') or page.query_selector('.cf-turnstile'):
            return 'cloudflare-turnstile'

        # Generic challenge form (some sites use custom challenges)
        if page.query_selector('form[id*="challenge"]') or page.query_selector('form[class*="challenge"]'):
            return 'generic-challenge'

        # "Verify you are human" text
        try:
            if page.locator('text=/verify.*human/i').first.is_visible():
                return 'generic-verification'
        except Exception:
            pass

        # No captcha detected
        return None
    
    def cleanup(self):
        """
        Clean up all browser resources.
        Closes all contexts, browsers, and stops Playwright.
        """
        logger.info("Cleaning up voter resources")
        self.browser_manager.cleanup_all()
        logger.info("Voter cleanup complete")
