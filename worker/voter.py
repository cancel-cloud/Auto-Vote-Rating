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
        rating = project.get('rating')
        project_id = project.get('id')
        
        # Comprehensive URL patterns for all supported voting sites
        url_patterns = {
            'minecraft-server.eu': f'https://minecraft-server.eu/vote/index/{project_id}',
            'minecraft-serverlist.net': f'https://www.minecraft-serverlist.net/vote/{project_id}',
            'topcraft.club': f'https://topcraft.club/servers/{project_id}/vote/',
            'mctop.su': f'https://mctop.su/servers/{project_id}/vote/',
            'mcrate.su': f'http://mcrate.su/rate/{project_id}',
            'minecraftrating.ru': f'https://minecraftrating.ru/projects/{project_id}/',
            'monitoringminecraft.ru': f'https://monitoringminecraft.ru/top/{project_id}/vote',
            'ionmc.top': f'https://ionmc.top/projects/{project_id}/vote',
            'minecraftservers.org': f'https://minecraftservers.org/vote/{project_id}',
            'serveur-prive.net': f'https://serveur-prive.net/minecraft/{project_id}/vote',
            'planetminecraft.com': f'https://www.planetminecraft.com/server/{project_id}/',
            'topg.org': f'https://topg.org/minecraft/vote/{project_id}',
            'minecraft-mp.com': f'https://minecraft-mp.com/vote/{project_id}',
            'minecraft-server-list.com': f'https://minecraft-server-list.com/vote/{project_id}',
            'serverpact.com': f'https://serverpact.com/server/{project_id}',
            'minecraftiplist.com': f'https://minecraftiplist.com/server/{project_id}',
            'topminecraftservers.org': f'https://topminecraftservers.org/vote/{project_id}',
            'minecraftservers.biz': f'https://minecraftservers.biz/vote/{project_id}',
            'hotmc.ru': f'https://hotmc.ru/server/{project_id}',
            'minecraft-server.net': f'https://minecraft-server.net/vote/{project_id}',
            'top-games.net': f'https://top-games.net/minecraft/{project_id}',
            'tmonitoring.com': f'https://tmonitoring.com/server/{project_id}',
            'top.gg': f'https://top.gg/bot/{project_id}',
            'discordbotlist.com': f'https://discordbotlist.com/bots/{project_id}',
            'discords.com': f'https://discords.com/bots/{project_id}',
            'mmotop.ru': f'https://mmotop.ru/server/{project_id}',
            'mc-servers.com': f'https://mc-servers.com/vote/{project_id}',
            'minecraftlist.org': f'https://minecraftlist.org/vote/{project_id}',
            'minecraft-index.com': f'https://minecraft-index.com/vote/{project_id}',
            'serverlist101.com': f'https://serverlist101.com/server/{project_id}',
            'mcserver-list.eu': f'https://mcserver-list.eu/server/{project_id}',
            'craftlist.org': f'https://craftlist.org/server/{project_id}',
            'czech-craft.eu': f'https://czech-craft.eu/server/{project_id}',
            'minecraft.buzz': f'https://minecraft.buzz/server/{project_id}',
            'minecraftservery.eu': f'https://minecraftservery.eu/server/{project_id}',
            'rpg-paradize.com': f'https://rpg-paradize.com/server/{project_id}',
            'minecraftkrant.nl': f'https://minecraftkrant.nl/server/{project_id}',
            'trackyserver.com': f'https://trackyserver.com/server/{project_id}',
            'mc-lists.org': f'https://mc-lists.org/server/{project_id}',
            'topmcservers.com': f'https://topmcservers.com/server/{project_id}',
            'bestservers.com': f'https://bestservers.com/server/{project_id}',
            'craft-list.net': f'https://craft-list.net/server/{project_id}',
            'minecraft-servers-list.org': f'https://minecraft-servers-list.org/server/{project_id}',
            'serverliste.net': f'https://serverliste.net/server/{project_id}',
            'gtop100.com': f'https://gtop100.com/server/{project_id}',
            'wargm.ru': f'https://wargm.ru/server/{project_id}',
            'minestatus.net': f'https://minestatus.net/server/{project_id}',
            'misterlauncher.org': f'https://misterlauncher.org/server/{project_id}',
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
