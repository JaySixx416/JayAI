from uuid import uuid4

from jayai.contracts import JobState
from jayai.queue import GROUP, STREAM, process_entry, run_once


class MemoryStore:
    def __init__(self):
        self.user = uuid4()
        self.job = uuid4()
        self.state = JobState.RECEIVED
        self.transitions = []
        self.paused = False

    def is_paused(self, user):
        return self.paused

    def get_job(self, user, job):
        return {"state": self.state.value} if user == self.user and job == self.job else None

    def transition_job(self, user, job, state, reason):
        assert user == self.user and job == self.job
        self.transitions.append(state)
        self.state = state
        return state


class MemoryQueue:
    def __init__(self):
        self.acked = []

    def xack(self, stream, group, entry):
        assert (stream, group) == (STREAM, GROUP)
        self.acked.append(entry)


def test_worker_is_idempotent_and_stops_for_approval():
    db, r = MemoryStore(), MemoryQueue()
    data = {"job_id": str(db.job), "user_id": str(db.user)}
    process_entry(db, r, "1-0", data)
    process_entry(db, r, "2-0", data)
    assert db.transitions == [JobState.PLANNING, JobState.WAITING_FOR_APPROVAL]
    assert db.state == JobState.WAITING_FOR_APPROVAL
    assert r.acked == ["1-0", "2-0"]


def test_worker_does_not_process_wrong_user():
    db, r = MemoryStore(), MemoryQueue()
    process_entry(db, r, "1-0", {"job_id": str(db.job), "user_id": str(uuid4())})
    assert db.state == JobState.RECEIVED
    assert r.acked == ["1-0"]


def test_worker_does_not_ack_failed_transition():
    db, r = MemoryStore(), MemoryQueue()
    def fail(*args):
        raise RuntimeError("database unavailable")
    db.transition_job = fail
    try:
        process_entry(db, r, "1-0", {"job_id": str(db.job), "user_id": str(db.user)})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected database failure")
    assert r.acked == []


def test_paused_worker_does_not_advance_or_ack():
    db, r = MemoryStore(), MemoryQueue()
    db.paused = True
    process_entry(db, r, "1-0", {"job_id": str(db.job), "user_id": str(db.user)})
    assert db.state == JobState.RECEIVED
    assert r.acked == []


def test_expired_job_fails_once_and_is_acknowledged():
    db, r = MemoryStore(), MemoryQueue()
    original = db.transition_job

    def expired(user, job, state, reason):
        if state == JobState.PLANNING:
            raise RuntimeError("Job runtime limit reached")
        return original(user, job, state, reason)

    db.transition_job = expired
    data = {"job_id": str(db.job), "user_id": str(db.user)}
    process_entry(db, r, "1-0", data)
    process_entry(db, r, "2-0", data)
    assert db.state == JobState.FAILED
    assert db.transitions == [JobState.FAILED]
    assert r.acked == ["1-0", "2-0"]
