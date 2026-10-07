-- Existing grants expire immediately at migration time. Users may create a
-- fresh narrow grant with an explicit one-hour default (maximum 24 hours).
ALTER TABLE permissions ADD COLUMN expires_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX permissions_user_expiry ON permissions(user_id, expires_at);
