"""
Database management for Auto-Vote-Rating.
Provides persistence for projects, settings, and statistics.
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """Simple JSON-based database for storing projects and settings"""
    
    def __init__(self, data_dir: str = '/app/data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.projects_file = self.data_dir / 'projects.json'
        self.settings_file = self.data_dir / 'settings.json'
        self.stats_file = self.data_dir / 'stats.json'
        
        self._projects = {}
        self._settings = {}
        self._stats = {}
        
    def initialize(self):
        """Initialize database with default values if needed"""
        # Load existing data
        self._load_projects()
        self._load_settings()
        self._load_stats()
        
        # Initialize default settings if empty
        if not self._settings:
            self._settings = {
                'disabledNotifStart': False,
                'disabledNotifInfo': False,
                'disabledNotifWarn': False,
                'disabledNotifError': False,
                'disabledCheckInternet': False,
                'disabledOneVote': False,
                'disabledRestartOnTimeout': False,
                'disabledFocusedTab': True,
                'disabledWarnCaptcha': False,
                'disabledClickCaptcha': False,
                'disableCloseTabsOnSuccess': False,
                'disableCloseTabsOnError': False,
                'timeout': 5000,
                'timeoutError': 900000,
                'timeoutVote': 900000,
                'debug': False,
                # New scheduling settings
                'earliestTime': '09:00',
                'latestTime': '21:00',
                'retryEnabled': True,
                'maxRetriesPerDay': 3,
                'retryMinDelayMinutes': 30,
                'retryMaxDelayMinutes': 180
            }
            self._save_settings()
        
        # Initialize default stats if empty
        if not self._stats:
            self._stats = {
                'generalStats': {
                    'successVotes': 0,
                    'errorVotes': 0,
                    'laterVotes': 0,
                    'monthSuccessVotes': 0,
                    'lastMonthSuccessVotes': 0,
                    'lastSuccessVote': None,
                    'lastAttemptVote': None
                },
                'todayStats': {
                    'successVotes': 0,
                    'errorVotes': 0,
                    'laterVotes': 0,
                    'lastSuccessVote': None,
                    'lastAttemptVote': None
                }
            }
            self._save_stats()
    
    def _load_projects(self):
        """Load projects from disk"""
        if self.projects_file.exists():
            try:
                with open(self.projects_file, 'r') as f:
                    self._projects = json.load(f)
                logger.info(f"Loaded {len(self._projects)} projects from {self.projects_file}")
            except Exception as e:
                logger.error(f"Error loading projects: {e}")
                self._projects = {}
        else:
            self._projects = {}
    
    def _save_projects(self):
        """Save projects to disk"""
        try:
            with open(self.projects_file, 'w') as f:
                json.dump(self._projects, f, indent=2)
            logger.debug(f"Saved {len(self._projects)} projects to {self.projects_file}")
        except Exception as e:
            logger.error(f"Error saving projects: {e}")
    
    def _load_settings(self):
        """Load settings from disk"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    self._settings = json.load(f)
                logger.info(f"Loaded settings from {self.settings_file}")
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                self._settings = {}
        else:
            self._settings = {}
    
    def _save_settings(self):
        """Save settings to disk"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self._settings, f, indent=2)
            logger.debug(f"Saved settings to {self.settings_file}")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    def _load_stats(self):
        """Load statistics from disk"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    self._stats = json.load(f)
                logger.info(f"Loaded statistics from {self.stats_file}")
            except Exception as e:
                logger.error(f"Error loading statistics: {e}")
                self._stats = {}
        else:
            self._stats = {}
    
    def _save_stats(self):
        """Save statistics to disk"""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self._stats, f, indent=2)
            logger.debug(f"Saved statistics to {self.stats_file}")
        except Exception as e:
            logger.error(f"Error saving statistics: {e}")
    
    # Project operations
    def get_all_projects(self) -> List[Dict]:
        """Get all projects"""
        return list(self._projects.values())
    
    def get_project(self, key: str) -> Optional[Dict]:
        """Get a specific project by key"""
        return self._projects.get(key)
    
    def add_project(self, project: Dict) -> str:
        """Add a new project"""
        # Generate a unique key
        key = str(len(self._projects))
        while key in self._projects:
            key = str(int(key) + 1)
        
        project['key'] = key
        
        # Initialize stats if not present
        if 'stats' not in project:
            project['stats'] = {
                'successVotes': 0,
                'errorVotes': 0,
                'laterVotes': 0,
                'monthSuccessVotes': 0,
                'lastMonthSuccessVotes': 0,
                'lastSuccessVote': None,
                'lastAttemptVote': None,
                'added': int(datetime.now().timestamp() * 1000)
            }
        
        # Initialize retry tracking fields
        if 'lastAttemptAt' not in project:
            project['lastAttemptAt'] = None
        if 'lastSuccessAt' not in project:
            project['lastSuccessAt'] = None
        if 'nextAttemptAt' not in project:
            project['nextAttemptAt'] = None
        if 'retriesTodayCount' not in project:
            project['retriesTodayCount'] = 0
        if 'lastError' not in project:
            project['lastError'] = None
        
        self._projects[key] = project
        self._save_projects()
        logger.info(f"Added project with key {key}")
        return key
    
    def update_project(self, project: Dict):
        """Update an existing project"""
        key = project.get('key')
        if key in self._projects:
            self._projects[key] = project
            self._save_projects()
            logger.debug(f"Updated project {key}")
        else:
            logger.warning(f"Attempted to update non-existent project {key}")
    
    def delete_project(self, key: str):
        """Delete a project"""
        if key in self._projects:
            del self._projects[key]
            self._save_projects()
            logger.info(f"Deleted project {key}")
        else:
            logger.warning(f"Attempted to delete non-existent project {key}")
    
    # Settings operations
    def get_settings(self) -> Dict:
        """Get all settings"""
        return self._settings.copy()
    
    def update_settings(self, settings: Dict):
        """Update settings"""
        self._settings.update(settings)
        self._save_settings()
        logger.info("Updated settings")
    
    # Statistics operations
    def get_stats(self) -> Dict:
        """Get all statistics"""
        return self._stats.copy()
    
    def update_stats(self, stats: Dict):
        """Update statistics"""
        self._stats.update(stats)
        self._save_stats()
        logger.debug("Updated statistics")
