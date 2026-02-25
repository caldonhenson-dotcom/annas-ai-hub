/**
 * Vercel Serverless Function — Claude Query (Anthropic)
 * =====================================================
 * Accepts a user-provided Claude API key from the client,
 * fetches dashboard context from Supabase, and proxies
 * the request to the Anthropic Messages API.
 *
 * Also supports a `test: true` mode to validate the API key.
 */

const { buildContext } = require("./_summarise");
const { setCors, rateLimit, getSupabaseUrl, errorResponse } = require("./_helpers");

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

const CLAUDE_API = "https://api.anthropic.com/v1/messages";
const CLAUDE_MODEL = "claude-sonnet-4-5-20250929";

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!rateLimit(req, 10)) {
    return res.status(429).json({ error: "Too many requests. Try again in a minute." });
  }

  try {
    const { question, history, report, test, apiKey } = req.body;

    // Validate API key presence
    if (!apiKey || typeof apiKey !== "string" || !apiKey.startsWith("sk-ant-")) {
      return res.status(400).json({ error: "Invalid Claude API key", valid: false });
    }

    // ---------- Test mode: validate key with a minimal request ----------
    if (test === true) {
      try {
        const testResp = await fetch(CLAUDE_API, {
          method: "POST",
          headers: {
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
          },
          body: JSON.stringify({
            model: CLAUDE_MODEL,
            max_tokens: 10,
            messages: [{ role: "user", content: "Say OK" }],
          }),
        });

        if (testResp.ok) {
          return res.status(200).json({ valid: true });
        }

        const errData = await testResp.json().catch(() => ({}));
        if (testResp.status === 401) {
          return res.status(200).json({ valid: false, error: "Invalid API key" });
        }
        return res.status(200).json({
          valid: false,
          error: errData.error?.message || "Key validation failed",
        });
      } catch (e) {
        return res.status(200).json({ valid: false, error: "Connection failed" });
      }
    }

    // ---------- Chat mode: full query ----------
    if (!question || typeof question !== "string" || question.trim().length === 0) {
      return res.status(400).json({ error: "Missing 'question' field" });
    }
    if (question.length > 2000) {
      return res.status(400).json({ error: "Question too long (max 2000 characters)" });
    }

    // Fetch dashboard context from Supabase
    let context = "";
    try {
      const sbUrl = getSupabaseUrl();
      const storageBase = sbUrl + "/storage/v1/object/public/dashboard-data";
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
      context = buildContext(indexed);
    } catch (e) {
      console.warn("Context fetch failed, proceeding without data:", e);
      context = "(Dashboard data currently unavailable)";
    }

    // Build messages
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

    // Call Anthropic Messages API
    const claudeResp = await fetch(CLAUDE_API, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: CLAUDE_MODEL,
        max_tokens: report ? 3000 : 1500,
        system: SYSTEM_PROMPT,
        messages: messages,
      }),
    });

    if (!claudeResp.ok) {
      const errBody = await claudeResp.text();
      console.error("Claude API error:", claudeResp.status, errBody);
      if (claudeResp.status === 401) {
        return res.status(401).json({ error: "Invalid API key" });
      }
      return res.status(502).json({ error: "Claude API error", status: claudeResp.status });
    }

    const claudeData = await claudeResp.json();
    const answer = claudeData.content?.[0]?.text || "I wasn't able to generate a response.";

    // Return usage for client-side token tracking
    const usage = claudeData.usage || {};

    return res.status(200).json({
      answer,
      usage: {
        input_tokens: usage.input_tokens || 0,
        output_tokens: usage.output_tokens || 0,
      },
    });
  } catch (err) {
    return errorResponse(res, 500, "An unexpected error occurred", err);
  }
};
