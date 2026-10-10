# JayAI 0.25.0 work and verification status

JayAI 0.25.0 is a Linux-only self-hosted prototype for Chromebook Linux or
another local Linux environment. The API stays on loopback. The application
does not inspect the ChromeOS host and does not support Windows runtime
components in this tree.

## Current implemented behavior

- Local Ollama planning with strict response validation and loopback endpoint
  validation.
- Exact-digest plan approval and rejection with user-scoped persistence.
- Atomic approval/admission and rejection/cancellation in the PostgreSQL
  repository.
- Pause blocks new admissions while already-admitted read-only checks can
  finish bookkeeping.
- Restart reconciliation marks stale active jobs failed with an audit reason;
  it never replays unknown work or verifies a result without durable evidence.
- Read-only Linux health and bounded process checks only.
- Per-user file workspace containment and linked-root rejection.
- Dashboard key held in the current browser tab only; no browser storage.
- Linux foreground launcher with loopback binding, disabled access logging,
  symlink-resistant key handling, and atomic key replacement.
- Package resources include all SQL migrations in wheel builds.
- Concurrent health observations use a lock and unique temporary files.
- Health history retains the most recent valid summaries.
- Redis pending-entry scans carry `XAUTOCLAIM` progress and never trim pending
  work.

## Open verification work

- Run one live Chromebook/Linux smoke test with the user’s existing PostgreSQL
  account, local Ollama model, and dashboard workflow.
- Verify real PostgreSQL concurrency for approvals, pause completion, restart
  reconciliation, OAuth refresh, and duplicate queue delivery using an
  isolated test database.
- Verify live Redis behavior with a large pending set, paused entries, poison
  entries, duplicates, and safe stream retention.
- Verify live Ollama behavior on the target Chromebook with `qwen2.5:0.5b`.
- Complete visual browser review of the dashboard and Song Studio on the target
  Linux device.
- Define production authentication, key custody/rotation, retention, provider
  revocation, and backup-erasure policies before broader access.
- Keep connector content out of planning until provenance, bounded content,
  policy checks, and adversarial isolation tests exist.
- Keep consequential actions disabled until dry-run, exact target consent,
  rollback, and post-change verification are designed.

## Verified in this workspace

- File isolation regression and normal traversal/link tests.
- Mocked database configuration and Chromebook launcher behavior.
- Mocked planner, approval, pause, queue, dashboard security, maintenance,
  migration packaging, and evidence validation tests.
- `bash -n scripts/start-jayai.sh`.
- `.venv/bin/python -m compileall -q jayai tests`.

These checks do not prove live PostgreSQL, Redis, Ollama, Google OAuth, OpenAI,
or device readiness. No live service result should be marked complete from
mocked tests.

## Deliberately out of scope

Arbitrary shell commands, installations, deletion, account changes, outbound
messages, purchases, public posts, automatic routines, and unsupervised
settings changes remain disabled.

## Future addon candidates

Potential later work includes supervised Redis processing, scoped read-only
connectors, expiring/revocable sessions, reviewable routines, carefully
bounded change recipes with rollback, and opt-in learning improvements. Each
requires separate design, adversarial tests, and live verification before it
becomes an enabled feature. None is part of the 0.25.0 supported workflow.
