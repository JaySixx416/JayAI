"""Explicit PostgreSQL persistence. All user-facing queries include tenant scope."""

import os
import re
import hmac
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jayai.contracts import JobState, Limits, PolicyMode, SkillSpec, ToolSpec
from jayai.plans import plan_digest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def database_url() -> str:
    """Return a libpq connection string; explicit parameters bypass URL parsing."""
    if "JAYAI_DB_PASSWORD" in os.environ:
        password = os.environ["JAYAI_DB_PASSWORD"]
        if not password:
            raise RuntimeError("JAYAI_DB_PASSWORD must not be empty")
        return make_conninfo(
            host=os.environ.get("JAYAI_DB_HOST", "127.0.0.1"),
            port=os.environ.get("JAYAI_DB_PORT", "5432"),
            dbname=os.environ.get("JAYAI_DB_NAME", "jayai"),
            user=os.environ.get("JAYAI_DB_USER", "jayai"),
            password=password,
            connect_timeout="10",
        )
    url = os.environ.get("JAYAI_DATABASE_URL", "")
    if not url:
        raise RuntimeError("JAYAI_DATABASE_URL or JAYAI_DB_PASSWORD is required")
    # psycopg expects postgresql://, while some configuration uses SQLAlchemy's dialect prefix.
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def check_database() -> None:
    """Check the same configuration used by repositories without changing schema."""
    with psycopg.connect(database_url(), connect_timeout=10, autocommit=True) as conn:
        row = conn.execute("SELECT 1").fetchone()
        if row != (1,):
            raise RuntimeError("Database verification returned an unexpected result")


def migrate(url: str | None = None) -> list[str]:
    """Apply each version once, atomically, with a database advisory lock."""
    applied: list[str] = []
    with psycopg.connect(url or database_url()) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(747165)")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            existing = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
            for path in sorted(MIGRATIONS.glob("[0-9]*.sql")):
                if path.name in existing:
                    continue
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
                applied.append(path.name)
    return applied


