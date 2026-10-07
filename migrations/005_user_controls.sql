-- Persist a per-user stop switch; missing rows are treated as paused by the worker.
CREATE TABLE user_controls (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    paused BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO user_controls (user_id) SELECT id FROM users ON CONFLICT DO NOTHING;
