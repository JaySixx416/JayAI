# Release 0.24.0

## Implemented

- Analyzed TODO dependencies and added P0–P6 recommendations and priority order.
- Added foreground Windows PowerShell and Linux launchers with database checks/migrations, loopback binding, stable user profiles, and temporary dashboard keys.
- Consolidated standalone installation, database creation, upgrades, account continuity, backup, SSH tunnel diagnosis, and device acceptance documentation.
- Added authenticated account-scoped learning JSON export with database timestamp serialization and no-store response caching.
- Added review-only routine suggestions supported by repeated verified outcomes; no schedule or automatic execution is created.

## Verification

Python 3.12 automated suite: **90 passed, 1 warning**. Warning: Starlette uses a deprecated AnyIO BlockingPortal alias. Linux launcher syntax: passed `bash -n`.

Windows PowerShell execution, live PostgreSQL/Redis/Ollama, Chromebook and Windows browser checks, and companion/tunnel checks remain unverified for this release. Follow STANDALONE.md's acceptance check and record results in TODO.md. No database schema changes were added in 0.24.0.

## Next work

Complete P0 target-device acceptance, then P1 OAuth/key/retention review and untrusted-input isolation before connecting external content to model planning. Remaining TODO checkboxes are intentionally open until implementation and evidence satisfy them.
