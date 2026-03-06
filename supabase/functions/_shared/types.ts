/**
 * Shared TypeScript types for sync edge functions.
 */

/** Result returned by every sync function. */
export interface SyncResult {
  source: string;
  recordsUpserted: number;
  recordsSkipped: number;
  durationMs: number;
  error?: string;
}

/** Row shape for data_freshness table. */
export interface FreshnessRow {
  source: string;
  last_fetch_at: string | null;
  record_count: number | null;
  status: string;
  updated_at: string;
  watermark: Record<string, unknown>;
  triggered_by: string;
}

/** Freshness check result from checkFreshness(). */
export interface FreshnessCheck {
  isStale: boolean;
  lastFetchAt: string | null;
  watermark: Record<string, unknown>;
  ageMinutes: number;
}

/** Configuration for a sync connector. */
export interface SyncConfig {
  source: string;
  ttlMinutes: number;
  batchSize: number;
  timeoutMs: number;
}
