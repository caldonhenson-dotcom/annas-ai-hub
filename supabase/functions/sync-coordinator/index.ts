/**
 * sync-coordinator — Orchestrator that checks TTLs and triggers stale syncs.
 * Invoked by pg_cron every 2 hours on weekdays 08-18 UTC.
 *
 * Deploy: supabase functions deploy sync-coordinator --no-verify-jwt
 */

import { CORS_HEADERS, handleCors } from "../_shared/cors.ts";
import { checkFreshness } from "../_shared/sync-base.ts";

/** Source TTLs in minutes. Add new connectors here. */
const SOURCES: Array<{ source: string; ttlMinutes: number; fnName: string }> = [
  { source: "hubspot", ttlMinutes: 120, fnName: "sync-hubspot" },
  { source: "monday",  ttlMinutes: 240, fnName: "sync-monday" },
];

Deno.serve(async (req: Request) => {
  const cors = handleCors(req);
  if (cors) return cors;

  const start = Date.now();
  const baseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!baseUrl || !serviceKey) {
    return new Response(
      JSON.stringify({ error: "Missing SUPABASE_URL or SERVICE_ROLE_KEY" }),
      { status: 500, headers: CORS_HEADERS },
    );
  }

  const triggered: string[] = [];
  const skipped: string[] = [];
  const errors: string[] = [];

  for (const { source, ttlMinutes, fnName } of SOURCES) {
    try {
      const check = await checkFreshness(source, ttlMinutes);
      if (!check.isStale) {
        skipped.push(`${source} (${check.ageMinutes}m old)`);
        continue;
      }

      console.log(`Triggering ${fnName} (${source} is ${check.ageMinutes}m stale)`);
      const resp = await fetch(`${baseUrl}/functions/v1/${fnName}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${serviceKey}`,
          "Content-Type": "application/json",
        },
        signal: AbortSignal.timeout(140_000), // Just under 150s edge limit
      });

      if (resp.ok) {
        const result = await resp.json();
        triggered.push(`${source}: ${result.recordsUpserted ?? 0} upserted`);
      } else {
        const text = await resp.text();
        errors.push(`${source}: ${resp.status} — ${text}`);
      }
    } catch (err) {
      errors.push(`${source}: ${String(err)}`);
    }
  }

  const summary = {
    triggered,
    skipped,
    errors,
    durationMs: Date.now() - start,
  };
  console.log("Coordinator complete:", JSON.stringify(summary));
  return new Response(JSON.stringify(summary), { headers: CORS_HEADERS });
});
