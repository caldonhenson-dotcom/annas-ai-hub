/**
 * sync-hubspot — Incremental HubSpot CRM sync.
 * Ports the Python search_modified() pattern to Deno edge functions.
 *
 * Deploy: supabase functions deploy sync-hubspot --no-verify-jwt
 * Secrets: HUBSPOT_API_KEY (set via supabase secrets set)
 */

import { CORS_HEADERS, handleCors } from "../_shared/cors.ts";
import {
  checkFreshness, batchUpsert, updateFreshness,
  markError, refreshViews,
} from "../_shared/sync-base.ts";
import { hubspotLimiter } from "../_shared/rate-limiter.ts";
import type { SyncResult } from "../_shared/types.ts";
import {
  HUBSPOT_BASE, PAGE_LIMIT,
  CONTACT_PROPS, DEAL_PROPS, COMPANY_PROPS,
  mapContact, mapDeal, mapCompany,
} from "./config.ts";

const TTL_MINUTES = 120; // 2 hours

Deno.serve(async (req: Request) => {
  const cors = handleCors(req);
  if (cors) return cors;

  const start = Date.now();
  const apiKey = Deno.env.get("HUBSPOT_API_KEY");
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "Missing HUBSPOT_API_KEY" }),
      { status: 500, headers: CORS_HEADERS },
    );
  }

  try {
    const freshness = await checkFreshness("hubspot", TTL_MINUTES);
    if (!freshness.isStale) {
      const result: SyncResult = {
        source: "hubspot", recordsUpserted: 0, recordsSkipped: 0,
        durationMs: Date.now() - start,
      };
      return new Response(JSON.stringify(result), { headers: CORS_HEADERS });
    }

    const sinceMsRaw = freshness.watermark?.last_sync_ms;
    const sinceMs = typeof sinceMsRaw === "number" ? sinceMsRaw : null;
    let total = 0;

    total += await syncObjectType(apiKey, "contacts", CONTACT_PROPS, mapContact, sinceMs);
    total += await syncObjectType(apiKey, "deals", DEAL_PROPS, mapDeal, sinceMs);
    total += await syncObjectType(apiKey, "companies", COMPANY_PROPS, mapCompany, sinceMs);

    const nowMs = Date.now();
    await updateFreshness("hubspot", total, "edge_function", { last_sync_ms: nowMs });
    await refreshViews();

    const result: SyncResult = {
      source: "hubspot", recordsUpserted: total, recordsSkipped: 0,
      durationMs: Date.now() - start,
    };
    console.log(`HubSpot sync complete: ${total} records in ${result.durationMs}ms`);
    return new Response(JSON.stringify(result), { headers: CORS_HEADERS });
  } catch (err) {
    await markError("hubspot", String(err));
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: CORS_HEADERS },
    );
  }
});

/** Fetch modified records for one object type and upsert. */
async function syncObjectType(
  apiKey: string,
  objectType: string,
  props: string[],
  mapFn: (r: Record<string, unknown>) => Record<string, unknown>,
  sinceMs: number | null,
): Promise<number> {
  const records = sinceMs
    ? await searchModified(apiKey, objectType, props, sinceMs)
    : await paginateAll(apiKey, objectType, props);

  if (records.length === 0) {
    console.log(`${objectType}: no modified records`);
    return 0;
  }

  const rows = records.map(mapFn);
  const table = objectType === "contacts" ? "contacts"
    : objectType === "deals" ? "deals" : "companies";
  const count = await batchUpsert(table, rows, "id");
  console.log(`${objectType}: upserted ${count} records`);
  return count;
}

/** Build the search body for HubSpot incremental search. */
function buildSearchBody(props: string[], sinceMs: number, after: number) {
  return {
    filterGroups: [{
      filters: [{
        propertyName: "lastmodifieddate", operator: "GTE",
        value: String(sinceMs),
      }],
    }],
    properties: props,
    limit: PAGE_LIMIT,
    after,
    sorts: [{ propertyName: "lastmodifieddate", direction: "ASCENDING" }],
  };
}

/** Search for records modified since a timestamp (incremental). */
async function searchModified(
  apiKey: string, objectType: string, props: string[], sinceMs: number,
): Promise<Record<string, unknown>[]> {
  const all: Record<string, unknown>[] = [];
  let after = 0;

  while (true) {
    await hubspotLimiter.acquire();
    const resp = await fetch(`${HUBSPOT_BASE}/crm/v3/objects/${objectType}/search`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(buildSearchBody(props, sinceMs, after)),
      signal: AbortSignal.timeout(15_000),
    });

    if (!resp.ok) { console.error(`HubSpot search ${objectType}: ${resp.status}`); break; }
    const data = await resp.json();
    all.push(...(data.results ?? []));
    const nextAfter = data.paging?.next?.after;
    if (!nextAfter) break;
    after = Number(nextAfter);
  }

  console.log(`searchModified(${objectType}): found ${all.length} records`);
  return all;
}

/** Paginate all records (full fetch — used on first run). */
async function paginateAll(
  apiKey: string,
  objectType: string,
  props: string[],
): Promise<Record<string, unknown>[]> {
  const all: Record<string, unknown>[] = [];
  let after: string | undefined;

  while (true) {
    await hubspotLimiter.acquire();
    const params = new URLSearchParams({
      properties: props.join(","),
      limit: String(PAGE_LIMIT),
    });
    if (after) params.set("after", after);

    const resp = await fetch(
      `${HUBSPOT_BASE}/crm/v3/objects/${objectType}?${params}`,
      {
        headers: { "Authorization": `Bearer ${apiKey}` },
        signal: AbortSignal.timeout(15_000),
      },
    );

    if (!resp.ok) {
      console.error(`HubSpot paginate ${objectType}: ${resp.status}`);
      break;
    }

    const data = await resp.json();
    all.push(...(data.results ?? []));

    after = data.paging?.next?.after;
    if (!after) break;
  }

  console.log(`paginateAll(${objectType}): fetched ${all.length} records`);
  return all;
}
