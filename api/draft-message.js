/**
 * Vercel Serverless Function — AI Message Drafting (Groq)
 * =======================================================
 * Generates hyper-personalised outreach messages using the prospect's
 * research brief, pillar context, and sequence step.
 *
 * POST body:
 *   { prospect (object), research_brief (object), sequence_step (1-4),
 *     channel ("linkedin"|"email"), conversation_history? (array),
 *     reply_to? (string — inbound message to reply to) }
 *
 * Environment variables:
 *   GROQ_API_KEY              — Groq API key
 *   SUPABASE_URL              — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — For storing drafted messages
 */

// ---- Supabase helpers ------------------------------------------------------

function supabaseHeaders() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  return {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    Prefer: "return=representation",
  };
}

function supabaseUrl(path) {
  const base =
    process.env.SUPABASE_URL || "https://rsvhflnpaexhzjhidgzk.supabase.co";
  return `${base}/rest/v1/${path}`;
}

// ---- Prompts ---------------------------------------------------------------

const DRAFT_SYSTEM_PROMPT = `You are a senior business development specialist at eComplete, drafting LinkedIn messages and emails to prospective clients. eComplete is a DTC growth capital and services firm that owns and operates brands like Naturecan across 40+ markets.

Your messages MUST:
1. Be hyper-personalized — reference specific details about the prospect's company, recent activity, or challenges
2. Lead with value, not a pitch — offer insights, share relevant content, or ask thoughtful questions
3. Be concise — LinkedIn DMs should be 50-120 words, emails 100-200 words
4. Sound human and conversational — avoid corporate jargon, buzzwords, or salesy language
5. Have a clear but soft call-to-action — never pressure, always give the prospect an easy out
6. Match the sequence step tone:
   - Step 1: Warm connection request / introduction
   - Step 2: Value-add follow-up (share insight/content)
   - Step 3: Social proof / case study reference
   - Step 4: Soft close / final gentle nudge

Rules:
- NEVER use phrases like 'I hope this finds you well', 'Just reaching out', 'I'd love to pick your brain', 'synergies', 'leverage', 'circle back'
- NEVER be pushy or create false urgency
- ALWAYS use the prospect's first name
- ALWAYS reference at least one specific detail from the research brief
- Keep the tone professional but approachable — like a peer, not a vendor
- Return ONLY the message text, nothing else.`;

const REPLY_SYSTEM_PROMPT = `You are a senior business development specialist at eComplete, drafting a reply to a prospect who has responded to your outreach. eComplete is a DTC growth capital and services firm.

Your reply MUST:
1. Directly address what the prospect said — never ignore their specific points
2. If they raised an objection, address it thoughtfully and honestly
3. If they asked a question, answer it concisely
4. If they showed interest, move the conversation forward with a specific next step
5. If they referred someone else, thank them warmly and ask for an introduction
6. If they said 'not now', respect it completely — offer to stay in touch without pressure
7. If they asked to unsubscribe, acknowledge immediately and confirm removal

Rules:
- Keep replies short: 40-100 words for LinkedIn, 80-150 for email
- Match their energy and formality level
- Be genuinely helpful, not transactional
- Reference specific things from the conversation to show you're paying attention
- Return ONLY the reply text, nothing else.`;

// ---- Sequence step labels --------------------------------------------------

const STEP_LABELS = {
  1: "Warm connection request / introduction",
  2: "Value-add follow-up (share insight or content)",
  3: "Social proof / case study reference",
  4: "Soft close / final gentle nudge",
};

