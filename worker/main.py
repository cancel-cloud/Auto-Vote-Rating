"""
Main worker script for Auto-Vote-Rating Docker container.
Handles scheduling, logging and vote reminder orchestration.
"""
from __future__ import annotations

import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo

from config import Config
from database import Database
from statuses import ProjectStatus
from voter import Voter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/app/data/worker.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

DUE_SOON_MINUTES = 10
NEEDS_ACTION_WINDOW_MINUTES = 15


def _dt_from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_from_dt(dt: datetime) -> str:
    ref = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return ref.astimezone(timezone.utc).isoformat()


def _ms_from_dt(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class VoteWorker:
    """Main worker class managing voting logic."""

    def __init__(
        self,
        config: Optional[Config] = None,
        db: Optional[Database] = None,
        voter: Optional[Voter] = None,
    ):
        self.config = config or Config()
        self.db = db or Database(self.config.data_dir)
        self.voter = voter or Voter(self.db, self.config)
        self.scheduler = BackgroundScheduler()
        self.running = False
        self.tz = ZoneInfo(self.config.timezone)

    def start(self):
        logger.info("Starting Auto-Vote-Rating Worker")
        self.running = True

        self.db.initialize()
        projects = self.db.get_all_projects()
        logger.info("Loaded %d projects from database", len(projects))

        self.scheduler.add_job(self.check_and_vote, "interval", minutes=1, id="vote_checker")
        self.scheduler.start()
        logger.info("Scheduler started")

        self.check_and_vote()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            self.stop()

    def stop(self):
        logger.info("Stopping Auto-Vote-Rating Worker")
        self.running = False
        self.scheduler.shutdown(wait=False)
        self.voter.cleanup()
        logger.info("Worker stopped")

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------
    def check_and_vote(self):
        """Run a worker tick."""
        try:
            projects = self.db.get_all_projects()
            settings = self.db.get_settings()
            now_utc = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(self.tz)

            self.db.mark_worker_tick()
            self.db.append_log({"event": "tick.start", "projectCount": len(projects)})

            for project in projects:
                try:
                    action = self._process_project(project, settings, now_utc, now_local)
                    self.db.append_log(
                        {
                            "event": "project.tick",
                            "projectKey": project["key"],
                            "projectName": project.get("name") or project.get("id"),
                            "status": project.get("runtime", {}).get("status"),
                            "nextAttemptAt": project.get("runtime", {}).get("nextAttemptAt"),
                            "action": action,
                        }
                    )
                    self.db.update_project(project)
                except Exception as exc:
                    logger.error("Error processing project %s: %s", project.get("key"), exc, exc_info=True)
                    self.db.append_log(
                        {
                            "event": "project.error",
                            "projectKey": project.get("key"),
                            "message": str(exc),
                        }
                    )

        except Exception as exc:
            logger.error("Error in check_and_vote: %s", exc, exc_info=True)
            self.db.append_log({"event": "tick.error", "message": str(exc)})

    def _process_project(
        self,
        project: Dict,
        settings: Dict,
        now_utc: datetime,
        now_local: datetime,
    ) -> str:
        project.setdefault("stats", {})
        runtime = project.setdefault("runtime", {})

        self._reset_daily_counters(runtime, settings, now_local)
        self._settle_needs_action(project, runtime, now_utc)

        next_attempt = _dt_from_iso(runtime.get("nextAttemptAt"))
        status = runtime.get("status")

        if status == ProjectStatus.QUEUED.value:
            self._start_vote(project, runtime, settings, now_utc, now_local, reason="manual queue")
            return "queued->in_progress"

        if next_attempt and now_utc >= next_attempt:
            self._start_vote(project, runtime, settings, now_utc, now_local, reason="scheduled")
            return "due->in_progress"

        if not next_attempt:
            scheduled = self._schedule_daily(project, runtime, settings, now_local, allow_today=True)
            return f"scheduled:{scheduled}"

        self._update_schedule_status(runtime, next_attempt, now_utc)
        return "waiting"

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------
    def _reset_daily_counters(self, runtime: Dict, settings: Dict, now_local: datetime):
        today_key = now_local.strftime("%Y-%m-%d")
        policy = settings.get("retryPolicy", {})
        max_retries = policy.get("maxRetriesPerDay", 3)
        if runtime.get("attemptsDate") != today_key:
            runtime["attemptsDate"] = today_key
            runtime["attemptsToday"] = 0
            runtime["retriesRemaining"] = max_retries

    def _settle_needs_action(self, project: Dict, runtime: Dict, now_utc: datetime):
        if runtime.get("status") != ProjectStatus.NEEDS_USER_ACTION.value:
            return
        expiry = _dt_from_iso(runtime.get("needsActionUntil"))
        if expiry and now_utc >= expiry:
            runtime["status"] = ProjectStatus.SUCCESS.value
            runtime["needsActionUntil"] = None
            runtime["lastAction"] = "Vote reminder completed"
            self.db.append_project_event(project, "SUCCESS", "Marked successful after reminder window")

    def _schedule_daily(
        self,
        project: Dict,
        runtime: Dict,
        settings: Dict,
        now_local: datetime,
        allow_today: bool,
    ) -> str:
        start_str = settings.get("dailyWindowStart", "09:00")
        end_str = settings.get("dailyWindowEnd", "21:00")
        jitter = int(settings.get("jitterMinutes", 20))

        target_local = self._pick_window_time(now_local, start_str, end_str, jitter, allow_today=allow_today)
        runtime["nextAttemptAt"] = _iso_from_dt(target_local.astimezone(timezone.utc))
        project["time"] = _ms_from_dt(target_local)
        self._update_schedule_status(runtime, target_local.astimezone(timezone.utc), datetime.now(timezone.utc))
        self.db.append_project_event(project, "SCHEDULED", f"Next attempt scheduled at {target_local.isoformat()}")
        return runtime["nextAttemptAt"]

    def _pick_window_time(
        self,
        now_local: datetime,
        start_str: str,
        end_str: str,
        jitter_minutes: int,
        allow_today: bool,
    ) -> datetime:
        start_hour, start_min = [int(x) for x in start_str.split(":")]
        end_hour, end_min = [int(x) for x in end_str.split(":")]

        base = now_local
        window_start = base.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
        window_end = base.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        if window_end <= window_start:
            window_end += timedelta(days=1)
        if not allow_today or now_local >= window_end:
            base = now_local + timedelta(days=1)
            window_start = base.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            window_end = base.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            if window_end <= window_start:
                window_end += timedelta(days=1)
        window_start = max(window_start, now_local) if allow_today else window_start
        delta_seconds = max(int((window_end - window_start).total_seconds()), 1)
        offset = random.randint(0, delta_seconds)
        candidate = window_start + timedelta(seconds=offset)
        if jitter_minutes:
            candidate += timedelta(minutes=random.randint(-jitter_minutes, jitter_minutes))
        if candidate < window_start:
            candidate = window_start
        if candidate > window_end:
            candidate = window_end
        return candidate

    def _schedule_retry(
        self,
        project: Dict,
        runtime: Dict,
        settings: Dict,
        now_local: datetime,
    ) -> Optional[datetime]:
        policy = settings.get("retryPolicy", {})
        retries_remaining = runtime.get("retriesRemaining")
        if retries_remaining is None:
            retries_remaining = policy.get("maxRetriesPerDay", 3)
        if retries_remaining <= 0:
            return None
        backoff = policy.get("retryBackoffMinutes", 30)
        jitter = policy.get("retryJitterMinutes", 10)
        attempt_index = runtime.get("attemptsToday", 1)
        delay_minutes = max(backoff * attempt_index, 5)
        if jitter:
            delay_minutes += random.randint(-jitter, jitter)
        delay_minutes = max(delay_minutes, 5)
        candidate = now_local + timedelta(minutes=delay_minutes)

        retry_end_str = policy.get("retryWindowEnd", settings.get("dailyWindowEnd", "23:00"))
        end_hour, end_min = [int(x) for x in retry_end_str.split(":")]
        retry_window_end = now_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        if candidate <= retry_window_end:
            runtime["retriesRemaining"] = max(retries_remaining - 1, 0)
            self.db.append_project_event(project, "RETRY_SCHEDULED", f"Retry at {candidate.isoformat()}")
            return candidate
        return None

    def _update_schedule_status(self, runtime: Dict, next_attempt: datetime, now_utc: datetime):
        if not next_attempt:
            runtime["status"] = ProjectStatus.IDLE.value
            return
        seconds_until = (next_attempt - now_utc).total_seconds()
        if seconds_until <= 0:
            runtime["status"] = ProjectStatus.QUEUED.value
        elif seconds_until <= DUE_SOON_MINUTES * 60:
            runtime["status"] = ProjectStatus.DUE_SOON.value
        else:
            runtime["status"] = ProjectStatus.SCHEDULED.value

    # ------------------------------------------------------------------
    # Voting flow
    # ------------------------------------------------------------------
    def _start_vote(
        self,
        project: Dict,
        runtime: Dict,
        settings: Dict,
        now_utc: datetime,
        now_local: datetime,
        reason: str,
    ):
        runtime["status"] = ProjectStatus.IN_PROGRESS.value
        runtime["queuedAt"] = None
        runtime["startedAt"] = _iso_from_dt(now_utc)
        runtime["lastAttemptAt"] = runtime["startedAt"]
        runtime["manualTrigger"] = False
        runtime["lastAction"] = f"Attempt started ({reason})"
        runtime["attemptsToday"] = runtime.get("attemptsToday", 0) + 1
        runtime["nextAttemptAt"] = None
        runtime["needsActionUntil"] = None
        project["stats"]["lastAttemptVote"] = _ms_from_dt(now_utc)
        self.db.append_project_event(project, "IN_PROGRESS", f"Vote attempt started ({reason})")
        self.db.update_project(project)

        result = self.voter.vote(project)
        self._complete_attempt(project, runtime, settings, now_utc, now_local, result)

    def _complete_attempt(
        self,
        project: Dict,
        runtime: Dict,
        settings: Dict,
        now_utc: datetime,
        now_local: datetime,
        result: Dict,
    ):
        runtime["finishedAt"] = _iso_from_dt(now_utc)
        policy = settings.get("retryPolicy", {})
        if result.get("success"):
            message = result.get("message") or "Vote page opened - complete manually"
            runtime["status"] = ProjectStatus.NEEDS_USER_ACTION.value
            runtime["lastAction"] = message
            runtime["lastResult"] = {
                "ok": True,
                "reason": None,
                "httpStatus": None,
                "message": message,
            }
            runtime["lastSuccessAt"] = _iso_from_dt(now_utc)
            runtime["needsActionUntil"] = _iso_from_dt(now_utc + timedelta(minutes=NEEDS_ACTION_WINDOW_MINUTES))
            runtime["retriesRemaining"] = policy.get("maxRetriesPerDay", 3)
            project["stats"]["successVotes"] = project["stats"].get("successVotes", 0) + 1
            project["stats"]["monthSuccessVotes"] = project["stats"].get("monthSuccessVotes", 0) + 1
            project["stats"]["lastSuccessVote"] = _ms_from_dt(now_utc)
            self.db.append_project_event(project, "NEEDS_USER_ACTION", message)
            self.db.append_log(
                {
                    "event": "project.result",
                    "projectKey": project["key"],
                    "result": "success",
                    "message": message,
                }
            )
            future = self._pick_window_time(
                now_local + timedelta(days=1),
                settings.get("dailyWindowStart", "09:00"),
                settings.get("dailyWindowEnd", "21:00"),
                int(settings.get("jitterMinutes", 20)),
                allow_today=False,
            )
            runtime["nextAttemptAt"] = _iso_from_dt(future.astimezone(timezone.utc))
            project["time"] = _ms_from_dt(future)
        else:
            reason = result.get("error") or "Unknown error"
            runtime["status"] = ProjectStatus.FAILED.value
            runtime["lastAction"] = reason
            runtime["lastResult"] = {
                "ok": False,
                "reason": reason,
                "httpStatus": result.get("httpStatus"),
                "message": reason,
            }
            project["stats"]["errorVotes"] = project["stats"].get("errorVotes", 0) + 1
            self.db.append_project_event(project, "FAILED", reason)
            self.db.append_log(
                {
                    "event": "project.result",
                    "projectKey": project["key"],
                    "result": "failure",
                    "message": reason,
                }
            )
            retry_dt = self._schedule_retry(project, runtime, settings, now_local)
            if retry_dt:
                runtime["nextAttemptAt"] = _iso_from_dt(retry_dt.astimezone(timezone.utc))
                project["time"] = _ms_from_dt(retry_dt)
                self._update_schedule_status(runtime, retry_dt.astimezone(timezone.utc), now_utc)
            else:
                future = self._pick_window_time(
                    now_local + timedelta(days=1),
                    settings.get("dailyWindowStart", "09:00"),
                    settings.get("dailyWindowEnd", "21:00"),
                    int(settings.get("jitterMinutes", 20)),
                    allow_today=False,
                )
                runtime["nextAttemptAt"] = _iso_from_dt(future.astimezone(timezone.utc))
                project["time"] = _ms_from_dt(future)
                self._update_schedule_status(runtime, future.astimezone(timezone.utc), now_utc)


def main():
    worker = VoteWorker()
    worker.start()


if __name__ == "__main__":
    main()
