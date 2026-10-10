-- Cloud authentication foundation. Apply only after isolated database review.
CREATE TABLE oidc_identities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer TEXT NOT NULL CHECK (length(issuer) BETWEEN 1 AND 2048),
    subject TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (issuer, subject),
    UNIQUE (user_id, issuer)
);
CREATE INDEX oidc_identities_user ON oidc_identities(user_id);

CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > issued_at),
    CHECK (revoked_at IS NULL OR revoked_at >= issued_at)
);
CREATE INDEX auth_sessions_active_lookup ON auth_sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;
CREATE INDEX auth_sessions_user_active ON auth_sessions(user_id, expires_at)
    WHERE revoked_at IS NULL;
