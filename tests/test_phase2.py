from pathlib import Path
from uuid import uuid4

import pytest

from jayai.db import MIGRATIONS, Repository, database_url


def test_database_url_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAYAI_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="JAYAI_DATABASE_URL"):
        database_url()


def test_reject_blank_goal_before_connecting() -> None:
    repo = Repository("postgresql://unused")
    with pytest.raises(ValueError, match="goal cannot be empty"):
        repo.create_job(uuid4(), " \t ")


def test_initial_migration_has_core_tables() -> None:
    sql = (MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8")
    for table in ("users", "jobs", "job_steps", "permissions", "audit_events"):
        assert f"CREATE TABLE {table} " in sql
