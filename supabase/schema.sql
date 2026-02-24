-- ============================================
-- ANNAS AI HUB — Supabase Schema
-- ============================================
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)
--
-- Stores processed dashboard metrics as JSONB snapshots.
-- The frontend reads the latest snapshot per source via REST API.
-- ============================================

-- 1. Main snapshots table
CREATE TABLE IF NOT EXISTS dashboard_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- hubspot_sales | monday | inbound_queue | email_actions | weekly_summary
    data        JSONB NOT NULL,         -- full processed metrics JSON
    generated_at TIMESTAMPTZ NOT NULL,  -- when the analyzer produced this data
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_snapshots_source
    ON dashboard_snapshots (source);
CREATE INDEX IF NOT EXISTS idx_snapshots_source_generated
    ON dashboard_snapshots (source, generated_at DESC);

-- 2. Lightweight "latest" view — one row per source
CREATE OR REPLACE VIEW dashboard_latest AS
SELECT DISTINCT ON (source)
    id, source, data, generated_at, created_at
FROM dashboard_snapshots
ORDER BY source, generated_at DESC;

-- 3. Row Level Security
ALTER TABLE dashboard_snapshots ENABLE ROW LEVEL SECURITY;

-- Allow anyone with the anon key to SELECT (read-only for the frontend)
CREATE POLICY "Allow public read"
    ON dashboard_snapshots
    FOR SELECT
    USING (true);

-- Allow service_role to INSERT (server-side sync script)
CREATE POLICY "Allow service insert"
    ON dashboard_snapshots
    FOR INSERT
    WITH CHECK (true);

-- Allow service_role to DELETE old snapshots (cleanup)
CREATE POLICY "Allow service delete"
    ON dashboard_snapshots
    FOR DELETE
    USING (true);
