/**
 * Vercel Serverless Function — Prospect Research (Groq)
 * =====================================================
 * AI-powered deep research on a prospect. Calls Groq to generate
 * a structured research brief covering company, people, digital
 * presence, pain points, and conversation starters.
 *
 * POST body:
 *   { first_name, last_name, company_name, job_title, linkedin_url,
 *     company_domain, industry, company_size, prospect_id? }
 *
 * Environment variables:
 *   GROQ_API_KEY              — Groq API key
 *   SUPABASE_URL              — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — For storing research results
 */

const { setCors, rateLimit, supabaseHeaders, supabaseUrl, errorResponse, sanitizeForPrompt } = require("./_helpers");

// ---- Prompts ---------------------------------------------------------------

const RESEARCH_SYSTEM_PROMPT = `You are a senior B2B research analyst at eComplete, a DTC growth capital and services firm. Your job is to produce actionable intelligence briefs on prospective clients.

Your research brief MUST cover:
1. Company Overview — what they sell, market position, estimated revenue range, funding history
2. Key People — founders, C-suite, decision-makers and their backgrounds
3. Digital Presence — website quality, social media following, ad spend signals, SEO visibility
4. Pain Points — likely operational challenges based on their size, industry, and growth stage
5. Opportunity Assessment — why eComplete's services would be valuable to them
6. Conversation Starters — 3 specific, personalized hooks for outreach based on recent news, posts, or company activity
7. Risk Factors — any red flags (declining traffic, legal issues, negative reviews, funding trouble)

Rules:
- Be specific and data-driven. Avoid generic statements.
- If you can't find information on a topic, say so explicitly rather than guessing.
- Always cite the reasoning behind your assessments.
- Output valid JSON matching the schema provided.
- Keep the brief concise but comprehensive — aim for 400-600 words total.`;

const OUTPUT_SCHEMA = JSON.stringify(
  {
    company_overview: {
      description: "string",
      products_services: ["string"],
      estimated_revenue: "string",
      funding_history: "string",
      founded_year: "string or null",
      headquarters: "string or null",
      employee_count: "string or null",
    },
    key_people: [
      {
        name: "string",
        title: "string",
        background: "string",
        linkedin_url: "string or null",
      },
    ],
    digital_presence: {
      website_quality: "string (poor/average/good/excellent)",
      social_following: {
        linkedin: "string or null",
        instagram: "string or null",
        tiktok: "string or null",
      },
      seo_visibility: "string",
      ad_spend_signals: "string",
    },
    pain_points: ["string"],
    opportunity_assessment: {
      fit_rating: "string (low/medium/high/very high)",
      reasoning: "string",
      recommended_pillar: "string",
      recommended_services: ["string"],
    },
    conversation_starters: ["string"],
    risk_factors: ["string"],
    research_confidence: "string (low/medium/high)",
    sources_consulted: ["string"],
  },
  null,
  2,
);

// ---- Main handler ----------------------------------------------------------

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!rateLimit(req, 8)) {
    return res.status(429).json({ error: "Too many requests. Try again in a minute." });
  }

  try {
    const {
      first_name,
      last_name,
      company_name,
      job_title,
      linkedin_url,
      company_domain,
      industry,
      company_size,
      prospect_id,
      pillar_context,
    } = req.body || {};

    if (!company_name && !first_name) {
      return res
        .status(400)
        .json({ error: "Provide at least first_name or company_name" });
    }

    const groqKey = process.env.GROQ_API_KEY;
    if (!groqKey) {
      return errorResponse(res, 500, "AI service not configured");
    }

    // Build user prompt with prospect details
    const details = [];
    if (first_name || last_name)
      details.push(`Name: ${first_name || ""} ${last_name || ""}`.trim());
    if (job_title) details.push(`Title: ${job_title}`);
    if (company_name) details.push(`Company: ${company_name}`);
    if (company_domain) details.push(`Website: ${company_domain}`);
    if (industry) details.push(`Industry: ${industry}`);
    if (company_size) details.push(`Company Size: ${company_size}`);
    if (linkedin_url) details.push(`LinkedIn: ${linkedin_url}`);

    let userPrompt = `Research this prospect and their company:\n\n${details.join("\n")}`;

    if (pillar_context) {
      userPrompt += `\n\nTarget Pillar Context:\n${typeof pillar_context === "string" ? pillar_context : JSON.stringify(pillar_context)}`;
    }

    userPrompt += `\n\nReturn your analysis as valid JSON matching this schema:\n${OUTPUT_SCHEMA}`;

    // Call Groq
    const groqResp = await fetch(
      "https://api.groq.com/openai/v1/chat/completions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${groqKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "llama-3.3-70b-versatile",
          max_tokens: 3000,
          temperature: 0.3,
          response_format: { type: "json_object" },
          messages: [
            { role: "system", content: RESEARCH_SYSTEM_PROMPT },
            { role: "user", content: userPrompt },
          ],
        }),
      },
    );

    if (!groqResp.ok) {
      const errBody = await groqResp.text();
      console.error("Groq API error:", groqResp.status, errBody);
      return res
        .status(502)
        .json({ error: "AI service error", status: groqResp.status });
    }

    const groqData = await groqResp.json();
    const rawContent =
      groqData.choices?.[0]?.message?.content || "{}";

    // Parse JSON from AI response (handle markdown wrappers)
    let research;
    try {
      let cleaned = rawContent.trim();
      // Strip markdown code fences if present
      if (cleaned.startsWith("```")) {
        cleaned = cleaned.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
      }
      research = JSON.parse(cleaned);
    } catch (e) {
      console.error("JSON parse error:", e, "Raw:", rawContent.substring(0, 200));
      return res.status(502).json({
        error: "AI returned invalid response — please retry",
      });
    }

    // Store in Supabase if prospect_id provided (validate UUID/integer format)
    const safeProspectId = prospect_id && /^[a-f0-9-]{1,64}$/i.test(String(prospect_id)) ? String(prospect_id) : null;
    if (safeProspectId && process.env.SUPABASE_SERVICE_ROLE_KEY) {
      try {
        await fetch(
          supabaseUrl(`outreach_prospects?id=eq.${safeProspectId}`),
          {
            method: "PATCH",
            headers: supabaseHeaders(),
            body: JSON.stringify({
              research_brief: research,
              research_status: "complete",
              researched_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            }),
          },
        );
      } catch (e) {
        console.warn("Failed to store research in Supabase:", e);
      }
    }

    // Log AI usage
    if (process.env.SUPABASE_SERVICE_ROLE_KEY) {
      try {
        await fetch(supabaseUrl("outreach_ai_logs"), {
          method: "POST",
          headers: supabaseHeaders(),
          body: JSON.stringify({
            task: "research",
            provider: "groq",
            model: "llama-3.3-70b-versatile",
            input_tokens: groqData.usage?.prompt_tokens || 0,
            output_tokens: groqData.usage?.completion_tokens || 0,
            latency_ms: 0,
            prospect_id: safeProspectId,
            success: true,
          }),
        });
      } catch (e) {
        /* non-critical */
      }
    }

    return res.status(200).json({
      research,
      prospect_id: safeProspectId,
      model: "groq/llama-3.3-70b-versatile",
      tokens: {
        input: groqData.usage?.prompt_tokens || 0,
        output: groqData.usage?.completion_tokens || 0,
      },
    });
  } catch (err) {
    return errorResponse(res, 500, "An unexpected error occurred", err);
  }
};
