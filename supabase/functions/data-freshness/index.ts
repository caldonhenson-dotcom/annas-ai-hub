/**
 * data-freshness — Dashboard-facing GET endpoint for sync status.
 * Returns freshness info for all sources so the UI can show live status.
 *
 * Deploy: supabase functions deploy data-freshness --no-verify-jwt
 */

import { CORS_HEADERS, handleCors } from "../_shared/cors.ts";
import { getServiceClient } from "../_shared/supabase.ts";

/** TTLs used to determine if a source is stale. */
const TTL_MAP: Record<string, number> = {
  hubspot: 120,
  monday: 240,
  gsheets: 60,
};

Deno.serve(async (req: Request) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    const sb = getServiceClient();
    const { data, error } = await sb
      .from("data_freshness")
      .select("source, last_fetch_at, record_count, status, updated_at, triggered_by")
      .order("source");

    if (error) throw error;

    const now = Date.now();
    const sources = (data ?? []).map((row) => {
      const lastMs = row.last_fetch_at
        ? new Date(row.last_fetch_at).getTime() : 0;
      const ageMinutes = lastMs ? Math.round((now - lastMs) / 60_000) : null;
      const ttl = TTL_MAP[row.source] ?? 120;

      return {
        source: row.source,
        lastFetchAt: row.last_fetch_at,
        recordCount: row.record_count,
        status: row.status,
        triggeredBy: row.triggered_by,
        ageMinutes,
        isStale: ageMinutes === null || ageMinutes >= ttl,
        ttlMinutes: ttl,
      };
    });

    return new Response(
      JSON.stringify({ sources, checkedAt: new Date().toISOString() }),
      { headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: CORS_HEADERS },
    );
  }
});
