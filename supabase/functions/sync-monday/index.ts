/**
 * sync-monday — Incremental Monday.com M&A board sync.
 * Ports the Python check_board_activity() + fetch_board_items() pattern.
 * Only fetches boards that have had recent activity (dormancy check).
 *
 * Deploy: supabase functions deploy sync-monday --no-verify-jwt
 * Secrets: MONDAY_API_KEY
 */

import { CORS_HEADERS, handleCors } from "../_shared/cors.ts";
import {
  checkFreshness, batchUpsert, updateFreshness,
  markError, refreshViews,
} from "../_shared/sync-base.ts";
import { mondayLimiter } from "../_shared/rate-limiter.ts";
import type { SyncResult } from "../_shared/types.ts";

const TTL_MINUTES = 240; // 4 hours
const MONDAY_API = "https://api.monday.com/v2";

Deno.serve(async (req: Request) => {
  const cors = handleCors(req);
  if (cors) return cors;

  const start = Date.now();
  const apiKey = Deno.env.get("MONDAY_API_KEY");
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "Missing MONDAY_API_KEY" }),
      { status: 500, headers: CORS_HEADERS },
    );
  }

  try {
    const freshness = await checkFreshness("monday", TTL_MINUTES);
    if (!freshness.isStale) {
      return new Response(JSON.stringify({
        source: "monday", recordsUpserted: 0, recordsSkipped: 0,
        durationMs: Date.now() - start,
      }), { headers: CORS_HEADERS });
    }

    const { upserted, skipped } = await syncAllBoards(apiKey, freshness.lastFetchAt);
    await updateFreshness("monday", upserted, "edge_function");
    await refreshViews();

    const result: SyncResult = {
      source: "monday", recordsUpserted: upserted,
      recordsSkipped: skipped, durationMs: Date.now() - start,
    };
    console.log(`Monday sync: ${upserted} upserted, ${skipped} dormant boards`);
    return new Response(JSON.stringify(result), { headers: CORS_HEADERS });
  } catch (err) {
    await markError("monday", String(err));
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: CORS_HEADERS },
    );
  }
});

/** Sync all boards — fetch active ones, skip dormant. */
async function syncAllBoards(apiKey: string, lastFetchAt: string | null) {
  const boards = await fetchBoards(apiKey);
  let upserted = 0;
  let skipped = 0;

  for (const board of boards) {
    if (await isBoardDormant(apiKey, board.id, lastFetchAt)) { skipped++; continue; }
    const items = await fetchBoardItems(apiKey, board.id);
    const rows = items.map((item) => mapProject(item, board));
    upserted += await batchUpsert("monday_projects", rows, "id");
  }

  await batchUpsert("monday_boards", boards.map(mapBoard), "id");
  return { upserted, skipped };
}

/** Execute a Monday.com GraphQL query. */
async function gql(apiKey: string, query: string, vars?: Record<string, unknown>) {
  await mondayLimiter.acquire();
  const body: Record<string, unknown> = { query };
  if (vars) body.variables = vars;

  const resp = await fetch(MONDAY_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": apiKey,
      "API-Version": "2024-10",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!resp.ok) throw new Error(`Monday API ${resp.status}`);
  const json = await resp.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
}

/** Fetch all boards. */
async function fetchBoards(apiKey: string) {
  const data = await gql(apiKey, `query { boards(limit:200) { id name state } }`);
  return (data?.boards ?? []) as Array<{ id: string; name: string; state: string }>;
}

/** Check if board has been dormant since last fetch (1 cheap API call). */
async function isBoardDormant(
  apiKey: string, boardId: string, lastFetchAt: string | null,
): Promise<boolean> {
  if (!lastFetchAt) return false; // First sync — always fetch
  const data = await gql(apiKey,
    `query($id:[ID!]!) { boards(ids:$id) { activity_logs(limit:1) { created_at } } }`,
    { id: [boardId] },
  );
  const logs = data?.boards?.[0]?.activity_logs ?? [];
  if (logs.length === 0) return true; // No activity ever
  return logs[0].created_at < lastFetchAt;
}

/** Fetch all items from a board with cursor pagination. */
async function fetchBoardItems(apiKey: string, boardId: string) {
  const items: Record<string, unknown>[] = [];
  // First page
  const first = await gql(apiKey,
    `query($id:[ID!]!) { boards(ids:$id) { items_page(limit:100) { cursor items { id name state created_at updated_at group { id title } column_values { id text } } } } }`,
    { id: [boardId] },
  );
  const page = first?.boards?.[0]?.items_page;
  items.push(...(page?.items ?? []));
  let cursor = page?.cursor;

  while (cursor) {
    const next = await gql(apiKey,
      `query($c:String!) { next_items_page(cursor:$c,limit:100) { cursor items { id name state created_at updated_at group { id title } column_values { id text } } } }`,
      { c: cursor },
    );
    const np = next?.next_items_page;
    items.push(...(np?.items ?? []));
    cursor = np?.cursor;
  }
  return items;
}

/** Map a Monday item to monday_projects table row. */
function mapProject(
  item: Record<string, unknown>,
  board: { id: string; name: string },
): Record<string, unknown> {
  const cols = (item.column_values ?? []) as Array<{ id: string; text: string }>;
  const colMap: Record<string, string> = {};
  for (const c of cols) colMap[c.id] = c.text ?? "";
  const group = item.group as { title?: string } | undefined;

  return {
    id: String(item.id),
    name: item.name,
    board_id: board.id,
    board_name: board.name,
    stage: colMap["status"] || group?.title || null,
    status: colMap["status"] || null,
    owner: colMap["person"] || colMap["owner"] || "Unassigned",
    is_active: item.state !== "archived" && item.state !== "deleted",
    group_name: group?.title || null,
    created_at: item.created_at,
    updated_at: item.updated_at,
    fetched_at: new Date().toISOString(),
  };
}

/** Map a board to monday_boards table row. */
function mapBoard(board: { id: string; name: string; state: string }) {
  return {
    id: board.id,
    name: board.name,
    state: board.state,
    fetched_at: new Date().toISOString(),
  };
}
