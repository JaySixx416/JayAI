"""Transactional outbox plus Redis Stream delivery; delivery is at least once."""

import logging
import os
import socket
import time
from uuid import UUID

import psycopg
import redis
from redis.exceptions import ResponseError

from jayai.contracts import JobState
from jayai.db import Repository
from jayai.engine import Engine

STREAM = "jayai:jobs:v1"
GROUP = "jayai:workers:v1"
LOG = logging.getLogger(__name__)
_RECLAIM_CURSORS: dict[str, str] = {}


def client() -> redis.Redis:
    url = os.getenv("JAYAI_REDIS_URL", "")
    if not url or not url.startswith(("redis://", "rediss://")):
        raise RuntimeError("JAYAI_REDIS_URL is required")
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=5)


def group_ready(r: redis.Redis) -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def publish_pending(db: Repository, r: redis.Redis, batch: int = 20) -> int:
    """Hold rows across XADD; failed publish rolls back. Duplicates are harmless."""
    if not 1 <= batch <= 100:
        raise ValueError("batch must be 1..100")
    count = 0
    with psycopg.connect(db.url) as conn:
        rows = conn.execute("SELECT job_id, user_id FROM job_outbox WHERE published_at IS NULL "
                            "ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED", (batch,)).fetchall()
        for job_id, user_id in rows:
            r.xadd(STREAM, {"job_id": str(job_id), "user_id": str(user_id)})
            conn.execute("UPDATE job_outbox SET published_at=now() WHERE job_id=%s", (job_id,))
            count += 1
    return count


def process_entry(db: Repository, r: redis.Redis, entry_id: str, fields: dict) -> None:
    try:
        user_id = UUID(fields["user_id"])
        job_id = UUID(fields["job_id"])
    except (KeyError, ValueError) as exc:
        # Malformed stream entry has no safe tenant/job target; log and discard.
        LOG.error("Invalid queue entry %s: %s", entry_id, exc)
        r.xack(STREAM, GROUP, entry_id)
        return
    row = db.get_job(user_id, job_id)
    if row is None:
        # Never execute a job whose authenticated tenant does not match the payload.
        LOG.error("Missing or mismatched job in queue entry %s", entry_id)
        r.xack(STREAM, GROUP, entry_id)
        return
    if db.is_paused(user_id):
        # Leave this entry pending; a resumed worker can reclaim it.
        return
    if JobState(row["state"]) == JobState.RECEIVED:
        try:
            engine = Engine(db)
            engine.transition(user_id, job_id, JobState.PLANNING, "Queue worker started planning")
            engine.transition(user_id, job_id, JobState.WAITING_FOR_APPROVAL, "Awaiting approved execution plan")
        except RuntimeError as exc:
            if str(exc) not in ("Job runtime limit reached", "Job step limit reached"):
                raise
            # A permanently exhausted job cannot succeed on retry. Record the
            # failure durably before acknowledging its queue entry.
            Engine(db).transition(user_id, job_id, JobState.FAILED, str(exc))
        except ValueError:
            # Duplicate deliveries may race another worker: confirm durable progress.
            current = db.get_job(user_id, job_id)
            if current is None or JobState(current["state"]) == JobState.RECEIVED:
                raise
    elif JobState(row["state"]) == JobState.PLANNING:
        try:
            Engine(db).transition(user_id, job_id, JobState.WAITING_FOR_APPROVAL, "Awaiting approved execution plan")
        except RuntimeError as exc:
            if str(exc) not in ("Job runtime limit reached", "Job step limit reached"):
                raise
            Engine(db).transition(user_id, job_id, JobState.FAILED, str(exc))
    r.xack(STREAM, GROUP, entry_id)


def run_once(db: Repository, r: redis.Redis, consumer: str, block_ms: int = 1000) -> int:
    group_ready(r)
    # A restart can leave synchronous execution between durable transitions.
    # Mark old active jobs failed with an audit reason; never replay or verify.
    reconcile = getattr(db, "reconcile_stale_active_jobs", None)
    if reconcile is not None:
        reconcile()
    publish_pending(db, r)
    # Recover abandoned pending entries before reading new work. XAUTOCLAIM
    # returns a continuation ID; retain it so a large pending set is scanned
    # across worker iterations instead of restarting at the first ten entries.
    cursor_key = consumer
    start_id = _RECLAIM_CURSORS.get(cursor_key, "0-0")
    reclaimed = r.xautoclaim(STREAM, GROUP, consumer, min_idle_time=30000,
                             start_id=start_id, count=10)
    next_id, claimed = reclaimed[0], reclaimed[1]
    if next_id == "0-0":
        _RECLAIM_CURSORS.pop(cursor_key, None)
    else:
        _RECLAIM_CURSORS[cursor_key] = next_id
    messages = claimed
    if not messages:
        # Do not let a new-message read hide the remainder of a pending scan.
        if next_id != "0-0":
            return 0
        batches = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=10, block=block_ms)
        messages = [message for _, entries in batches for message in entries]
    for entry_id, fields in messages:
        try:
            process_entry(db, r, entry_id, fields)
        except Exception:
            LOG.exception("Queue entry %s remains pending for retry", entry_id)
    return len(messages)


def run_worker() -> None:
    db = Repository()
    r = client()
    consumer = socket.gethostname() + "-" + str(os.getpid())
    while True:
        try:
            run_once(db, r, consumer)
        except (psycopg.Error, redis.RedisError):
            LOG.exception("Queue unavailable; retrying")
            time.sleep(2)
