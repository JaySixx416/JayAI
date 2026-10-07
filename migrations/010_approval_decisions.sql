CREATE TABLE approval_decisions (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    plan_sha256 CHAR(64) NOT NULL CHECK (plan_sha256 ~ '^[a-f0-9]{64}$'),
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 500),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, plan_sha256)
);
CREATE INDEX approval_decisions_user_time ON approval_decisions(user_id, decided_at DESC);
