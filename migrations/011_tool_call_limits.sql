ALTER TABLE tool_calls
    ADD COLUMN job_id UUID REFERENCES jobs(id),
    ADD COLUMN idempotency_key TEXT CHECK (idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 128);

CREATE INDEX tool_calls_job_created ON tool_calls(job_id, created_at) WHERE job_id IS NOT NULL;
CREATE UNIQUE INDEX tool_calls_job_idempotency
    ON tool_calls(job_id, idempotency_key)
    WHERE job_id IS NOT NULL AND idempotency_key IS NOT NULL;