class Repository:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or database_url()

    def create_user(self) -> UUID:
        user_id = uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
            conn.execute("INSERT INTO user_controls (user_id) VALUES (%s)", (user_id,))
        return user_id

    def set_unlimited_limits(self, user_id: UUID, enabled: bool) -> None:
        """Set the limits preference for exactly one user and audit the change."""
        with psycopg.connect(self.url) as conn:
            row = conn.execute("UPDATE user_controls SET unlimited_limits = %s, updated_at = now() "
                               "WHERE user_id = %s RETURNING user_id", (enabled, user_id)).fetchone()
            if row is None:
                raise LookupError("user control not found")
            conn.execute("INSERT INTO audit_events (id, user_id, event_type, details) VALUES (%s, %s, %s, %s)",
                         (uuid4(), user_id, "user.limits_changed", Jsonb({"unlimited_limits": enabled})))

    def create_job(self, user_id: UUID, goal: str, limits: Limits | None = None) -> UUID:
        if not goal.strip():
            raise ValueError("goal cannot be empty")
        job_id = uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO jobs (id, user_id, goal, state, limits) VALUES (%s, %s, %s, %s, %s)",
                         (job_id, user_id, goal, JobState.RECEIVED.value, Jsonb((limits or Limits()).model_dump())))
            conn.execute("INSERT INTO audit_events (id, user_id, job_id, event_type, details) VALUES (%s, %s, %s, %s, %s)",
                         (uuid4(), user_id, job_id, "job.created", Jsonb({"state": JobState.RECEIVED.value})))
            conn.execute("INSERT INTO job_outbox (job_id, user_id) VALUES (%s, %s)", (job_id, user_id))
        return job_id

    def get_job(self, user_id: UUID, job_id: UUID) -> dict | None:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            return conn.execute("SELECT id, user_id, goal, state, limits, created_at, updated_at FROM jobs WHERE id = %s AND user_id = %s",
                                (job_id, user_id)).fetchone()

    def list_jobs(self, user_id: UUID) -> list[dict]:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            return conn.execute("SELECT id, user_id, goal, state, limits FROM jobs WHERE user_id = %s "
                                "ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()

    def save_plan(self, user_id: UUID, job_id: UUID, plan: dict) -> None:
        with psycopg.connect(self.url) as conn:
            control = conn.execute("SELECT paused FROM user_controls WHERE user_id = %s FOR UPDATE", (user_id,)).fetchone()
            if control is None or control[0]:
                raise PermissionError("User actions paused")
            row = conn.execute("SELECT state FROM jobs WHERE id = %s AND user_id = %s FOR UPDATE",
                               (job_id, user_id)).fetchone()
            if row is None:
                raise LookupError("job not found")
            if row[0] not in (JobState.RECEIVED.value, JobState.PLANNING.value, JobState.WAITING_FOR_APPROVAL.value):
                raise ValueError("Job cannot accept a plan in its current state")
            inserted = conn.execute("INSERT INTO job_plans (job_id, user_id, plan) VALUES (%s, %s, %s) "
                                    "ON CONFLICT (job_id) DO NOTHING RETURNING job_id",
                                    (job_id, user_id, Jsonb(plan))).fetchone()
            if inserted is None:
                raise ValueError("Job already has a plan")
            conn.execute("INSERT INTO audit_events (id, user_id, job_id, event_type, details) VALUES (%s, %s, %s, %s, %s)",
                         (uuid4(), user_id, job_id, "job.plan.proposed", Jsonb({"steps": len(plan["steps"])})))

    def get_plan(self, user_id: UUID, job_id: UUID) -> dict | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT plan FROM job_plans WHERE user_id = %s AND job_id = %s", (user_id, job_id)).fetchone()
            return row[0] if row else None

    def record_approval_decision(self, user_id: UUID, job_id: UUID, digest: str,
                                 decision: str, reason: str = "") -> dict:
        """Record one immutable, user-scoped decision for the exact stored plan."""
        if decision not in ("APPROVED", "REJECTED") or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid approval decision")
        if len(reason) > 500:
            raise ValueError("Decision reason exceeds 500 characters")
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            control = conn.execute("SELECT paused FROM user_controls WHERE user_id = %s FOR UPDATE",
                                   (user_id,)).fetchone()
            if control is None:
                raise LookupError("user control not found")
            if decision == "APPROVED" and control["paused"]:
                raise PermissionError("User actions paused")
            row = conn.execute(
                "SELECT j.state, p.plan FROM jobs j JOIN job_plans p ON p.job_id=j.id AND p.user_id=j.user_id "
                "WHERE j.id=%s AND j.user_id=%s FOR UPDATE OF j", (job_id, user_id)
            ).fetchone()
            if row is None:
                raise LookupError("job or plan not found")
            if row["state"] != JobState.WAITING_FOR_APPROVAL.value:
                raise ValueError("Job has no plan awaiting approval")
            if not hmac.compare_digest(plan_digest(row["plan"]), digest):
                raise ValueError("Plan digest does not match")
            existing = conn.execute(
                "SELECT id, decision, reason, decided_at FROM approval_decisions "
                "WHERE job_id=%s AND user_id=%s AND plan_sha256=%s",
                (job_id, user_id, digest),
            ).fetchone()
            if existing:
                if existing["decision"] != decision:
                    raise ValueError("A different decision is already recorded for this plan")
                return dict(existing)
            event_id = uuid4()
            conn.execute(
                "INSERT INTO approval_decisions (id, job_id, user_id, plan_sha256, decision, reason) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (event_id, job_id, user_id, digest, decision, reason),
            )
            conn.execute(
                "INSERT INTO audit_events (id,user_id,job_id,event_type,details) VALUES (%s,%s,%s,%s,%s)",
                (uuid4(), user_id, job_id, "job.plan." + decision.lower(),
                 Jsonb({"plan_sha256": digest, "reason": reason[:500]})),
            )
            return {"id": event_id, "decision": decision, "reason": reason,
                    "plan_sha256": digest}

    def get_approval_decision(self, user_id: UUID, job_id: UUID) -> dict | None:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT plan_sha256, decision, reason, decided_at FROM approval_decisions "
                "WHERE user_id=%s AND job_id=%s", (user_id, job_id),
            ).fetchone()
            return dict(row) if row else None

    def reserve_plan_request(self, user_id: UUID, job_id: UUID) -> None:
        """Serialize admissions per user; apply caps unless this user opted out."""
        with psycopg.connect(self.url) as conn:
            control = conn.execute("SELECT paused, unlimited_limits FROM user_controls WHERE user_id = %s FOR UPDATE", (user_id,)).fetchone()
            if control is None or control[0]:
                raise PermissionError("User actions paused")
            unlimited = control[1]
            job = conn.execute("SELECT state, limits, created_at FROM jobs WHERE id = %s AND user_id = %s FOR UPDATE",
                               (job_id, user_id)).fetchone()
            if job is None:
                raise LookupError("Job not found")
            if job[0] not in (JobState.RECEIVED.value, JobState.PLANNING.value, JobState.WAITING_FOR_APPROVAL.value):
                raise ValueError("Job cannot accept a plan in its current state")
            limits = Limits.model_validate(job[1])
            remaining = 2 if job[0] == JobState.RECEIVED.value else (1 if job[0] == JobState.PLANNING.value else 0)
            if remaining and not unlimited:
                used = conn.execute("SELECT count(*) FROM job_steps WHERE job_id = %s", (job_id,)).fetchone()[0]
                if used + remaining > limits.max_steps:
                    raise ValueError("Job step limit cannot fit plan transitions")
            if not unlimited:
                expired = conn.execute("SELECT EXTRACT(EPOCH FROM (now() - %s)) > %s",
                                       (job[2], limits.max_runtime_seconds)).fetchone()[0]
                if expired:
                    raise ValueError("Job runtime limit reached")
            if conn.execute("SELECT 1 FROM job_plans WHERE job_id = %s", (job_id,)).fetchone():
                raise ValueError("Job already has a plan")
            attempts = conn.execute("SELECT attempts, status, updated_at FROM plan_requests WHERE job_id = %s FOR UPDATE",
                                    (job_id,)).fetchone()
            if attempts:
                if attempts[0] >= 3 and not unlimited:
                    raise ValueError("Job planning retry limit reached")
                if attempts[1] == "RUNNING" and conn.execute(
                    "SELECT now() - %s < interval '180 seconds'", (attempts[2],)).fetchone()[0]:
                    raise ValueError("Plan request already running")
            if not unlimited:
                daily = conn.execute("SELECT coalesce(sum(attempts), 0) FROM plan_requests "
                                     "WHERE user_id = %s AND updated_at >= now() - interval '24 hours'", (user_id,)).fetchone()[0]
                if daily >= 10:
                    raise PermissionError("Daily planning request limit reached")
            conn.execute("INSERT INTO plan_requests (job_id, user_id, attempts, status) VALUES (%s, %s, 1, 'RUNNING') "
                         "ON CONFLICT (job_id) DO UPDATE SET attempts = plan_requests.attempts + 1, "
                         "status = 'RUNNING', updated_at = now()", (job_id, user_id))

    def finish_plan_request(self, user_id: UUID, job_id: UUID, success: bool) -> None:
        with psycopg.connect(self.url) as conn:
            conn.execute("UPDATE plan_requests SET status = %s, updated_at = now() WHERE user_id = %s AND job_id = %s",
                         ("COMPLETED" if success else "FAILED", user_id, job_id))

    def save_result(self, user_id: UUID, job_id: UUID, result: dict) -> None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id = %s AND user_id = %s FOR UPDATE",
                               (job_id, user_id)).fetchone()
            if row is None or row[0] != JobState.VERIFYING.value:
                raise ValueError("Job is not verifying")
            conn.execute("INSERT INTO job_results (job_id, user_id, result) VALUES (%s, %s, %s)",
                         (job_id, user_id, Jsonb(result)))
            conn.execute("INSERT INTO audit_events (id, user_id, job_id, event_type, details) VALUES (%s, %s, %s, %s, %s)",
                         (uuid4(), user_id, job_id, "job.result.verified", Jsonb({"kind": result["kind"]})))

    def get_result(self, user_id: UUID, job_id: UUID) -> dict | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT result FROM job_results WHERE user_id = %s AND job_id = %s", (user_id, job_id)).fetchone()
            return row[0] if row else None

    def is_paused(self, user_id: UUID) -> bool:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT paused FROM user_controls WHERE user_id = %s", (user_id,)).fetchone()
            return row is None or row[0]

    def set_paused(self, user_id: UUID, paused: bool) -> None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("UPDATE user_controls SET paused = %s, updated_at = now() "
                               "WHERE user_id = %s RETURNING user_id", (paused, user_id)).fetchone()
            if row is None:
                raise LookupError("user control not found")
            conn.execute("INSERT INTO audit_events (id, user_id, event_type, details) VALUES (%s, %s, %s, %s)",
                         (uuid4(), user_id, "user.paused" if paused else "user.resumed", Jsonb({})))

    def transition_job(self, user_id: UUID, job_id: UUID, target: JobState, reason: str) -> JobState:
        from jayai.engine import validate_transition

        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            control = conn.execute("SELECT paused, unlimited_limits FROM user_controls WHERE user_id = %s FOR UPDATE", (user_id,)).fetchone()
            if control is None:
                raise RuntimeError("User control missing")
            if control["paused"] and target not in (JobState.FAILED, JobState.CANCELLED):
                raise RuntimeError("User actions paused")
            # Row lock serializes concurrent workers; state, step and audit commit together.
            row = conn.execute("SELECT state, limits, created_at FROM jobs WHERE id = %s AND user_id = %s FOR UPDATE",
                               (job_id, user_id)).fetchone()
            if row is None:
                raise LookupError("job not found")
            current = JobState(row["state"])
            validate_transition(current, target)
            limits = Limits.model_validate(row["limits"])
            count = conn.execute("SELECT count(*) AS n FROM job_steps WHERE job_id = %s", (job_id,)).fetchone()["n"]
            if not control.get("unlimited_limits", False) and count >= limits.max_steps and target not in (JobState.FAILED, JobState.CANCELLED):
                raise RuntimeError("Job step limit reached")
            if not control.get("unlimited_limits", False):
                elapsed = conn.execute("SELECT EXTRACT(EPOCH FROM (now() - %s)) AS seconds", (row["created_at"],)).fetchone()["seconds"]
                if elapsed > limits.max_runtime_seconds and target not in (JobState.FAILED, JobState.CANCELLED):
                    raise RuntimeError("Job runtime limit reached")
            conn.execute("UPDATE jobs SET state = %s, updated_at = now() WHERE id = %s AND user_id = %s",
                         (target.value, job_id, user_id))
            conn.execute("INSERT INTO job_steps (id, job_id, ordinal, state, input) VALUES (%s, %s, %s, %s, %s)",
                         (uuid4(), job_id, count, target.value, Jsonb({"reason": reason})))
            conn.execute("INSERT INTO audit_events (id, user_id, job_id, event_type, details) VALUES (%s, %s, %s, %s, %s)",
                         (uuid4(), user_id, job_id, "job.transition", Jsonb({"from": current.value, "to": target.value})))
            if target in (JobState.COMPLETED, JobState.FAILED):
                action = conn.execute("SELECT plan->>'action' FROM job_plans WHERE job_id=%s AND user_id=%s",
                                      (job_id, user_id)).fetchone()
                kind = action[0] if action and action[0] in ("pc_health", "pc_processes", "windows_health") else "unknown"
                outcome = "VERIFIED" if target == JobState.COMPLETED else "FAILED"
                if target == JobState.COMPLETED and conn.execute(
                        "SELECT 1 FROM job_results WHERE job_id=%s AND user_id=%s", (job_id, user_id)).fetchone() is None:
                    raise RuntimeError("Cannot complete job without a verified result")
                conn.execute(
                    "INSERT INTO learning_episodes (id,user_id,job_id,task_kind,outcome,duration_seconds) "
                    "VALUES (%s,%s,%s,%s,%s,greatest(0,EXTRACT(EPOCH FROM (now() - %s)))) "
                    "ON CONFLICT (job_id) DO NOTHING", (uuid4(), user_id, job_id, kind, outcome, row["created_at"]),
                )
                conn.execute("WITH keep AS (SELECT id FROM learning_episodes WHERE user_id=%s "
                             "ORDER BY created_at DESC LIMIT 500) DELETE FROM learning_episodes "
                             "WHERE user_id=%s AND id NOT IN (SELECT id FROM keep)", (user_id, user_id))
        return target

    def add_step(self, user_id: UUID, job_id: UUID, ordinal: int, state: str, data: dict) -> UUID:
        if ordinal < 0:
            raise ValueError("ordinal must be nonnegative")
        step_id = uuid4()
        with psycopg.connect(self.url) as conn:
            result = conn.execute("INSERT INTO job_steps (id, job_id, ordinal, state, input) "
                                  "SELECT %s, id, %s, %s, %s FROM jobs WHERE id = %s AND user_id = %s RETURNING id",
                                  (step_id, ordinal, state, Jsonb(data), job_id, user_id)).fetchone()
            if result is None:
                raise LookupError("job not found")
        return step_id

    def set_permission(self, user_id: UUID, resource: str, actions: list[str], mode: str,
                       expires_in_seconds: int = 3600) -> UUID:
        if not resource or not actions or len(actions) > 16 or len(set(actions)) != len(actions):
            raise ValueError("resource and actions are required")
        if not 60 <= expires_in_seconds <= 86400:
            raise ValueError("Permission duration must be between 60 and 86400 seconds")
        mode = PolicyMode(mode).value
        permission_id = uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO permissions (id, user_id, resource, actions, mode, expires_at) "
                         "VALUES (%s, %s, %s, %s, %s, now() + (%s * interval '1 second'))",
                         (permission_id, user_id, resource, Jsonb(actions), mode, expires_in_seconds))
            conn.execute("INSERT INTO audit_events (id,user_id,event_type,details) VALUES (%s,%s,%s,%s)",
                         (uuid4(), user_id, "permission.granted",
                          Jsonb({"resource": resource, "actions": actions, "mode": mode,
                                 "expires_in_seconds": expires_in_seconds})))
        return permission_id

    def permission_modes(self, user_id: UUID, resource: str, action: str) -> list[str]:
        with psycopg.connect(self.url) as conn:
            return [row[0] for row in conn.execute(
                "SELECT mode FROM permissions WHERE user_id = %s AND resource = %s AND actions ? %s AND expires_at > now()",
                (user_id, resource, action))]

    def list_permissions(self, user_id: UUID) -> list[dict]:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            rows = conn.execute("SELECT id,resource,actions,mode,expires_at,(expires_at<=now()) AS expired "
                                "FROM permissions WHERE user_id=%s ORDER BY expires_at DESC", (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def revoke_permission(self, user_id: UUID, permission_id: UUID) -> bool:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("DELETE FROM permissions WHERE user_id=%s AND id=%s RETURNING resource,actions",
                               (user_id, permission_id)).fetchone()
            if row is None:
                return False
            conn.execute("INSERT INTO audit_events (id,user_id,event_type,details) VALUES (%s,%s,%s,%s)",
                         (uuid4(), user_id, "permission.revoked",
                          Jsonb({"resource": row[0], "actions": row[1]})))
            return True

    def sync_tool(self, spec: ToolSpec) -> None:
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO tool_definitions (id, spec) VALUES (%s, %s) "
                         "ON CONFLICT (id) DO UPDATE SET spec = EXCLUDED.spec, updated_at = now()",
                         (spec.id, Jsonb(spec.model_dump(mode="json"))))

    def install_skill(self, user_id: UUID, skill: SkillSpec) -> None:
        with psycopg.connect(self.url) as conn:
            conn.execute("INSERT INTO skills (user_id, id, version, manifest, enabled) VALUES (%s, %s, %s, %s, true) "
                         "ON CONFLICT (user_id, id) DO UPDATE SET version = EXCLUDED.version, manifest = EXCLUDED.manifest, enabled = true, removed_at = NULL, updated_at = now()",
                         (user_id, skill.id, skill.version, Jsonb(skill.model_dump(mode="json"))))

    def get_skill(self, user_id: UUID, skill_id: str) -> SkillSpec | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT manifest FROM skills WHERE user_id = %s AND id = %s AND enabled = true AND removed_at IS NULL",
                               (user_id, skill_id)).fetchone()
            return SkillSpec.model_validate(row[0]) if row else None

    def set_skill_enabled(self, user_id: UUID, skill_id: str, enabled: bool) -> bool:
        with psycopg.connect(self.url) as conn:
            return conn.execute("UPDATE skills SET enabled = %s, updated_at = now() WHERE user_id = %s AND id = %s AND removed_at IS NULL RETURNING id",
                                (enabled, user_id, skill_id)).fetchone() is not None

    def remove_skill(self, user_id: UUID, skill_id: str) -> bool:
        """Soft remove to retain historical tool calls and auditability."""
        with psycopg.connect(self.url) as conn:
            return conn.execute("UPDATE skills SET enabled = false, removed_at = now(), updated_at = now() "
                                "WHERE user_id = %s AND id = %s AND removed_at IS NULL RETURNING id",
                                (user_id, skill_id)).fetchone() is not None

    def start_tool_call(self, user_id: UUID, skill_id: str, tool_id: str,
                        job_id: UUID | None = None, idempotency_key: str | None = None) -> UUID:
        if job_id is not None and (not idempotency_key or len(idempotency_key) > 128):
            raise ValueError("A job-bound tool call needs a 1–128 character idempotency key")
        if job_id is None and idempotency_key is not None:
            raise ValueError("An idempotency key requires a job id")
        call_id = uuid4()
        with psycopg.connect(self.url) as conn:
            # Serialize action start with set_paused(). Once pause commits,
            # no later tool call may be admitted for this user.
            control = conn.execute("SELECT paused FROM user_controls WHERE user_id = %s FOR UPDATE", (user_id,)).fetchone()
            if control is None or control[0]:
                raise PermissionError("User actions paused")
            if job_id is not None:
                job = conn.execute("SELECT limits, created_at, state FROM jobs WHERE id=%s AND user_id=%s FOR UPDATE",
                                   (job_id, user_id)).fetchone()
                if job is None:
                    raise LookupError("job not found")
                if job[2] in (JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELLED.value):
                    raise PermissionError("Terminal job cannot start a tool call")
                limits = Limits.model_validate(job[0])
                count = conn.execute("SELECT count(*) FROM tool_calls WHERE job_id=%s", (job_id,)).fetchone()[0]
                if count >= limits.max_tool_calls:
                    raise PermissionError("Job tool-call limit reached")
                expired = conn.execute("SELECT EXTRACT(EPOCH FROM (now() - %s)) > %s",
                                       (job[1], limits.max_runtime_seconds)).fetchone()[0]
                if expired:
                    raise PermissionError("Job runtime limit reached")
                repeated = conn.execute("SELECT 1 FROM tool_calls WHERE job_id=%s AND idempotency_key=%s",
                                        (job_id, idempotency_key)).fetchone()
                if repeated:
                    raise PermissionError("Duplicate tool call blocked")
            conn.execute("INSERT INTO tool_calls (id, user_id, skill_id, tool_id, status, job_id, idempotency_key) "
                         "VALUES (%s, %s, %s, %s, 'STARTED', %s, %s)",
                         (call_id, user_id, skill_id, tool_id, job_id, idempotency_key))
        return call_id

    def finish_tool_call(self, user_id: UUID, call_id: UUID, success: bool) -> None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute("UPDATE tool_calls SET status = %s, completed_at = now() WHERE id = %s AND user_id = %s AND status = 'STARTED' RETURNING id",
                               ("SUCCEEDED" if success else "FAILED", call_id, user_id)).fetchone()
            if row is None:
                raise LookupError("tool call not found or already finished")

    def audit(self, user_id: UUID, event_type: str, details: dict, job_id: UUID | None = None) -> UUID:
        event_id = uuid4()
        with psycopg.connect(self.url) as conn:
            if job_id is not None:
                owned = conn.execute("SELECT 1 FROM jobs WHERE id = %s AND user_id = %s", (job_id, user_id)).fetchone()
                if owned is None:
                    raise LookupError("job not found")
            conn.execute("INSERT INTO audit_events (id, user_id, job_id, event_type, details) VALUES (%s, %s, %s, %s, %s)",
                         (event_id, user_id, job_id, event_type, Jsonb(details)))
        return event_id

    def list_learning(self, user_id: UUID) -> dict:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            records = conn.execute(
                "SELECT record_key,kind,observation,source,evidence_count,confidence,explicit,created_at,updated_at "
                "FROM learning_records WHERE user_id=%s ORDER BY updated_at DESC LIMIT 200", (user_id,),
            ).fetchall()
            episodes = conn.execute(
                "SELECT task_kind,outcome,duration_seconds,created_at FROM learning_episodes "
                "WHERE user_id=%s ORDER BY created_at DESC LIMIT 100", (user_id,),
            ).fetchall()
            patterns = conn.execute(
                "SELECT task_kind,count(*) AS verified_count FROM learning_episodes "
                "WHERE user_id=%s AND outcome='VERIFIED' GROUP BY task_kind HAVING count(*)>=2 "
                "ORDER BY verified_count DESC", (user_id,),
            ).fetchall()
            return {"records": [dict(row) for row in records],
                    "episodes": [dict(row) for row in episodes],
                    "repeat_patterns": [dict(row) for row in patterns]}

    def save_learning(self, user_id: UUID, record_key: str, learning: dict) -> dict:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            row = conn.execute(
                "INSERT INTO learning_records (id,user_id,record_key,kind,observation,source,evidence_count,confidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id,record_key) DO UPDATE SET "
                "kind=EXCLUDED.kind,observation=EXCLUDED.observation,source=EXCLUDED.source,"
                "evidence_count=EXCLUDED.evidence_count,confidence=EXCLUDED.confidence,updated_at=now() "
                "RETURNING record_key,kind,observation,source,evidence_count,confidence,explicit,created_at,updated_at",
                (uuid4(), user_id, record_key, learning["kind"], learning["observation"],
                 learning["source"], learning["evidence_count"], learning["confidence"]),
            ).fetchone()
            conn.execute("INSERT INTO audit_events (id,user_id,event_type,details) VALUES (%s,%s,%s,%s)",
                         (uuid4(), user_id, "learning.record_saved",
                          Jsonb({"record_key": record_key, "kind": learning["kind"], "source": learning["source"]})))
            return dict(row)

    def delete_learning(self, user_id: UUID, record_key: str | None = None) -> int:
        with psycopg.connect(self.url) as conn:
            if record_key is None:
                records = conn.execute("DELETE FROM learning_records WHERE user_id=%s RETURNING id", (user_id,)).fetchall()
                episodes = conn.execute("DELETE FROM learning_episodes WHERE user_id=%s RETURNING id", (user_id,)).fetchall()
                count = len(records) + len(episodes)
                event = "learning.cleared"
                details = {"deleted_count": count}
            else:
                deleted = conn.execute("DELETE FROM learning_records WHERE user_id=%s AND record_key=%s RETURNING id",
                                       (user_id, record_key)).fetchone()
                count = int(deleted is not None)
                event = "learning.record_deleted"
                details = {"record_key": record_key, "deleted": bool(count)}
            conn.execute("INSERT INTO audit_events (id,user_id,event_type,details) VALUES (%s,%s,%s,%s)",
                         (uuid4(), user_id, event, Jsonb(details)))
            return count
