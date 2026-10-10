"""Isolated PostgreSQL migration validation.

This test is intentionally opt-in. It must receive a disposable database URL
through JAYAI_ISOLATED_DATABASE_URL and never falls back to JayAI settings.
"""

import os

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
    assert applied == expected
    with psycopg.connect(url) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
        }
    assert {"users", "jobs", "job_results", "oidc_identities", "auth_sessions"} <= tables
