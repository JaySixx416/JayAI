# JayAI TODO — release 0.25.0 status

Goal: the same manually reviewed prototype on Jay's Windows PC and Chromebook Linux environment. ChromeOS host access remains separate. Consequential actions and unsupervised commands stay disabled.

## Recommended priority order

1. **P0 — Make the current standalone build usable and verifiable.** Keep the app loopback-only; finish the Windows/Chromebook launch path, migrations, docs, package tests, and the restricted dashboard tunnel. Do not mark device checks complete from mocked tests. Current code work: launchers, learning export, and docs are implemented; target-device checks remain open.
2. **P1 — Close security and reliability gates before expanding execution.** Review OAuth/key lifecycle and retention; add untrusted-input isolation tests; test approval, interruption, duplicate delivery, and recovery. Preserve the read-only allowlist until these pass.
3. **P2 — Stabilize background services.** Add supervised worker/monitor lifecycle and status only after the live Redis queue and device startup behavior are verified. Keep foreground startup as the supported standalone path for now.
4. **P3 — Finish safe learning behavior.** Evaluate explicit preferences against a baseline with measurable plan quality/time and rollback; add a routine approval record for scope, schedule, and actions. Suggestions must remain non-executable until approved.
5. **P4 — Connect file, browser, and Google reads to jobs.** First add structured action arguments, connector-specific permission/verification, and prompt-injection isolation tests. External data stays untrusted and cannot change policy.
6. **P5 — Add research, troubleshooting, or change recipes only from verified user feedback.** Keep repairs, installs, deletion, account changes, outbound messages, spending, and public posts disabled until dry-run, target confirmation, rollback, and post-change verification exist.
7. **P6 — Extend the selected songwriting workflow only after the Chromebook live smoke succeeds.** Suno generation remains a manual handoff until an official supported API is available.

### Recommendations from this review

- Treat 0.24.1 as a self-hosted development prototype, not a production release or single-file installer. PostgreSQL and Ollama remain required services; Redis and Google OAuth are optional.
- Do not connect email, web, documents, or Google content to model planning until the untrusted-data boundary is tested.
- Keep the Windows companion/dashboard access on loopback and use the restricted SSH key. Add only `permitopen="127.0.0.1:8000"` for the dashboard tunnel; do not remove the key's existing restrictions.
- Mark live checks complete only after Windows, Chromebook, Redis, and local model evidence comes back from those actual environments.
- Do not implement the business-workflow item by guessing. Its data scope and success measure belong to Jay.

## Prototype milestone

- [x] Local model-backed plan, authenticated user-scoped API, exact-digest approval/rejection, pause and cancel controls.
- [x] Execute approved read-only health checks and bounded process listings; verify scope, timestamp, data shape, and evidence before completing a job.
- [x] PostgreSQL connection check and migrations; this release adds migrations 010–013 without resetting existing data.
- [x] Local dashboard for jobs, plans, approval/rejection, results, pause, explicit learning records, and recent health history.
- [x] Self-hosted foreground launchers for Windows and Chromebook Linux, with loopback binding, database checks/migrations, stable non-secret user IDs, and per-run dashboard keys.
- [x] Consolidated standalone setup, upgrade, scope, tunnel, backup, and troubleshooting documentation.
- [x] Per-account learning export and non-executable routine suggestions from repeated verified task categories.
- [ ] Run the 0.24.1 end-to-end task and denial smoke on Jay's Windows PC and confirm the dashboard visually in the Windows browser.
- [ ] Confirm the 0.24.1 task flow in Chromebook Linux; outputs must continue to label Linux container scope.
- [ ] When Redis is available, verify the live queue reaches `WAITING_FOR_APPROVAL` and test the expired pending-entry fix.
- [ ] Verify a live local model plan on Windows and a live Windows companion check from the Chromebook tunnel.

## P1 — Safety and permissions

- [x] Deny by default; permission grants are user-scoped, resource/action-scoped, time-limited (1 minute to 24 hours), inspectable, and revocable. Expired grants no longer match.
- [x] Bind approval/rejection to an immutable plan digest and retain one exact decision per job/plan; changed or stale digests are rejected.
- [x] Pause blocks admission of new tool actions; cancel and rejection are recorded. Already-running system checks may finish.
- [x] Bound per-job runtime and tool-call count; require idempotency keys for job-bound calls and reject duplicates.
- [x] Model planning calls are bounded; default cost allowance is zero and the planner uses local Ollama.
- [x] Audit permission grants/revocations, approval decisions, results, and learning record changes without logging credential values.
- [x] Learning is explicit, account-scoped, secret-pattern filtered, inspectable, correctable, and erasable; job outcome categories are bounded.
- [x] Test the current closed planning boundary against email, web, document, and tool-output fields; reject unsupported source/control fields on job creation and unauthorized model actions/approval fields. See `docs/UNTRUSTED_DATA.md`.
- [ ] Before enabling connector content in planning, add real connector-to-planner isolation tests, structured source handling, and per-action policy/verification. Current tests establish exclusion, not safe model use of external content.
- [x] Complete an initial code review of credential encryption, key management, retention, and OAuth lifecycle; record findings in `docs/SECURITY_REVIEW.md` and fix redirect parsing, refreshed scope validation, refresh-token rotation, and stale refresh writes.
- [ ] Close the production gates from that review: managed key custody/rotation, retention/purge policy, provider revocation, and live OAuth/concurrent refresh verification.
- [ ] Add broader interruption and concurrent duplicate-delivery tests against live PostgreSQL/Redis; retain the read-only action allowlist until verified.

