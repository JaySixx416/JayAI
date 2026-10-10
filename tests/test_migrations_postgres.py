"""Isolated PostgreSQL migration validation.

This test is intentionally opt-in. It must receive a disposable database URL
through JAYAI_ISOLATED_DATABASE_URL and never falls back to JayAI settings.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from jayai.db import migrate, migration_resources


@pytest.mark.skipif(
    not os.getenv("JAYAI_ISOLATED_DATABASE_URL"),
    reason="requires an explicitly configured disposable PostgreSQL database",
)
def test_all_migrations_apply_to_isolated_database():
    url = os.environ["JAYAI_ISOLATED_DATABASE_URL"]
    applied = migrate(url)
    expected = [resource.name for resource in migration_resources()]
    assert set(applied) <= set(expected)
    with psycopg.connect(url) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
        }
    assert {"users", "jobs", "job_results", "oidc_identities", "auth_sessions"} <= tables


@pytest.mark.skipif(
    not os.getenv("JAYAI_ISOLATED_DATABASE_URL"),
    reason="requires an explicitly configured disposable PostgreSQL database",
)
def test_sessions_and_identity_binding_are_safe_under_concurrency():
    url = os.environ["JAYAI_ISOLATED_DATABASE_URL"]
    migrate(url)
    user_a, user_b = uuid4(), uuid4()
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s), (%s)", (user_a, user_b))

    from jayai.db import Repository
    repository = Repository(url)
    tokens = [f"{index:064x}" for index in range(8)]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        session_ids = list(pool.map(
            lambda token: repository.create_auth_session(user_a, token, expires_at),
            tokens,
        ))
    assert len(set(session_ids)) == len(tokens)
    assert repository.get_auth_session(tokens[0])["user_id"] == user_a
    assert repository.revoke_user_sessions(user_a) == len(tokens)
    assert repository.get_auth_session(tokens[0]) is None

    with ThreadPoolExecutor(max_workers=2) as pool:
        bindings = list(pool.map(
            lambda user: repository.bind_oidc_identity(user, "https://issuer.example", "subject-1"),
            (user_a, user_b),
        ))
    assert sorted(bindings) == [False, True]
