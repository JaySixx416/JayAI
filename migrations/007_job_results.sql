CREATE TABLE job_results (
    job_id UUID PRIMARY KEY REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX job_results_user ON job_results(user_id);
