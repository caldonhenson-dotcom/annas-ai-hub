-- ============================================
-- ANNAS AI HUB — API Keys
-- ============================================
-- Migration 007: API key authentication table
-- Keys are stored as SHA-256 hashes for security
-- ============================================

CREATE TABLE IF NOT EXISTS api_keys (
    id              BIGSERIAL PRIMARY KEY,
    key_hash        TEXT UNIQUE NOT NULL,    -- SHA-256 hash of the API key
    name            TEXT NOT NULL,           -- descriptive name (e.g. "Dashboard Frontend")
    scope           TEXT DEFAULT 'read',     -- read | write | admin
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ,
    active          BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash) WHERE active = TRUE;

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- Only service role can manage API keys
CREATE POLICY "Allow service read api_keys"
    ON api_keys FOR SELECT USING (true);
CREATE POLICY "Allow service write api_keys"
    ON api_keys FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow service update api_keys"
    ON api_keys FOR UPDATE USING (true);
