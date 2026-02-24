-- ============================================
-- ANNAS AI HUB — Pipeline Runs & Data Freshness
-- ============================================
-- Migration 003: Tables for pipeline orchestration tracking
-- Run in Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- ============================================

-- 1. Pipeline run tracking
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          BIGSERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'running',  -- running | success | failed
    steps       JSONB DEFAULT '[]'::jsonb,        -- [{name, status, duration_ms, error}]
    error_log   TEXT,
    narration   TEXT,                             -- AI-generated change summary (Phase 4)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs (status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started
    ON pipeline_runs (started_at DESC);

-- 2. Data freshness per source
CREATE TABLE IF NOT EXISTS data_freshness (
    source        TEXT PRIMARY KEY,               -- hubspot | monday | gsheets
    last_fetch_at TIMESTAMPTZ,
    record_count  INT,
    status        TEXT DEFAULT 'ok',              -- ok | error | stale
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 3. RLS policies
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_freshness ENABLE ROW LEVEL SECURITY;

-- Public read for dashboard display
CREATE POLICY "Allow public read pipeline_runs"
    ON pipeline_runs FOR SELECT USING (true);

CREATE POLICY "Allow service insert pipeline_runs"
    ON pipeline_runs FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow service update pipeline_runs"
    ON pipeline_runs FOR UPDATE USING (true);

CREATE POLICY "Allow public read data_freshness"
    ON data_freshness FOR SELECT USING (true);

CREATE POLICY "Allow service upsert data_freshness"
    ON data_freshness FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow service update data_freshness"
    ON data_freshness FOR UPDATE USING (true);
