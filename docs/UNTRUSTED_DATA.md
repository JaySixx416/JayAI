# Untrusted data and planning — 0.24.2

## Supported boundary

The planner receives the authenticated user's saved goal and a server-owned system instruction/schema. Email, web pages, documents, connector results, learning records, and tool reports are not added to its request. API and queue operation do not convert connector content into a goal automatically.

Job creation accepts `goal` and `limits` only. Extra fields now return HTTP 422, including supplied source content, plans, approval flags, and permissions. Clients that previously sent ignored extra fields must remove them. This is an intentional validation tightening; the dashboard's existing request remains compatible.

Model output is untrusted. It must pass the strict ProposedPlan schema with only summary, steps, and the read-only action enum. Unknown actions and authority fields are rejected. Model text cannot grant permissions or approve itself. Accepted plans remain in WAITING_FOR_APPROVAL; execution still requires the authenticated exact-digest approval path and server verification. Descriptions and steps are review text, not commands interpreted by the runner.

## What the tests establish

- Four source categories containing instruction attacks, placed alongside the stored goal, do not reach the model request.
- Seven API cases supplying content/control fields are rejected before job persistence.
- Six model responses adding shell/send/delete actions, approval, permissions, or commands fail strict validation.

These tests use a mocked model and store. They verify the current exclusion boundary and output validation; they do not prove a model can safely read adversarial connector content. A user can manually paste external text into a goal; that text is then part of the submitted goal and may influence review text or select an allowed read-only action. Approval and scope checks still apply.

## Gate before connecting sources

Keep connector content out of planning until each real connector path has provenance, bounded content, structured action arguments, policy/permission checks, and adversarial tests. Test that source instructions cannot alter goals, grant authority, select out-of-scope targets, auto-approve, or cause follow-up execution. Add tool-output attacks to any future replanning path. No source-handling feature is enabled by this release.

## Verification

The current verification suite uses mocked providers and stores. Live Chromebook device acceptance, live model adversarial behavior, and integrated connector planning remain unverified.