## P2 — Planning and P3 — execution

- [x] Generate local model plans and persist immutable, user-scoped plans with server-defined expected evidence.
- [x] Require exact-digest approval/rejection; record decision and show it in the job API/dashboard.
- [x] Verify scoped read-only PC health, process inventory, and Windows companion evidence before completion; failures leave the job failed.
- [ ] Verify Windows and Chromebook live task smoke end to end.
- [ ] Connect existing scoped file/browser/Google read tools to the job runner with per-action policy and verification before execution.
- [ ] Add separately reviewed change workflows only after dry-run preview, exact target consent, rollback, and post-change verification exist. Do not enable arbitrary shell, deletion, install, account changes, sends, or spending.

## P4 — Dashboard

- [x] Task-first responsive layout with job status, plans, expected evidence, run/reject/cancel, results, and pause.
- [x] Learning panel for inspecting, correcting, removing, and clearing explicit preferences/outcome summaries.
- [x] Recent bounded PC health history with environment scope and plain-language findings.
- [ ] Confirm visual usability in Windows browser and Chromebook Linux browser; fix any observed device-specific issues.
- [ ] Add a dedicated troubleshooting view after live finding feedback establishes which suggestions are useful.

## P5 — PC support

- [x] Read-only scoped health checks, Windows update/reboot status, startup names, recent error identifiers, package inventory, and bounded process list.
- [x] Health history stores bounded summaries without filenames or file contents.
- [ ] Test live monitoring, Windows companion tunnel, and Linux diagnostics on their target devices.
- [x] Add predictable foreground API startup and stop instructions for Windows and Chromebook Linux.
- [ ] Add supervised worker/monitor background startup, recovery, and status management.
- [ ] Add vetted-source research with source links and untrusted-input isolation.
- [ ] Add a narrow file/application inspection registry and reviewed single-operation change recipes with dry runs and rollback.

## P6 — Learning

- [x] Store explicit preferences and brief success/failure categories; show repeat verified task categories without inferring permissions.
- [ ] Use saved preferences and verified outcomes in later plans with a measurable accuracy/time evaluation and rollback.
- [x] Show review-only routine suggestions with supporting verified examples; scope, schedule, and actions remain blank and nothing executes automatically.
- [ ] Add separate approval and persistence for routine scope, schedule, and actions before any routine can be enabled.
- [x] Export learned preferences, outcome summaries, and review-only routine suggestions as account-scoped JSON.

## P7 — Business workflow

- [ ] Jay selects a concrete workflow (for example, research, draft preparation, or follow-up tracking), its allowed data, deliverables, and success/cost measures.
- [ ] Implement that selected workflow as a scoped, reviewable slice. Purchases, payments, investments, account changes, and public posts remain behind explicit approval.

## Release evidence and boundaries

The 0.22.2 Windows setup was confirmed by Jay: PostgreSQL direct/Psycopg connection succeeded, migration 009 applied, and tests reported 71 passed, 1 skipped, 1 warning. Jay later confirmed PostgreSQL connection and migrations 010–013 on Windows, with 88 tests passed, 1 skipped, and 1 Starlette/AnyIO deprecation warning on release 0.23.0. Release 0.24.1 adds launchers, consolidated docs, and learning export/suggestions; local Python 3.12 verification reports **90 passed, 1 warning** (Starlette/AnyIO deprecation). The Linux launcher passed `bash -n`; PowerShell execution and service startup were not available in this environment. Live Windows and Chromebook smoke tests, browser visual review, Redis queue, live model, and Windows companion tunnel remain device/service checks. The current dashboard tunnel log showed Windows SSH refusing forwarding (`administratively prohibited`); allowlist port 8000 for the restricted Chromebook key before retesting. Business workflow implementation still requires Jay's choice. Full OS privileges, unsupervised commands, and consequential actions are intentionally out of scope for this prototype.

## 0.24.1 follow-up evidence

OAuth hardening suite and existing tests: **99 passed, 1 warning** on Python 3.12. Provider/SQL interactions in the new tests use mocks; live Google consent, token refresh, PostgreSQL concurrency, and revocation are unverified. Initial security review is complete; production gates stay open.

## 0.24.2 follow-up evidence

Closed-boundary injection regressions and existing suite: **116 passed, 1 warning** on Python 3.12. Seventeen new cases exercise source exclusion, job API rejection, and model-schema rejection. Live adversarial model behavior and integrated connector planning remain unverified; external-content planning remains disabled.

## 0.25.0 Song Studio

- [x] Add responsive Song Studio UI and authenticated review endpoints for Chromebook Crostini and Windows.
- [x] Add validated title, analysis, audit, revised lyrics, performance map, and Suno export package response; no database migration.
- [x] Keep the optional provider key in the process environment and avoid persisting it in the database or logs.
- [x] Keep Suno handoff manual; no website automation or unverified Suno API.
- [ ] Install and run 0.25.0 on Jay's Chromebook, confirm Song Studio visually, and complete one live API-backed review.
- [ ] Confirm the resulting lyrics/style package can be pasted into Suno Custom Mode and reviewed before creation.

Automated test execution for this package must be confirmed before release; the current workspace does not have the pinned pytest/runtime dependencies installed.
