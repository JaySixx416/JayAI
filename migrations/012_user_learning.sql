CREATE TABLE learning_records (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    record_key TEXT NOT NULL CHECK (record_key ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    kind TEXT NOT NULL CHECK (kind IN ('format', 'workflow', 'environment', 'accessibility')),
    observation TEXT NOT NULL CHECK (length(observation) BETWEEN 1 AND 500),
    source TEXT NOT NULL CHECK (source IN ('USER_STATED', 'USER_CORRECTION')),
    evidence_count INT NOT NULL CHECK (evidence_count BETWEEN 1 AND 1000),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    explicit BOOLEAN NOT NULL DEFAULT true CHECK (explicit),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, record_key)
);
CREATE INDEX learning_records_user_updated ON learning_records(user_id, updated_at DESC);

-- Store only outcome category and timing, never task text, PC report contents, or files.
CREATE TABLE learning_episodes (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    job_id UUID NOT NULL UNIQUE REFERENCES jobs(id),
    task_kind TEXT NOT NULL CHECK (task_kind IN ('pc_health', 'pc_processes', 'windows_health', 'unknown')),
    outcome TEXT NOT NULL CHECK (outcome IN ('VERIFIED', 'FAILED')),
    duration_seconds DOUBLE PRECISION NOT NULL CHECK (duration_seconds >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX learning_episodes_user_kind_time ON learning_episodes(user_id, task_kind, created_at DESC);
