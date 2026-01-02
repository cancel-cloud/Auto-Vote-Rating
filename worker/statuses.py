"""
Project status definitions shared between worker and dashboard.
"""
from enum import Enum


class ProjectStatus(str, Enum):
    IDLE = "IDLE"
    SCHEDULED = "SCHEDULED"
    DUE_SOON = "DUE_SOON"
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_USER_ACTION = "NEEDS_USER_ACTION"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def is_active(status: str) -> bool:
    """Return True if the project is actively being worked on."""
    return status in {
        ProjectStatus.QUEUED.value,
        ProjectStatus.IN_PROGRESS.value,
        ProjectStatus.NEEDS_USER_ACTION.value,
    }
