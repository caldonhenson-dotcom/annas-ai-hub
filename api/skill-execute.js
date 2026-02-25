/**
 * Vercel Serverless Function — Skill Execute
 * ============================================
 * Routes skill execution requests to the appropriate handler:
 *   - structured: Groq AI with JSON output mode
 *   - api-call:   Proxies whitelisted API calls (HubSpot, Monday, Supabase)
 *
 * POST body:
 *   { _type: "structured"|"api-call", ...handlerFields }
 *
 * Environment variables:
 *   GROQ_API_KEY              — Groq API key
 *   HUBSPOT_ACCESS_TOKEN      — HubSpot private app token
 *   MONDAY_API_KEY            — Monday.com API key
 *   SUPABASE_URL              — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — Supabase service role key
 */

const { setCors, rateLimit, supabaseHeaders, supabaseUrl, errorResponse, sanitizeForPrompt } = require("./_helpers");

// ---- Whitelisted API paths (prevent arbitrary external calls) ---------------

const HUBSPOT_WHITELIST = [
  /^\/crm\/v3\/objects\/(contacts|companies|deals)/,
  /^\/crm\/v3\/pipelines/,
  /^\/crm\/v3\/associations/,
];

const MONDAY_WHITELIST = [
  /^\/v2$/, // Monday GraphQL endpoint
];

// ---- Structured AI handler --------------------------------------------------

async function handleStructured(body, res) {
  const { question, schema, systemPrompt, maxTokens } = body;

  if (!question || typeof question !== "string") {
    return res.status(400).json({ error: "Missing 'question' for structured query" });
  }

  const groqKey = process.env.GROQ_API_KEY;
  if (!groqKey) {
    return errorResponse(res, 500, "AI service not configured");
  }

  const system = systemPrompt ||
    "You are an AI assistant for eComplete, an M&A advisory firm. " +
    "Return your response as valid JSON matching the requested schema. " +
    "Be precise, data-driven, and concise.";

  const messages = [
    { role: "system", content: system },
    { role: "user", content: question + (schema ? "\n\nReturn JSON matching this schema:\n" + JSON.stringify(schema) : "") },
  ];

  const groqResp = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + groqKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "llama-3.3-70b-versatile",
      max_tokens: maxTokens || 2000,
      temperature: 0.3,
      response_format: schema ? { type: "json_object" } : undefined,
      messages: messages,
    }),
  });

  if (!groqResp.ok) {
    const errBody = await groqResp.text();
    console.error("Groq API error:", groqResp.status, errBody);
    return res.status(502).json({ error: "AI service error", status: groqResp.status });
  }

  const groqData = await groqResp.json();
  var raw = groqData.choices?.[0]?.message?.content || "{}";

  // Try to parse as JSON, fall back to raw text
  var parsed;
  try { parsed = JSON.parse(raw); } catch (e) { parsed = raw; }

  return res.status(200).json({
    result: parsed,
    model: "groq/llama-3.3-70b-versatile",
    tokens: {
      input: groqData.usage?.prompt_tokens || 0,
      output: groqData.usage?.completion_tokens || 0,
    },
  });
}

// ---- API call proxy handler -------------------------------------------------

async function handleApiCall(body, res) {
  const { target, path, method, query, action } = body;

  if (!target) {
    return res.status(400).json({ error: "Missing 'target' for api-call" });
  }

  // HubSpot proxy
  if (target === "hubspot") {
    const token = process.env.HUBSPOT_ACCESS_TOKEN;
    if (!token) return errorResponse(res, 500, "HubSpot not configured");
    if (!path) return res.status(400).json({ error: "Missing 'path' for HubSpot call" });

    var allowed = HUBSPOT_WHITELIST.some(function (re) { return re.test(path); });
    if (!allowed) return res.status(403).json({ error: "API path not allowed" });

    var url = "https://api.hubapi.com" + path;
    if (query) url += "?" + new URLSearchParams(query).toString();

    var hsResp = await fetch(url, {
      method: method || "GET",
      headers: {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
      },
      body: ["POST", "PUT", "PATCH"].includes(method) ? JSON.stringify(body.body || {}) : undefined,
    });

    var hsData;
    try { hsData = await hsResp.json(); } catch (e) { hsData = { status: hsResp.status }; }
    return res.status(hsResp.ok ? 200 : hsResp.status).json(hsData);
  }

  // Monday.com proxy
  if (target === "monday") {
    var mondayKey = process.env.MONDAY_API_KEY;
    if (!mondayKey) return errorResponse(res, 500, "Monday.com not configured");

    var mondayResp = await fetch("https://api.monday.com/v2", {
      method: "POST",
      headers: {
        Authorization: mondayKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: body.query }),
    });

    var mondayData;
    try { mondayData = await mondayResp.json(); } catch (e) { mondayData = { status: mondayResp.status }; }
    return res.status(mondayResp.ok ? 200 : mondayResp.status).json(mondayData);
  }

  // Supabase proxy (for skill-specific actions)
  if (target === "supabase") {
    if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
      return errorResponse(res, 500, "Database not configured");
    }

    if (action === "enroll") {
      // Enroll prospects in sequence
      var rows = (body.prospects || []).map(function (pid) {
        return { prospect_id: pid.trim(), sequence_type: body.sequence || "ma-intro", status: "active", step: 1 };
      });
      var enrollResp = await fetch(supabaseUrl("outreach_sequences"), {
        method: "POST",
        headers: supabaseHeaders(),
        body: JSON.stringify(rows),
      });
      var enrollData;
      try { enrollData = await enrollResp.json(); } catch (e) { enrollData = {}; }
      return res.status(enrollResp.ok ? 200 : enrollResp.status).json({ enrolled: rows.length, data: enrollData });
    }

    if (action === "recalculate_scores") {
      // Placeholder: fetch prospects and return for client-side scoring
      var scoreResp = await fetch(supabaseUrl("prospects?select=id,name,company&limit=50"), {
        headers: supabaseHeaders(),
      });
      var prospects;
      try { prospects = await scoreResp.json(); } catch (e) { prospects = []; }
      return res.status(200).json({ prospects: prospects, message: "Prospects ready for scoring" });
    }

    if (action === "sync_inbox") {
      return res.status(200).json({ synced: 0, message: "LinkedIn inbox sync requires LinkedIn integration" });
    }

    return res.status(400).json({ error: "Unknown Supabase action: " + action });
  }

  return res.status(400).json({ error: "Unknown target: " + target });
}

// ---- Main handler -----------------------------------------------------------

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!rateLimit(req, 20)) {
    return res.status(429).json({ error: "Too many requests. Try again in a minute." });
  }

  try {
    var body = req.body || {};
    var type = body._type;

    if (type === "structured") {
      return await handleStructured(body, res);
    }

    if (type === "api-call") {
      return await handleApiCall(body, res);
    }

    return res.status(400).json({ error: "Invalid _type. Expected 'structured' or 'api-call'" });
  } catch (err) {
    return errorResponse(res, 500, "Skill execution failed", err);
  }
};
