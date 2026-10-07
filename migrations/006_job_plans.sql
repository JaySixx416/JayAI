CREATE TABLE job_plans (
    job_id UUID PRIMARY KEY REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    plan JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX job_plans_user ON job_plans(user_id);
