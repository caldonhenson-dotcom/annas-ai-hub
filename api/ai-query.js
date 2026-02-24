/**
 * Vercel Serverless Function — AI Query (Groq)
 * =============================================
 * Receives a user question, fetches the latest dashboard metrics from
 * Supabase Storage, builds a summarised context, and calls Groq to
 * generate a concise answer.
 *
 * Environment variables required (set via Vercel dashboard or CLI):
 *   GROQ_API_KEY    — Groq API key
 *   SUPABASE_URL    — Supabase project URL
 */

// ---- Helpers ----------------------------------------------------------------

function jsonSafe(val, fallback = "N/A") {
  if (val === null || val === undefined) return fallback;
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}

function fmtCurrency(v) {
  if (v == null || isNaN(v)) return "\u00a30";
  const abs = Math.abs(v);
  if (abs >= 1e6) return `\u00a3${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `\u00a3${(v / 1e3).toFixed(0)}K`;
  return `\u00a3${Math.round(v).toLocaleString()}`;
}

function pct(v) {
  if (v == null || isNaN(v)) return "0%";
  return `${(v * 100).toFixed(1)}%`;
}

// ---- Data summarisation -----------------------------------------------------

function summariseHubSpot(data) {
  if (!data) return "";
  const p = data.pipeline_metrics || {};
  const l = data.lead_metrics || {};
  const a = data.activity_metrics || {};
  const c = data.contact_metrics || {};
  const i = data.insights || {};
  const re = data.reverse_engineering || {};
  const rc = data.record_counts || {};
  const fc = i.revenue_forecast || {};

  const byRep = (p.pipeline_by_rep || [])
    .slice(0, 8)
    .map((r) => `  - ${r.owner || r.rep || "Unknown"}: ${r.deal_count || 0} deals, ${fmtCurrency(r.total_value)}`)
    .join("\n");

  const stale = (p.stale_deals || [])
    .slice(0, 8)
    .map((d) => `  - "${d.name}" — ${d.days_in_stage || "?"} days in ${d.stage || "?"}${d.owner ? " (" + d.owner + ")" : ""}`)
    .join("\n");

  const actByRep = (Array.isArray(a.by_rep) ? a.by_rep : Object.entries(a.by_rep || {}).map(([name, stats]) => ({ owner: name, ...stats })))
    .slice(0, 8)
    .map((r) => `  - ${r.owner || r.rep}: ${r.total || 0} total (${r.calls || 0} calls, ${r.emails || 0} emails, ${r.meetings || 0} meetings)`)
    .join("\n");

  const stages = Object.entries(p.deals_by_stage || {})
    .map(([stage, info]) => {
      if (typeof info === "object") return `  - ${stage}: ${info.count || 0} deals, ${fmtCurrency(info.value)}`;
      return `  - ${stage}: ${info}`;
    })
    .join("\n");

  const srcEff = Object.entries(l.source_effectiveness || {})
    .slice(0, 6)
    .map(([src, info]) => `  - ${src}: ${info.total || 0} total, ${info.mqls || 0} MQLs`)
    .join("\n");

  return `## HubSpot CRM Data (as of ${data.generated_at || "unknown"})
Records: ${rc.contacts || 0} contacts, ${rc.companies || 0} companies, ${rc.deals || 0} deals

### Pipeline
- Total pipeline value: ${fmtCurrency(p.total_pipeline_value)}
- Weighted pipeline: ${fmtCurrency(p.weighted_pipeline_value)}
- Win rate: ${pct(p.win_rate)} (Won: ${p.won_deals_count || 0}, Lost: ${p.lost_deals_count || 0})
- Open deals: ${p.open_deals_count || 0}
- Avg deal size: ${fmtCurrency(p.avg_deal_size)}
- Avg sales cycle: ${p.avg_sales_cycle_days || "N/A"} days
- Pipeline coverage ratio: ${p.pipeline_coverage_ratio || "N/A"}
Deals by stage:
${stages || "  No stage data"}
Pipeline by rep:
${byRep || "  No rep data"}
Stale deals (in stage too long):
${stale || "  None"}

### Leads
- Total leads: ${l.total_leads || 0}
- New leads (30d): ${l.new_leads_30d || 0}
- Lead-to-MQL rate: ${pct(l.lead_to_mql_rate)}
- MQL-to-SQL rate: ${pct(l.mql_to_sql_rate)}
- Leads by source: ${jsonSafe(l.leads_by_source)}
- Lead status: ${jsonSafe(l.lead_status_distribution)}
Source effectiveness:
${srcEff || "  No data"}

### Activities
- Total activities: ${a.total_activities || 0}
- Breakdown: ${jsonSafe(a.activity_breakdown)}
- Touches per won deal: ${a.touches_per_won_deal || "N/A"}
Activity by rep:
${actByRep || "  No rep data"}

### Contacts
- Total: ${rc.contacts || 0}
- New (30d): ${c.new_contacts_30d || 0}
- Lifecycle stages: ${jsonSafe(c.lifecycle_stages)}

### Insights & Forecast
- 30-day forecast: ${fmtCurrency(fc.days_30)}
- 60-day forecast: ${fmtCurrency(fc.days_60)}
- 90-day forecast: ${fmtCurrency(fc.days_90)}
- Win/loss analysis: ${jsonSafe(i.win_loss_analysis)}
- Sales cycle trend: ${jsonSafe(i.sales_cycle_trend)}
- Deal size distribution: ${jsonSafe(i.deal_size_distribution)}

### Targets & Reverse Engineering
${jsonSafe(re)}`;
}

function summariseMonday(data) {
  if (!data) return "";
  const ma = data.ma_metrics || {};
  const ic = data.ic_metrics || {};
  const ai = data.ai_metrics || {};
  const ov = data.board_overview || {};

  const stageDistro = Object.entries(ma.stage_distribution || {})
    .map(([stage, count]) => `  - ${stage}: ${count}`)
    .join("\n");

  const staleMA = (ma.stale_projects || [])
    .slice(0, 8)
    .map((p) => `  - "${p.name}" — ${p.days_stale || "?"} days stale (${p.stage || "?"})${p.owner ? " — " + p.owner : ""}`)
    .join("\n");

  const owners = (ma.owner_summary || [])
    .slice(0, 8)
    .map((o) => `  - ${o.owner}: ${o.total || 0} projects (${o.active || 0} active)`)
    .join("\n");

  const topIC = (ic.top_scored || [])
    .slice(0, 5)
    .map((item) => `  - "${item.name}": score ${item.total_score || "?"} (${item.status || "?"})`)
    .join("\n");

  return `## Monday.com Data (as of ${data.generated_at || "unknown"})
Boards: ${ov.total_boards || 0} | Workspaces: ${ov.workspace_count || 0} | Total items: ${ov.total_items || 0}

### M&A Pipeline
- Total projects: ${ma.total_projects || 0}
- Active projects: ${ma.active_projects || 0}
Stage distribution:
${stageDistro || "  No stage data"}
Stale projects:
${staleMA || "  None"}
By owner:
${owners || "  No data"}

### IC Scorecards
- Total scored items: ${ic.total_scored_items || 0}
- Score stats: avg=${ic.score_stats?.avg || "?"}, min=${ic.score_stats?.min || "?"}, max=${ic.score_stats?.max || "?"}
Top scored:
${topIC || "  No data"}
- Category scores: ${jsonSafe(ic.category_scores)}
- Decision distribution: ${jsonSafe(ic.decision_distribution)}

### AI Workspace
- Total items: ${ai.total_items || 0}
- Status distribution: ${jsonSafe(ai.status_distribution)}
- Categories: ${Object.entries(ai.categories || {}).map(([cat, info]) => `${cat}: ${info?.count || 0}`).join(", ") || "None"}`;
}

function summariseQueue(data) {
  if (!data) return "";
  const s = data.summary || {};
  const items = data.items || [];

  const topCritical = items
    .filter((i) => i.priority === "critical")
    .slice(0, 8)
    .map((i) => `  - [${i.source}] "${i.title}" — ${i.category} → ${i.recommended_action || "review"}`)
    .join("\n");

  return `## Inbound Action Queue (as of ${data.generated_at || "unknown"})
- Total items: ${s.total_items || 0}
- By priority: ${jsonSafe(s.by_priority)}
- By category: ${jsonSafe(s.by_category)}
- By source: ${jsonSafe(s.by_source)}
Top critical items:
${topCritical || "  None"}`;
}

function buildContext(snapshots) {
  const parts = [];
  if (snapshots.hubspot_sales) parts.push(summariseHubSpot(snapshots.hubspot_sales.data));
  if (snapshots.monday) parts.push(summariseMonday(snapshots.monday.data));
  if (snapshots.inbound_queue) parts.push(summariseQueue(snapshots.inbound_queue.data));
  return parts.join("\n\n---\n\n");
}

// ---- System prompt ----------------------------------------------------------

const SYSTEM_PROMPT = `You are Anna, the AI assistant for the eComplete Sales & M&A Intelligence Dashboard. You help a 4-10 person sales team understand their CRM data, pipeline health, M&A projects, and activity metrics.

You have access to the latest data from:
- HubSpot CRM (contacts, deals, companies, activities, pipeline, forecasts)
- Monday.com (M&A pipeline, IC scorecards, AI workspace boards)
- Inbound queue (prioritised action items from all sources)

When answering:
- Be concise and specific — use actual numbers from the data
- Highlight trends, risks, and opportunities
- Suggest actionable next steps when relevant
- Use markdown formatting (bold, lists, tables) for clarity
- Use GBP (£) for all currency values
- If data is unavailable or unclear, say so honestly
- Keep responses focused — 2-4 paragraphs or a structured list
- When asked about a rep or project, pull together all relevant data points

You are NOT a general-purpose chatbot. Only answer questions related to the dashboard data, sales performance, M&A activity, and business operations.`;

// ---- Main handler -----------------------------------------------------------

const { setCors, rateLimit, getSupabaseUrl, errorResponse } = require("./_helpers");

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!rateLimit(req, 15)) {
    return res.status(429).json({ error: "Too many requests. Try again in a minute." });
  }

  try {
    const { question, history, report } = req.body;

    if (!question || typeof question !== "string" || question.trim().length === 0) {
      return res.status(400).json({ error: "Missing 'question' field" });
    }
    if (question.length > 2000) {
      return res.status(400).json({ error: "Question too long (max 2000 characters)" });
    }

    const groqKey = process.env.GROQ_API_KEY;
    if (!groqKey) {
      return errorResponse(res, 500, "AI service not configured");
    }

    let sbUrl;
    try { sbUrl = getSupabaseUrl(); } catch (e) {
      return errorResponse(res, 500, "Database not configured");
    }
    const storageBase = sbUrl + "/storage/v1/object/public/dashboard-data";

    // Fetch latest metrics from Supabase Storage
    const files = [
      { key: "hubspot_sales", file: "hubspot_sales_metrics.json" },
      { key: "monday", file: "monday_metrics.json" },
      { key: "inbound_queue", file: "inbound_queue.json" },
    ];

    const indexed = {};
    await Promise.all(
      files.map(async ({ key, file }) => {
        try {
          const r = await fetch(`${storageBase}/${file}`);
          if (r.ok) {
            const data = await r.json();
            indexed[key] = { data, generated_at: data.generated_at };
          }
        } catch (e) {
          console.warn(`Failed to fetch ${file}:`, e);
        }
      }),
    );

    // Build the data context
    const context = buildContext(indexed);

    // Build messages array with optional history
    const messages = [];

    if (Array.isArray(history)) {
      for (const msg of history.slice(-6)) {
        if (msg.role && msg.content) {
          messages.push({ role: msg.role, content: msg.content });
        }
      }
    }

    messages.push({
      role: "user",
      content: `Here is the latest dashboard data:\n\n${context}\n\n---\n\nQuestion: ${question.trim()}`,
    });

    // Call Groq (OpenAI-compatible API)
    const groqMessages = [
      { role: "system", content: SYSTEM_PROMPT },
      ...messages,
    ];

    const groqResp = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${groqKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        max_tokens: report ? 3000 : 1500,
        messages: groqMessages,
      }),
    });

    if (!groqResp.ok) {
      const errBody = await groqResp.text();
      console.error("Groq API error:", groqResp.status, errBody);
      return res.status(502).json({ error: "AI service error", status: groqResp.status });
    }

    const groqData = await groqResp.json();
    const answer = groqData.choices?.[0]?.message?.content || "I wasn't able to generate a response.";

    return res.status(200).json({
      answer,
      sources: Object.keys(indexed),
      generated_at: Object.fromEntries(
        Object.entries(indexed).map(([k, v]) => [k, v.generated_at]),
      ),
    });
  } catch (err) {
    return errorResponse(res, 500, "An unexpected error occurred", err);
  }
};
