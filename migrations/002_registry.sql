CREATE TABLE tool_definitions (
    id TEXT PRIMARY KEY,
    spec JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE skills (
    user_id UUID NOT NULL REFERENCES users(id),
    id TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    removed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id)
);
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    skill_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('STARTED','SUCCEEDED','FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (user_id, skill_id) REFERENCES skills(user_id, id)
);
CREATE INDEX tool_calls_user_created ON tool_calls(user_id, created_at DESC);
