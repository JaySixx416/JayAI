-- Opt-in per-user exemption from job runtime, step, and planning request caps.
-- Does not bypass pause, approvals, tenant scope, or executable action allowlists.
ALTER TABLE user_controls ADD COLUMN unlimited_limits BOOLEAN NOT NULL DEFAULT false;
