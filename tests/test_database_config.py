import sys
from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from jayai import db
from jayai.__main__ import main


@pytest.fixture(autouse=True)
def clean_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("JAYAI_DATABASE_URL", "JAYAI_DB_PASSWORD", "JAYAI_DB_HOST",
                 "JAYAI_DB_PORT", "JAYAI_DB_NAME", "JAYAI_DB_USER"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("password", ["a@#%/:? &", "a'b\\c", " white space ", "café雪", "line\nbreak"])
def test_password_round_trip_and_stale_url_override(monkeypatch, password):
    monkeypatch.setenv("JAYAI_DATABASE_URL", "postgresql://jayai:wrong@localhost/jayai")
    monkeypatch.setenv("JAYAI_DB_PASSWORD", password)
    config = conninfo_to_dict(db.database_url())
    assert config["password"] == password
    assert config["host"] == "127.0.0.1"
    assert config["port"] == "5432"
    assert config["dbname"] == config["user"] == "jayai"
    assert db.Repository().url == db.database_url()


def test_custom_parameters(monkeypatch):
    for key, value in {"PASSWORD": "secret", "HOST": "db.internal", "PORT": "5433",
                       "NAME": "custom_db", "USER": "custom_user"}.items():
        monkeypatch.setenv("JAYAI_DB_" + key, value)
    config = conninfo_to_dict(db.database_url())
    assert (config["host"], config["port"], config["dbname"], config["user"]) == (
        "db.internal", "5433", "custom_db", "custom_user")


def test_existing_url_is_preserved(monkeypatch):
    monkeypatch.setenv("JAYAI_DATABASE_URL", "postgresql+psycopg://jayai:p%40ss@localhost/jayai")
    assert db.database_url() == "postgresql://jayai:p%40ss@localhost/jayai"


def test_empty_password_fails_without_url_fallback(monkeypatch):
    monkeypatch.setenv("JAYAI_DB_PASSWORD", "")
    monkeypatch.setenv("JAYAI_DATABASE_URL", "postgresql://unused")
    with pytest.raises(RuntimeError, match="must not be empty"):
        db.database_url()


def test_check_is_read_only_and_uses_repository_configuration(monkeypatch):
    monkeypatch.setenv("JAYAI_DB_PASSWORD", "secret")
    connect = MagicMock()
    connection = connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = (1,)
    monkeypatch.setattr(db.psycopg, "connect", connect)
    db.check_database()
    connect.assert_called_once_with(db.Repository().url, connect_timeout=10, autocommit=True)
    connection.execute.assert_called_once_with("SELECT 1")


def test_cli_prompt_overrides_stale_url_without_exposing_password(monkeypatch, capsys):
    monkeypatch.setenv("JAYAI_DB_PASSWORD", "prior-password")
    monkeypatch.setenv("JAYAI_DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(sys, "argv", ["jayai", "db-check", "--prompt-db-password"])
    monkeypatch.setattr("jayai.__main__.getpass.getpass", lambda _: "a@#'secret")
    connect = MagicMock()
    connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
    monkeypatch.setattr(db.psycopg, "connect", connect)
    main()
    assert conninfo_to_dict(connect.call_args.args[0])["password"] == "a@#'secret"
    assert capsys.readouterr().out == "JayAI PostgreSQL connection: OK\n"


def test_cli_failure_does_not_print_connection_or_password(monkeypatch, capsys):
    monkeypatch.setenv("JAYAI_DB_PASSWORD", "private-value")
    monkeypatch.setattr(sys, "argv", ["jayai", "db-check"])
    monkeypatch.setattr(db.psycopg, "connect", MagicMock(side_effect=psycopg.OperationalError("private-value")))
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    output = capsys.readouterr()
    assert "FAILED" in output.err
    assert "private-value" not in output.out + output.err
