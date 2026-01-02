"""
Main worker script for Auto-Vote-Rating Docker container.
This replaces the browser extension background.js functionality.
"""
import os
import sys
import time
import json
import logging
import schedule
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import threading

from database import Database
from voter import Voter
from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/data/worker.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class VoteWorker:
    """Main worker class that manages voting operations"""
    
    def __init__(self):
        self.config = Config()
        self.db = Database(self.config.data_dir)
        self.voter = Voter(self.db, self.config)
        self.scheduler = BackgroundScheduler()
        self.running = False
        
    def start(self):
        """Start the worker"""
        logger.info("Starting Auto-Vote-Rating Worker")
        self.running = True
        
        # Initialize database
        self.db.initialize()
        
        # Load projects and settings
        projects = self.db.get_all_projects()
        logger.info(f"Loaded {len(projects)} projects from database")
        
        # Schedule voting checks every minute
        self.scheduler.add_job(
            self.check_and_vote,
            'interval',
            minutes=1,
            id='vote_checker'
        )
        
        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # Run initial check
        self.check_and_vote()
        
        # Keep the worker running
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            self.stop()
    
    def check_and_vote(self):
        """Check all projects and vote if needed"""
        try:
            projects = self.db.get_all_projects()
            current_time = datetime.now()
            
            # Reset daily retry counters at midnight
            for project in projects:
                if project.get('lastAttemptAt'):
                    last_attempt = datetime.fromtimestamp(project['lastAttemptAt'] / 1000)
                    if last_attempt.date() < current_time.date():
                        project['retriesTodayCount'] = 0
                        self.db.update_project(project)
            
            for project in projects:
                # Skip if voting is disabled
                if project.get('disabled', False):
                    continue
                
                # Check if it's time to vote
                next_vote_time = project.get('time')
                if next_vote_time:
                    next_vote_dt = datetime.fromtimestamp(next_vote_time / 1000)
                    if current_time >= next_vote_dt:
                        logger.info(f"Time to vote for project: {self.get_project_prefix(project)}")
                        self.vote_for_project(project)
                elif not next_vote_time:
                    # First time voting
                    logger.info(f"First time voting for project: {self.get_project_prefix(project)}")
                    self.vote_for_project(project)
                    
        except Exception as e:
            logger.error(f"Error in check_and_vote: {e}", exc_info=True)
    
    def calculate_next_vote_time(self, project: Dict, is_retry: bool = False) -> datetime:
        """Calculate next vote time with flexible scheduling and jitter"""
        settings = self.db.get_settings()
        
        if is_retry and settings.get('retryEnabled', True):
            # Same-day retry with exponential backoff
            retry_count = project.get('retriesTodayCount', 0)
            max_retries = settings.get('maxRetriesPerDay', 3)
            
            if retry_count < max_retries:
                # Exponential backoff: 30min, 1hr, 2hr, etc.
                min_delay = settings.get('retryMinDelayMinutes', 30)
                max_delay = settings.get('retryMaxDelayMinutes', 180)
                
                # Calculate exponential delay
                delay_minutes = min(min_delay * (2 ** retry_count), max_delay)
                
                # Add jitter (±20%)
                import random
                jitter = random.uniform(0.8, 1.2)
                delay_minutes = int(delay_minutes * jitter)
                
                next_time = datetime.now() + timedelta(minutes=delay_minutes)
                
                # Check if still within daily window
                earliest = settings.get('earliestTime', '09:00')
                latest = settings.get('latestTime', '21:00')
                
                earliest_hour, earliest_min = map(int, earliest.split(':'))
                latest_hour, latest_min = map(int, latest.split(':'))
                
                window_end = datetime.now().replace(hour=latest_hour, minute=latest_min, second=0, microsecond=0)
                
                if next_time < window_end:
                    return next_time
        
        # Next day scheduling with random time in window
        import random
        settings = self.db.get_settings()
        
        earliest = settings.get('earliestTime', '09:00')
        latest = settings.get('latestTime', '21:00')
        
        earliest_hour, earliest_min = map(int, earliest.split(':'))
        latest_hour, latest_min = map(int, latest.split(':'))
        
        # Calculate next day
        next_day = datetime.now() + timedelta(days=1)
        
        # Random hour and minute within window
        hour_range = latest_hour - earliest_hour
        random_hour = earliest_hour + random.randint(0, hour_range)
        random_minute = random.randint(0, 59)
        
        # Add jitter (±10 minutes)
        jitter_minutes = random.randint(-10, 10)
        
        next_time = next_day.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
        next_time += timedelta(minutes=jitter_minutes)
        
        # Ensure it's within the window
        earliest_time = next_day.replace(hour=earliest_hour, minute=earliest_min, second=0, microsecond=0)
        latest_time = next_day.replace(hour=latest_hour, minute=latest_min, second=0, microsecond=0)
        
        next_time = max(earliest_time, min(next_time, latest_time))
        
        return next_time
    
    def vote_for_project(self, project: Dict):
        """Execute voting for a specific project - REMINDER MODE (no auto-submission)"""
        try:
            # Update last attempt time
            project['stats'] = project.get('stats', {})
            project['stats']['lastAttemptVote'] = int(datetime.now().timestamp() * 1000)
            project['lastAttemptAt'] = int(datetime.now().timestamp() * 1000)
            self.db.update_project(project)
            
            # Execute the vote (opens page and notifies user - NO AUTO-SUBMISSION)
            result = self.voter.vote(project)
            
            # Update project based on result
            if result['success']:
                logger.info(f"Vote page opened for {self.get_project_prefix(project)} - User action required")
                
                # Update statistics
                project['stats']['successVotes'] = project['stats'].get('successVotes', 0) + 1
                project['stats']['monthSuccessVotes'] = project['stats'].get('monthSuccessVotes', 0) + 1
                project['stats']['lastSuccessVote'] = int(datetime.now().timestamp() * 1000)
                project['lastSuccessAt'] = int(datetime.now().timestamp() * 1000)
                
                # Reset retry counter on success
                project['retriesTodayCount'] = 0
                
                # Calculate next vote time for next day
                next_vote = self.calculate_next_vote_time(project, is_retry=False)
                project['time'] = int(next_vote.timestamp() * 1000)
                project['nextAttemptAt'] = int(next_vote.timestamp() * 1000)
                
                # Clear any errors
                if 'error' in project:
                    del project['error']
                    
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to open vote page for {self.get_project_prefix(project)}: {error_msg}")
                
                # Update statistics
                project['stats']['errorVotes'] = project['stats'].get('errorVotes', 0) + 1
                project['error'] = error_msg
                project['lastError'] = error_msg
                
                # Increment retry counter
                project['retriesTodayCount'] = project.get('retriesTodayCount', 0) + 1
                
                # Calculate next attempt time with retry logic
                next_vote = self.calculate_next_vote_time(project, is_retry=True)
                project['time'] = int(next_vote.timestamp() * 1000)
                project['nextAttemptAt'] = int(next_vote.timestamp() * 1000)
                
                logger.info(f"Retry {project['retriesTodayCount']} scheduled for {next_vote}")
            
            # Save updated project
            self.db.update_project(project)
            
        except Exception as e:
            logger.error(f"Error voting for project {self.get_project_prefix(project)}: {e}", exc_info=True)
            project['error'] = str(e)
            project['stats']['errorVotes'] = project['stats'].get('errorVotes', 0) + 1
            self.db.update_project(project)
    
    def get_project_prefix(self, project: Dict) -> str:
        """Generate a readable project identifier"""
        parts = [f"[{project.get('rating', 'unknown')}]"]
        if project.get('nick'):
            parts.append(project['nick'])
        if project.get('name'):
            parts.append(project['name'])
        elif project.get('id'):
            parts.append(project['id'])
        return ' - '.join(parts)
    
    def stop(self):
        """Stop the worker"""
        logger.info("Stopping Auto-Vote-Rating Worker")
        self.running = False
        self.scheduler.shutdown()
        self.voter.cleanup()
        logger.info("Worker stopped")


def main():
    """Main entry point"""
    worker = VoteWorker()
    worker.start()


if __name__ == '__main__':
    main()
