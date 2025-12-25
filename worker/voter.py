"""
Voter class that handles the actual voting operations using Playwright.
"""
import logging
import asyncio
import time
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

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
        Execute voting for a project.
        Returns a dict with 'success' boolean and optional 'error' message.
        """
        try:
            self._ensure_browser()
            
            rating = project.get('rating')
            
            # For now, we'll implement a basic voting mechanism
            # The actual implementation would need to parse the JavaScript voting scripts
            # and convert them to Python/Playwright equivalents
            
            logger.info(f"Attempting to vote for {rating} project")
            
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
                
                # Try to find and click the vote button
                # This is a simplified version - each site has different selectors
                success = self._attempt_vote(page, project)
                
                if success:
                    logger.info(f"Successfully voted for {rating}")
                    return {'success': True}
                else:
                    return {'success': False, 'error': 'Could not find vote button or already voted'}
                    
            except PlaywrightTimeout:
                logger.error(f"Timeout while voting for {rating}")
                return {'success': False, 'error': 'Page timeout'}
            except Exception as e:
                logger.error(f"Error during voting: {e}", exc_info=True)
                return {'success': False, 'error': str(e)}
            finally:
                page.close()
                context.close()
                
        except Exception as e:
            logger.error(f"Error in vote method: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _get_vote_url(self, project: Dict) -> Optional[str]:
        """Get the voting URL for a project"""
        rating = project.get('rating')
        project_id = project.get('id')
        
        # Load project definitions from projects.js equivalent
        # For now, we'll construct URLs based on common patterns
        
        url_patterns = {
            'topcraft.club': f'https://topcraft.club/servers/{project_id}/vote/',
            'mctop.su': f'https://mctop.su/servers/{project_id}/vote/',
            'mcrate.su': f'http://mcrate.su/rate/{project_id}',
            'minecraftservers.org': f'https://minecraftservers.org/vote/{project_id}',
            'planetminecraft.com': f'https://www.planetminecraft.com/server/{project_id}/',
            'topg.org': f'https://topg.org/minecraft/vote/{project_id}',
        }
        
        # Use custom URL if provided
        if project.get('responseURL'):
            return project['responseURL']
        
        # Use pattern if available
        if rating in url_patterns:
            return url_patterns[rating]
        
        # Fallback: try to construct from available data
        return None
    
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
