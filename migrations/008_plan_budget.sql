-- Bound model requests per development user and job, including failed requests.
CREATE TABLE plan_requests (
    job_id UUID PRIMARY KEY REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    attempts INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','FAILED','COMPLETED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX plan_requests_user_updated ON plan_requests(user_id, updated_at);
