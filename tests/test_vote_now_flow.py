from datetime import datetime, timedelta, timezone

from worker.config import Config
from worker.database import Database
from worker.main import VoteWorker
from worker.statuses import ProjectStatus


class DummyVoter:
    def __init__(self):
        self.called = False

    def vote(self, project):
        self.called = True
        return {"success": True, "message": "Opened in test"}

    def cleanup(self):
        pass


def test_vote_now_queue_and_process(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db = Database(str(data_dir))
    db.initialize()

    key = db.add_project({
        "rating": "minecraft-server.eu",
        "id": "208F7",
        "voteUrl": "https://minecraft-server.eu/vote/index/208F7/",
        "name": "Test Project"
    })

    queued_project = db.queue_vote_now(key, source="test")
    assert queued_project["runtime"]["status"] == ProjectStatus.QUEUED.value

    config = Config()
    config.data_dir = str(data_dir)
    worker = VoteWorker(config=config, db=db, voter=DummyVoter())
    worker.check_and_vote()

    updated = db.get_project(key)
    assert updated["runtime"]["lastAttemptAt"] is not None
    assert updated["runtime"]["status"] in {
        ProjectStatus.NEEDS_USER_ACTION.value,
        ProjectStatus.SUCCESS.value,
        ProjectStatus.SCHEDULED.value,
    }


def test_worker_keeps_manual_action_state(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db = Database(str(data_dir))
    db.initialize()

    key = db.add_project({
        "rating": "minecraft-server.eu",
        "id": "208F7",
        "voteUrl": "https://minecraft-server.eu/vote/index/208F7/",
        "name": "Manual Wait"
    })

    project = db.get_project(key)
    runtime = project["runtime"]
    runtime["status"] = ProjectStatus.NEEDS_USER_ACTION.value
    runtime["needsActionUntil"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    runtime["nextAttemptAt"] = None
    project["time"] = None
    db.update_project(project)

    dummy_voter = DummyVoter()
    config = Config()
    config.data_dir = str(data_dir)
    worker = VoteWorker(config=config, db=db, voter=dummy_voter)
    worker.check_and_vote()

    updated = db.get_project(key)
    assert updated["runtime"]["status"] == ProjectStatus.NEEDS_USER_ACTION.value
    assert updated["runtime"]["nextAttemptAt"] is None
    assert not dummy_voter.called
