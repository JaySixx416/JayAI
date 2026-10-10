"""Service-free launcher regressions; every PostgreSQL command is a stub.

Run with unittest even when JayAI's runtime dependencies are unavailable.
The fake Python command evaluates the uploaded database_url function with a
recording conninfo formatter, never imports psycopg and never opens a socket.
"""

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def config_reader():
    tree = ast.parse((ROOT / "jayai" / "db.py").read_text(encoding="utf-8"))
    node = next(item for item in tree.body
                if isinstance(item, ast.FunctionDef) and item.name == "database_url")
    scope = {"os": os, "make_conninfo": lambda **kwargs: kwargs}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "database_url", "exec"), scope)
    return scope["database_url"]


@unittest.skipUnless(os.name != "nt", "Unix-socket configuration is Linux-only")
class SocketConfigurationTests(unittest.TestCase):
    def test_socket_without_password(self):
        values = {"JAYAI_DB_HOST": "/tmp/private socket/it's jayai", "JAYAI_DB_PORT": "55432",
                  "JAYAI_DB_NAME": "existing", "JAYAI_DB_USER": "synthetic"}
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(config_reader()(), {"host": values["JAYAI_DB_HOST"],
                             "port": "55432", "dbname": "existing", "user": "synthetic",
                             "connect_timeout": "10"})

    def test_url_and_password_precedence_remain(self):
        values = {"JAYAI_DB_HOST": "/tmp/socket", "JAYAI_DATABASE_URL": "postgresql://synthetic/existing"}
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(config_reader()(), values["JAYAI_DATABASE_URL"])
            os.environ["JAYAI_DB_PASSWORD"] = "synthetic-only"
            self.assertEqual(config_reader()()["password"], "synthetic-only")
            os.environ["JAYAI_DB_PASSWORD"] = ""
            with self.assertRaisesRegex(RuntimeError, "must not be empty"):
                config_reader()()

    def test_unconfigured_and_tcp_remain_rejected(self):
        for values in ({}, {"JAYAI_DB_HOST": "127.0.0.1"}, {"JAYAI_DB_HOST": "relative/socket"}):
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                with self.assertRaisesRegex(RuntimeError, "JAYAI_DATABASE_URL"):
                    config_reader()()


@unittest.skipUnless(os.name != "nt" and shutil.which("bash"), "Linux launcher requires Bash")
class LauncherTests(unittest.TestCase):
    def run_launcher(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "project"
            (project / "scripts").mkdir(parents=True)
            (project / "jayai").mkdir()
            shutil.copyfile(ROOT / "scripts" / "start-jayai.sh", project / "scripts" / "start-jayai.sh")
            shutil.copyfile(ROOT / "jayai" / "db.py", project / "jayai" / "db.py")
            tools = base / "stub-tools"
            tools.mkdir()
            log = base / "calls.jsonl"
            state = base / "private state"
            profile = state / "JayAI"
            (profile / "postgres").mkdir(parents=True)
            (profile / "postgres" / "PG_VERSION").write_text("synthetic\n")
            (profile / "development-user-id").write_text("00000000-0000-0000-0000-000000000001")
            (profile / "dashboard-key").write_text("a" * 64)
            command_stub = '''import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["AUDIT_CALLS"], "a") as stream:
    stream.write(json.dumps({"name": name, "args": args}) + "\\n")
if name == "pg_config":
    print(os.environ["AUDIT_TOOLS"])
elif name == "psql":
    mode = os.environ["AUDIT_PROBE"]
    if mode == "failure":
        sys.exit(2)
    if mode == "present":
        print("1")
    elif mode == "unexpected":
        print("not-a-result")
elif name == "pg_isready":
    pass
elif name == "initdb":
    sys.exit(99)
'''
            for name in ("pg_config", "pg_ctl", "pg_isready", "initdb", "psql", "createdb"):
                file = tools / name
                file.write_text("#!" + sys.executable + "\n" + command_stub)
                file.chmod(0o700)
            python_dir = project / ".venv" / "bin"
            python_dir.mkdir(parents=True)
            fake_python = python_dir / "python"
            fake_python.write_text("#!" + sys.executable + "\n" + '''import ast, json, os, pathlib, sys
args = sys.argv[1:]
record = {"name": "python", "args": args}
if args == ["-m", "jayai", "db-check"]:
    source = pathlib.Path(__file__).resolve().parents[2] / "jayai" / "db.py"
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "database_url")
    scope = {"os": os, "make_conninfo": lambda **kw: kw}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "database_url", "exec"), scope)
    record["config"] = scope["database_url"]()
with open(os.environ["AUDIT_CALLS"], "a") as stream:
    stream.write(json.dumps(record) + "\\n")
''')
            fake_python.chmod(0o700)
            # Deliberately avoid all inherited database, libpq and JayAI settings.
            environment = {"PATH": str(tools) + ":/usr/bin:/bin", "HOME": str(base),
                           "USER": "synthetic", "XDG_STATE_HOME": str(state),
                           "AUDIT_CALLS": str(log), "AUDIT_TOOLS": str(tools), "AUDIT_PROBE": mode}
            result = subprocess.run(["bash", str(project / "scripts" / "start-jayai.sh")],
                                    env=environment, capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, calls

    def test_existing_database_reaches_supported_socket_configuration(self):
        result, calls = self.run_launcher("present")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call["name"] in ("initdb", "createdb") for call in calls))
        check = next(call for call in calls if call["args"] == ["-m", "jayai", "db-check"])
        self.assertTrue(check["config"]["host"].endswith("/JayAI/postgres-socket"))
        self.assertEqual(check["config"]["port"], "55432")
        self.assertEqual(check["config"]["user"], "synthetic")
        self.assertNotIn("password", check["config"])
        probe = next(call for call in calls if call["name"] == "psql")
        self.assertIn("-X", probe["args"])
        self.assertIn("ON_ERROR_STOP=1", probe["args"])
        self.assertNotIn("a" * 64, result.stdout + result.stderr)

    def test_inspection_error_stops_before_creation_and_application_commands(self):
        result, calls = self.run_launcher("failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not inspect", result.stderr)
        self.assertFalse(any(call["name"] in ("createdb", "initdb", "python") for call in calls))

    def test_unexpected_output_stops_before_creation(self):
        result, calls = self.run_launcher("unexpected")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected PostgreSQL", result.stderr)
        self.assertFalse(any(call["name"] in ("createdb", "python") for call in calls))

    def test_successful_absence_keeps_first_install_creation_branch(self):
        result, calls = self.run_launcher("absent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(call["name"] == "createdb" for call in calls), 1)


if __name__ == "__main__":
    unittest.main()
