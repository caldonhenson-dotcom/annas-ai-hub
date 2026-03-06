/**
 * Reusable sync utilities — core pattern for any connector.
 * All sync edge functions import these helpers.
 */

import { getServiceClient } from "./supabase.ts";
import type { FreshnessCheck } from "./types.ts";

/** Check if a source needs re-syncing based on TTL. */
export async function checkFreshness(
  source: string,
  ttlMinutes: number,
): Promise<FreshnessCheck> {
  const sb = getServiceClient();
  const { data } = await sb
    .from("data_freshness")
    .select("last_fetch_at, watermark")
    .eq("source", source)
    .single();

  if (!data || !data.last_fetch_at) {
    return { isStale: true, lastFetchAt: null, watermark: {}, ageMinutes: Infinity };
  }

  const ageMs = Date.now() - new Date(data.last_fetch_at).getTime();
  const ageMinutes = Math.round(ageMs / 60_000);

  return {
    isStale: ageMinutes >= ttlMinutes,
    lastFetchAt: data.last_fetch_at,
    watermark: data.watermark ?? {},
    ageMinutes,
  };
}

/** Batch upsert rows to a table with conflict resolution. */
export async function batchUpsert(
  table: string,
  rows: Record<string, unknown>[],
  conflictColumn: string,
  batchSize = 500,
): Promise<number> {
  if (rows.length === 0) return 0;
  const sb = getServiceClient();
  let upserted = 0;

  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    const { error } = await sb
      .from(table)
      .upsert(batch, { onConflict: conflictColumn });
    if (error) {
      console.error(`Upsert ${table} batch ${i}: ${error.message}`);
      continue;
    }
    upserted += batch.length;
  }
  return upserted;
}

/** Update data_freshness after a sync completes. */
export async function updateFreshness(
  source: string,
  count: number,
  triggeredBy: string,
  watermark?: Record<string, unknown>,
): Promise<void> {
  const sb = getServiceClient();
  const row: Record<string, unknown> = {
    source,
    last_fetch_at: new Date().toISOString(),
    record_count: count,
    status: "ok",
    updated_at: new Date().toISOString(),
    triggered_by: triggeredBy,
  };
  if (watermark) row.watermark = watermark;

  await sb.from("data_freshness").upsert(row, { onConflict: "source" });
}

/** Mark a source as errored in data_freshness. */
export async function markError(source: string, msg: string): Promise<void> {
  const sb = getServiceClient();
  await sb
    .from("data_freshness")
    .upsert(
      { source, status: "error", updated_at: new Date().toISOString() },
      { onConflict: "source" },
    );
  console.error(`[${source}] sync error: ${msg}`);
}

/** Refresh all materialized views via the stored function. */
export async function refreshViews(): Promise<void> {
  const sb = getServiceClient();
  const { error } = await sb.rpc("refresh_all_views");
  if (error) console.error(`View refresh failed: ${error.message}`);
  else console.log("Materialized views refreshed");
}
