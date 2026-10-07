CREATE TABLE job_outbox (
    job_id UUID PRIMARY KEY REFERENCES jobs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
CREATE INDEX job_outbox_unpublished ON job_outbox(created_at) WHERE published_at IS NULL;