// ---- Main handler ----------------------------------------------------------

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    const {
      prospect,
      research_brief,
      sequence_step,
      channel,
      conversation_history,
      reply_to,
    } = req.body || {};

    if (!prospect || !prospect.first_name) {
      return res.status(400).json({ error: "prospect object with first_name is required" });
    }

    const groqKey = process.env.GROQ_API_KEY;
    if (!groqKey) {
      return res.status(500).json({ error: "GROQ_API_KEY not configured" });
    }

    const isReply = !!reply_to;
    const systemPrompt = isReply ? REPLY_SYSTEM_PROMPT : DRAFT_SYSTEM_PROMPT;
    const step = sequence_step || 1;
    const ch = channel || "linkedin";

    // Build context prompt
    const parts = [];

    // Prospect identity
    parts.push("## Prospect");
    parts.push(`Name: ${prospect.first_name} ${prospect.last_name || ""}`);
    if (prospect.job_title) parts.push(`Title: ${prospect.job_title}`);
    if (prospect.company_name) parts.push(`Company: ${prospect.company_name}`);
    if (prospect.industry) parts.push(`Industry: ${prospect.industry}`);
    if (prospect.company_domain) parts.push(`Website: ${prospect.company_domain}`);

    // Research brief
    if (research_brief) {
      parts.push("\n## Research Brief");
      const rb = research_brief;

      if (rb.company_overview) {
        parts.push(`Company: ${rb.company_overview.description || ""}`);
        if (rb.company_overview.products_services?.length) {
          parts.push(
            `Products/Services: ${rb.company_overview.products_services.join(", ")}`,
          );
        }
        if (rb.company_overview.estimated_revenue)
          parts.push(`Revenue: ${rb.company_overview.estimated_revenue}`);
        if (rb.company_overview.employee_count)
          parts.push(`Employees: ${rb.company_overview.employee_count}`);
      }

      if (rb.pain_points?.length) {
        parts.push(`\nPain Points:\n${rb.pain_points.map((p) => `- ${p}`).join("\n")}`);
      }

      if (rb.conversation_starters?.length) {
        parts.push(
          `\nConversation Starters:\n${rb.conversation_starters.map((s) => `- ${s}`).join("\n")}`,
        );
      }

      if (rb.opportunity_assessment) {
        parts.push(`\nFit Rating: ${rb.opportunity_assessment.fit_rating}`);
        parts.push(`Reasoning: ${rb.opportunity_assessment.reasoning}`);
        if (rb.opportunity_assessment.recommended_services?.length) {
          parts.push(
            `Recommended Services: ${rb.opportunity_assessment.recommended_services.join(", ")}`,
          );
        }
      }

      if (rb.digital_presence) {
        parts.push(`\nWebsite Quality: ${rb.digital_presence.website_quality || "unknown"}`);
        if (rb.digital_presence.seo_visibility)
          parts.push(`SEO Visibility: ${rb.digital_presence.seo_visibility}`);
      }

      if (rb.key_people?.length) {
        parts.push(
          `\nKey People:\n${rb.key_people.map((p) => `- ${p.name} (${p.title}): ${p.background}`).join("\n")}`,
        );
      }
    }

    // Conversation history for replies
    if (isReply && conversation_history?.length) {
      parts.push("\n## Conversation History");
      for (const msg of conversation_history.slice(-6)) {
        const role = msg.direction === "outbound" ? "You" : prospect.first_name;
        parts.push(`${role}: ${msg.body}`);
      }
      parts.push(`\n## Latest inbound message to reply to:\n${reply_to}`);
    }

    // Sequence step and channel instructions
    if (!isReply) {
      parts.push(`\n## Instructions`);
      parts.push(`Channel: ${ch}`);
      parts.push(`Sequence Step: ${step} — ${STEP_LABELS[step] || "Custom step"}`);
      parts.push(
        `Word limit: ${ch === "linkedin" ? "50-120 words" : "100-200 words"}`,
      );
    } else {
      parts.push(`\n## Instructions`);
      parts.push(`Channel: ${ch}`);
      parts.push(
        `Word limit: ${ch === "linkedin" ? "40-100 words" : "80-150 words"}`,
      );
    }

    parts.push(
      "\nDraft the message now. Return ONLY the message text — no subject line, no greeting label, no explanation.",
    );

    const userPrompt = parts.join("\n");

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
          max_tokens: 1000,
          temperature: 0.7,
          messages: [
            { role: "system", content: systemPrompt },
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
    const draft =
      groqData.choices?.[0]?.message?.content?.trim() ||
      "Unable to generate a draft.";

    // Log AI usage
    if (process.env.SUPABASE_SERVICE_ROLE_KEY) {
      try {
        await fetch(supabaseUrl("outreach_ai_logs"), {
          method: "POST",
          headers: supabaseHeaders(),
          body: JSON.stringify({
            task: isReply ? "draft_reply" : "draft_message",
            provider: "groq",
            model: "llama-3.3-70b-versatile",
            input_tokens: groqData.usage?.prompt_tokens || 0,
            output_tokens: groqData.usage?.completion_tokens || 0,
            latency_ms: 0,
            prospect_id: prospect.id || null,
            success: true,
          }),
        });
      } catch (e) {
        /* non-critical */
      }
    }

    return res.status(200).json({
      draft,
      channel: ch,
      sequence_step: step,
      is_reply: isReply,
      model: "groq/llama-3.3-70b-versatile",
      tokens: {
        input: groqData.usage?.prompt_tokens || 0,
        output: groqData.usage?.completion_tokens || 0,
      },
    });
  } catch (err) {
    console.error("Unhandled error:", err);
    return res
      .status(500)
      .json({ error: "Internal error", detail: String(err) });
  }
};
