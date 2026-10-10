from jayai.db import MIGRATIONS, migration_resources


def test_all_migration_sql_is_available_as_packaged_resources():
    resources = migration_resources()
    assert [resource.name for resource in resources] == [
        f"{index:03d}_{suffix}"
        for index, suffix in enumerate((
            "initial.sql", "registry.sql", "connections.sql", "queue.sql",
            "user_controls.sql", "job_plans.sql", "job_results.sql",
            "plan_budget.sql", "user_limits.sql", "approval_decisions.sql",
            "tool_call_limits.sql", "user_learning.sql", "permission_expiry.sql",
            "oidc_sessions.sql",
        ), 1)
    ]


def test_auth_migration_stores_only_session_hashes_and_scopes_identity_uniqueness():
    sql = (MIGRATIONS / "014_oidc_sessions.sql").read_text(encoding="utf-8")
    assert "UNIQUE (issuer, subject)" in sql
    assert "UNIQUE (user_id, issuer)" in sql
    assert "token_hash TEXT NOT NULL UNIQUE" in sql
    assert "expires_at > issued_at" in sql
    assert "raw_token" not in sql and "access_token" not in sql
