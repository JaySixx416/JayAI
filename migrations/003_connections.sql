CREATE TABLE oauth_attempts (
    state_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
    verifier_ciphertext BYTEA NOT NULL, scopes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX oauth_attempts_created ON oauth_attempts(created_at);
CREATE TABLE oauth_connections (
    user_id UUID NOT NULL REFERENCES users(id), provider TEXT NOT NULL,
    access_ciphertext BYTEA NOT NULL, refresh_ciphertext BYTEA,
    scopes TEXT NOT NULL, expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, provider)
);
