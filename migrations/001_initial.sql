-- Initial schema proposal for Phase 2. Apply via a migration runner with a dedicated role.
CREATE TABLE users (id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE jobs (id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id), goal TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('RECEIVED','PLANNING','WAITING_FOR_APPROVAL','EXECUTING','OBSERVING','REPLANNING','VERIFYING','COMPLETED','FAILED','CANCELLED')), limits JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX jobs_user_created ON jobs(user_id, created_at DESC);
CREATE TABLE job_steps (id UUID PRIMARY KEY, job_id UUID NOT NULL REFERENCES jobs(id), ordinal INT NOT NULL CHECK (ordinal >= 0), state TEXT NOT NULL, input JSONB NOT NULL DEFAULT '{}'::jsonb, output JSONB, UNIQUE(job_id, ordinal));
CREATE INDEX job_steps_job_ordinal ON job_steps(job_id, ordinal);
CREATE TABLE permissions (id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id), resource TEXT NOT NULL, actions JSONB NOT NULL, mode TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE audit_events (id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id), job_id UUID REFERENCES jobs(id), event_type TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX audit_user_created ON audit_events(user_id, created_at DESC);
