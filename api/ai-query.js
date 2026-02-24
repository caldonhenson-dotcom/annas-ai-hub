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

const { buildContext } = require("./_summarise");

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
