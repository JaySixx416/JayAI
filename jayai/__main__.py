import argparse
import getpass
import os
import psycopg
from uuid import UUID

from jayai.db import Repository, check_database, migrate


def main() -> None:
    parser = argparse.ArgumentParser(description="JayAI management")
    parser.add_argument("command", choices=["db-check", "migrate", "create-dev-user", "worker", "pc-check", "pc-monitor", "remove-limits"])
    parser.add_argument("--prompt-db-password", action="store_true", help="Read database password privately; bypass JAYAI_DATABASE_URL for this process")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between PC checks (60–86400)")
    args = parser.parse_args()
    if args.prompt_db_password:
        os.environ["JAYAI_DB_PASSWORD"] = getpass.getpass("JayAI database password: ")
    if args.command == "db-check":
        try:
            check_database()
        except (psycopg.Error, RuntimeError):
            parser.exit(1, "JayAI PostgreSQL connection: FAILED. Check database credentials and host/port settings.\n")
        print("JayAI PostgreSQL connection: OK")
    elif args.command == "migrate":
        print("Applied:", ", ".join(migrate()) or "none (already current)")
    elif args.command == "worker":
        import logging
        from jayai.queue import run_worker
        logging.basicConfig(level=logging.INFO)
        run_worker()
    elif args.command == "remove-limits":
        user_id = UUID(os.environ["JAYAI_DEV_USER_ID"])
        Repository().set_unlimited_limits(user_id, True)
        print("Removed job and planning caps for:", user_id)
    elif args.command == "create-dev-user":
        print("Development user ID:", Repository().create_user())
    elif args.command in ("pc-check", "pc-monitor"):
        from jayai.maintenance import monitor
        try:
            monitor(args.interval, once=args.command == "pc-check")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
