-- ============================================
-- ANNAS AI HUB — Sync Watermarks
-- ============================================
-- Migration 010: Add watermark + triggered_by to data_freshness
-- Enables edge functions to track incremental sync state
-- ============================================

ALTER TABLE data_freshness
  ADD COLUMN IF NOT EXISTS watermark     JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS triggered_by  TEXT  DEFAULT 'manual';

COMMENT ON COLUMN data_freshness.watermark IS
  'Incremental sync cursor — e.g. {"last_sync_ms": 1709726400000}';
COMMENT ON COLUMN data_freshness.triggered_by IS
  'Who triggered last sync — manual | coordinator | python_pipeline';
