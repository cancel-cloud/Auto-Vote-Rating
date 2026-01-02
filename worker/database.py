"""
Database management for Auto-Vote-Rating.
Provides persistence for projects, settings, statistics, runtime status and debug logs.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from statuses import ProjectStatus

logger = logging.getLogger(__name__)

MAX_TIMELINE_EVENTS = 20
LOG_FILE_NAME = "debug.log.jsonl"
MAX_LOG_LINES = 1000
META_FILE = "storage-meta.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _to_iso_timestamp(value: Any) -> Optional[str]:
    """Normalize various timestamp formats into ISO-8601 UTC strings."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        # Accept both seconds + milliseconds.
        seconds = float(value)
        if seconds > 1_000_000_000_000:
            seconds = seconds / 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return None


def _default_runtime() -> Dict[str, Any]:
    return {
        "status": ProjectStatus.IDLE.value,
        "lastAttemptAt": None,
        "lastSuccessAt": None,
        "nextAttemptAt": None,
        "queuedAt": None,
        "startedAt": None,
        "finishedAt": None,
        "lastResult": {
            "ok": None,
            "reason": None,
            "httpStatus": None,
            "message": None,
        },
        "attemptsToday": 0,
        "attemptsDate": None,
        "retriesRemaining": None,
        "queuedBy": None,
        "timeline": [],
        "manualTrigger": False,
        "lastAction": None,
        "needsActionUntil": None,
    }


