"""
Voter class that handles the actual voting operations using Playwright.
"""
import logging
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from sites import build_vote_url

logger = logging.getLogger(__name__)


class Voter:
    """Handles voting operations using browser automation"""
    
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.playwright = None
        self.browser = None
        
    def _ensure_browser(self):
        """Ensure browser is running"""
        if not self.playwright:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.config.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            logger.info("Browser launched")
    
    def vote(self, project: Dict) -> Dict:
        """
        Execute voting for a project - REMINDER MODE.
        Opens the vote page and notifies user to complete manually.
        NO AUTOMATIC FORM SUBMISSION OR CLICKING.
        Returns a dict with 'success' boolean and optional 'error' message.
        """
        try:
            self._ensure_browser()
            
            rating = project.get('rating')
            
            logger.info(f"Opening vote page for {rating} project (REMINDER MODE - user action required)")
            
            # Create a new page
            context = self.browser.new_context()
            page = context.new_page()
            
            try:
                # Get the vote URL from project
                vote_url = self._get_vote_url(project)
                
                if not vote_url:
                    return {'success': False, 'error': 'Could not determine vote URL'}
                
                logger.info(f"Navigating to {vote_url}")
                
                # Navigate to vote page
                page.goto(vote_url, wait_until='networkidle', timeout=self.config.browser_timeout)
                
                # Wait a bit for the page to load
                page.wait_for_timeout(2000)
                
                # Log that page was opened successfully
                logger.info(f"✓ Vote page opened for {rating} - USER MUST COMPLETE VOTE MANUALLY")
                
                # Keep page open for a while so user can see it
                page.wait_for_timeout(5000)
                
                # Return success - page was opened
                return {
                    'success': True,
                    'message': 'Vote page opened - please complete vote manually'
                }
                    
            except PlaywrightTimeout:
                logger.error(f"Timeout while opening vote page for {rating}")
                return {'success': False, 'error': 'Page timeout'}
            except Exception as e:
                logger.error(f"Error during page opening: {e}", exc_info=True)
                return {'success': False, 'error': str(e)}
            finally:
                page.close()
                context.close()
                
        except Exception as e:
            logger.error(f"Error in vote method: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
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
    
    def _attempt_vote(self, page: Page, project: Dict) -> bool:
        """
        Attempt to click the vote button on the page.
        This is a simplified version that looks for common vote button patterns.
        """
        rating = project.get('rating')
        
        # Common vote button selectors
        vote_selectors = [
            'button:has-text("Vote")',
            'button:has-text("vote")',
            'a:has-text("Vote")',
            'input[type="submit"][value*="vote" i]',
            'button.vote-button',
            'a.vote-btn',
            '#vote-button',
            '.vote-btn',
        ]
        
        # Try each selector
        for selector in vote_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"Found vote button with selector: {selector}")
                    element.click()
                    page.wait_for_timeout(2000)  # Wait for action to complete
                    
                    # Check if we need to handle captcha
                    if self._has_captcha(page):
                        logger.warning("Captcha detected - manual intervention required")
                        return False
                    
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        logger.warning("Could not find vote button on page")
        return False
    
    def _has_captcha(self, page: Page) -> bool:
        """Check if page has a captcha"""
        captcha_indicators = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            '.g-recaptcha',
            '.h-captcha',
        ]
        
        for indicator in captcha_indicators:
            if page.query_selector(indicator):
                return True
        
        return False
    
    def cleanup(self):
        """Clean up browser resources"""
        if self.browser:
            self.browser.close()
            logger.info("Browser closed")
        if self.playwright:
            self.playwright.stop()
            logger.info("Playwright stopped")
