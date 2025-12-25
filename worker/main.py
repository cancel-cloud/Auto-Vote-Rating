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
    
    def vote_for_project(self, project: Dict):
        """Execute voting for a specific project"""
        try:
            # Update last attempt time
            project['stats'] = project.get('stats', {})
            project['stats']['lastAttemptVote'] = int(datetime.now().timestamp() * 1000)
            self.db.update_project(project)
            
            # Execute the vote
            result = self.voter.vote(project)
            
            # Update project based on result
            if result['success']:
                logger.info(f"Successfully voted for {self.get_project_prefix(project)}")
                
                # Update statistics
                project['stats']['successVotes'] = project['stats'].get('successVotes', 0) + 1
                project['stats']['monthSuccessVotes'] = project['stats'].get('monthSuccessVotes', 0) + 1
                project['stats']['lastSuccessVote'] = int(datetime.now().timestamp() * 1000)
                
                # Calculate next vote time (default: 24 hours)
                next_vote = datetime.now() + timedelta(hours=24)
                project['time'] = int(next_vote.timestamp() * 1000)
                
                # Clear any errors
                if 'error' in project:
                    del project['error']
                    
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to vote for {self.get_project_prefix(project)}: {error_msg}")
                
                # Update statistics
                project['stats']['errorVotes'] = project['stats'].get('errorVotes', 0) + 1
                project['error'] = error_msg
                
                # Retry after configured timeout (default: 15 minutes)
                settings = self.db.get_settings()
                retry_timeout = settings.get('timeoutError', 900000)  # 15 minutes in ms
                next_vote = datetime.now() + timedelta(milliseconds=retry_timeout)
                project['time'] = int(next_vote.timestamp() * 1000)
            
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