class Database:
    """Simple JSON-based persistence helper."""

    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.projects_file = self.data_dir / "projects.json"
        self.settings_file = self.data_dir / "settings.json"
        self.stats_file = self.data_dir / "stats.json"
        self.meta_file = self.data_dir / META_FILE
        self.log_file = self.data_dir / LOG_FILE_NAME

        self._projects: Dict[str, Dict[str, Any]] = {}
        self._settings: Dict[str, Any] = {}
        self._stats: Dict[str, Any] = {}
        self._meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Initialization + loading
    # ------------------------------------------------------------------
    def initialize(self):
        """Load persisted data and ensure defaults."""
        self._load_meta()
        self._load_projects()
        self._load_settings()
        self._load_stats()
        self._ensure_project_schema()

        if not self._settings:
            self._settings = self._default_settings()
            self._save_settings()

        if not self._stats:
            self._stats = self._default_stats()
            self._save_stats()

    def _load_projects(self):
        if self.projects_file.exists():
            try:
                with open(self.projects_file, "r", encoding="utf-8") as f:
                    self._projects = json.load(f)
                logger.info("Loaded %d projects from %s", len(self._projects), self.projects_file)
            except Exception as exc:
                logger.error("Error loading projects: %s", exc)
                self._projects = {}
        else:
            self._projects = {}

    def _load_settings(self):
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                logger.info("Loaded settings from %s", self.settings_file)
            except Exception as exc:
                logger.error("Error loading settings: %s", exc)
                self._settings = {}
        else:
            self._settings = {}

    def _load_stats(self):
        if self.stats_file.exists():
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    self._stats = json.load(f)
                logger.info("Loaded statistics from %s", self.stats_file)
            except Exception as exc:
                logger.error("Error loading statistics: %s", exc)
                self._stats = {}
        else:
            self._stats = {}

    def _load_meta(self):
        if self.meta_file.exists():
            try:
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    self._meta = json.load(f)
            except Exception:
                self._meta = {}
        else:
            self._meta = {}

    def _save_projects(self):
        with open(self.projects_file, "w", encoding="utf-8") as f:
            json.dump(self._projects, f, indent=2)
        self._meta["lastUpdatedAt"] = _iso_now()
        self._meta["projectsCount"] = len(self._projects)
        self._save_meta()

    def _save_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=2)

    def _save_stats(self):
        with open(self.stats_file, "w", encoding="utf-8") as f:
            json.dump(self._stats, f, indent=2)

    def _save_meta(self):
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, indent=2)

    def _default_settings(self) -> Dict[str, Any]:
        return {
            "disabledNotifStart": False,
            "disabledNotifInfo": False,
            "disabledNotifWarn": False,
            "disabledNotifError": False,
            "disabledCheckInternet": False,
            "disabledOneVote": False,
            "disabledRestartOnTimeout": False,
            "disabledFocusedTab": True,
            "disabledWarnCaptcha": False,
            "disabledClickCaptcha": False,
            "disableCloseTabsOnSuccess": False,
            "disableCloseTabsOnError": False,
            "timeout": 5000,
            "timeoutError": 900000,
            "timeoutVote": 900000,
            "debug": False,
            # Scheduling + retry defaults
            "dailyWindowStart": "09:00",
            "dailyWindowEnd": "21:00",
            "jitterMinutes": 25,
            "retryPolicy": {
                "maxRetriesPerDay": 3,
                "retryBackoffMinutes": 45,
                "retryJitterMinutes": 10,
                "retryWindowEnd": "23:00",
            },
        }

    def _default_stats(self) -> Dict[str, Any]:
        return {
            "generalStats": {
                "successVotes": 0,
                "errorVotes": 0,
                "laterVotes": 0,
                "monthSuccessVotes": 0,
                "lastMonthSuccessVotes": 0,
                "lastSuccessVote": None,
                "lastAttemptVote": None,
            },
            "todayStats": {
                "successVotes": 0,
                "errorVotes": 0,
                "laterVotes": 0,
                "lastSuccessVote": None,
                "lastAttemptVote": None,
            },
        }

    def _ensure_project_schema(self):
        """Make sure each project contains the new runtime + stats structure."""
        updated = False
        for key, project in list(self._projects.items()):
            normalized, changed = self._normalize_project(project)
            if changed:
                self._projects[key] = normalized
                updated = True
        if updated:
            self._save_projects()

    def _normalize_project(self, project: Dict[str, Any]) -> (Dict[str, Any], bool):
        changed = False
        if not project.get("key"):
            # Assign key based on dict index to keep compatibility.
            project["key"] = str(len(self._projects))
            changed = True

        # Stats defaults
        if "stats" not in project or not isinstance(project["stats"], dict):
            project["stats"] = self._default_stats()["generalStats"].copy()
            changed = True

        runtime = project.get("runtime")
        if not isinstance(runtime, dict):
            runtime = _default_runtime()
            project["runtime"] = runtime
            changed = True

        else:
            defaults = _default_runtime()
            for field, value in defaults.items():
                if field not in runtime:
                    runtime[field] = deepcopy(value)
                    changed = True

        # Normalize timestamps
        for field in (
            "lastAttemptAt",
            "lastSuccessAt",
            "nextAttemptAt",
            "queuedAt",
            "startedAt",
            "finishedAt",
            "needsActionUntil",
        ):
            normalized = _to_iso_timestamp(runtime.get(field) or project.get(field))
            runtime[field] = normalized

        legacy_last_attempt = project.get("stats", {}).get("lastAttemptVote")
        if legacy_last_attempt and not runtime.get("lastAttemptAt"):
            runtime["lastAttemptAt"] = _to_iso_timestamp(legacy_last_attempt)

        legacy_last_success = project.get("stats", {}).get("lastSuccessVote")
        if legacy_last_success and not runtime.get("lastSuccessAt"):
            runtime["lastSuccessAt"] = _to_iso_timestamp(legacy_last_success)

        if project.get("time") and not runtime.get("nextAttemptAt"):
            runtime["nextAttemptAt"] = _to_iso_timestamp(project["time"])

        timeline = runtime.get("timeline") or []
        if len(timeline) > MAX_TIMELINE_EVENTS:
            runtime["timeline"] = timeline[-MAX_TIMELINE_EVENTS:]
            changed = True

        return project, changed

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------
    def _reload_projects(self):
        self._load_projects()
        self._ensure_project_schema()

    def get_all_projects(self) -> List[Dict[str, Any]]:
        self._reload_projects()
        return list(self._projects.values())

    def get_project(self, key: str) -> Optional[Dict[str, Any]]:
        self._reload_projects()
        return self._projects.get(key)

    def add_project(self, project: Dict[str, Any]) -> str:
        self._reload_projects()
        key = str(len(self._projects))
        while key in self._projects:
            key = str(int(key) + 1)
        project["key"] = key

        stats = project.get("stats") or {}
        if not stats:
            stats = {
                "successVotes": 0,
                "errorVotes": 0,
                "laterVotes": 0,
                "monthSuccessVotes": 0,
                "lastMonthSuccessVotes": 0,
                "lastSuccessVote": None,
                "lastAttemptVote": None,
                "added": int(_utc_now().timestamp() * 1000),
            }
        project["stats"] = stats
        project["runtime"] = _default_runtime()

        self._projects[key] = project
        self._save_projects()
        logger.info("Added project with key %s", key)
        return key

    def update_project(self, project: Dict[str, Any]):
        key = project.get("key")
        if not key:
            logger.warning("Attempted to update project without key")
            return
        self._reload_projects()
        self._projects[key] = project
        self._save_projects()

    def patch_project_fields(self, key: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._reload_projects()
        project = self._projects.get(key)
        if not project:
            return None
        project.update(updates)
        self._projects[key] = project
        self._save_projects()
        return project

    def delete_project(self, key: str):
        self._reload_projects()
        if key in self._projects:
            del self._projects[key]
            self._save_projects()
            logger.info("Deleted project %s", key)

    # ------------------------------------------------------------------
    # Runtime helpers
    # ------------------------------------------------------------------
    def queue_vote_now(self, key: str, source: str = "user") -> Optional[Dict[str, Any]]:
        project = self.get_project(key)
        if not project:
            return None
        runtime = project.get("runtime") or _default_runtime()
        runtime["status"] = ProjectStatus.QUEUED.value
        runtime["queuedAt"] = _iso_now()
        runtime["nextAttemptAt"] = runtime["queuedAt"]
        runtime["queuedBy"] = source
        runtime["manualTrigger"] = True
        runtime["lastAction"] = "Vote queued by {}".format(source)
        project["time"] = None
        self.append_project_event(project, "QUEUED", "Vote queued via dashboard")
        self._projects[key] = project
        self._save_projects()
        self.append_log(
            {
                "event": "project.queued",
                "projectKey": key,
                "projectName": project.get("name") or project.get("id"),
                "source": source,
            }
        )
        return project

    def append_project_event(
        self,
        project: Dict[str, Any],
        event_type: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        runtime = project.setdefault("runtime", _default_runtime())
        timeline = runtime.get("timeline") or []
        entry = {"timestamp": _iso_now(), "type": event_type}
        if message:
            entry["message"] = message
        if data:
            entry["data"] = data
        timeline.append(entry)
        runtime["timeline"] = timeline[-MAX_TIMELINE_EVENTS:]

    def mark_worker_tick(self):
        self._meta["lastWorkerTickAt"] = _iso_now()
        self._save_meta()

    def get_storage_health(self) -> Dict[str, Any]:
        self._reload_projects()
        return {
            "dataDir": str(self.data_dir),
            "projectsCount": len(self._projects),
            "lastUpdatedAt": self._meta.get("lastUpdatedAt"),
            "lastWorkerTickAt": self._meta.get("lastWorkerTickAt"),
        }

    # ------------------------------------------------------------------
    # Settings + stats
    # ------------------------------------------------------------------
    def get_settings(self) -> Dict[str, Any]:
        self._load_settings()
        return deepcopy(self._settings)

    def update_settings(self, settings: Dict[str, Any]):
        self._load_settings()
        retry_policy = settings.pop("retryPolicy", None)
        if retry_policy:
            current_policy = self._settings.get("retryPolicy", {})
            current_policy.update(retry_policy)
            self._settings["retryPolicy"] = current_policy
        self._settings.update(settings)
        self._save_settings()
        logger.info("Updated settings")

    def get_stats(self) -> Dict[str, Any]:
        self._load_stats()
        return deepcopy(self._stats)

    def update_stats(self, stats: Dict[str, Any]):
        self._load_stats()
        self._stats.update(stats)
        self._save_stats()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def append_log(self, entry: Dict[str, Any]):
        enriched = {"timestamp": _iso_now(), **entry}
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(enriched))
            f.write("\n")
        self._trim_logs()

    def _trim_logs(self):
        if not self.log_file.exists():
            return
        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= MAX_LOG_LINES:
            return
        trimmed = lines[-MAX_LOG_LINES:]
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.writelines(trimmed)

    def get_logs(self, limit: int = 200, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.log_file.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entries.append(payload)
        if project_key:
            entries = [e for e in entries if e.get("projectKey") == project_key]
        return list(reversed(entries[-limit:]))
