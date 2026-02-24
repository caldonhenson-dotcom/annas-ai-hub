/**
 * Vercel Serverless Function — Outreach Dashboard Data
 * ====================================================
 * Returns live outreach data from Supabase for the dashboard.
 * Fetches prospects, messages, approvals and formats them for display.
 *
 * GET — Returns all outreach dashboard data
 *
 * Environment variables:
 *   SUPABASE_URL              — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — Supabase service role key
 */

const { setCors, rateLimit, supabaseHeaders, supabaseUrl, errorResponse } = require("./_helpers");

// ---- Main handler ----------------------------------------------------------

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!rateLimit(req, 20)) {
    return res.status(429).json({ error: "Too many requests. Try again in a minute." });
  }

  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!svcKey) {
    return res.status(200).json({ live: false, reason: "not_configured" });
  }

  try {
    const headers = supabaseHeaders();

    // Fetch prospects, messages, and approvals in parallel
    const [prospectsResp, messagesResp, approvalsResp, logsResp] = await Promise.all([
      fetch(supabaseUrl("outreach_prospects?select=*&order=lead_score.desc&limit=100"), { headers }).catch(() => null),
      fetch(supabaseUrl("outreach_messages?select=*&order=created_at.desc&limit=50"), { headers }).catch(() => null),
      fetch(supabaseUrl("outreach_approvals?select=*&order=created_at.desc&limit=20"), { headers }).catch(() => null),
      fetch(supabaseUrl("outreach_ai_logs?select=*&order=created_at.desc&limit=100"), { headers }).catch(() => null),
    ]);

    const prospects = prospectsResp?.ok ? await prospectsResp.json() : [];
    const messages = messagesResp?.ok ? await messagesResp.json() : [];
    const approvals = approvalsResp?.ok ? await approvalsResp.json() : [];
    const logs = logsResp?.ok ? await logsResp.json() : [];

    // If no data at all, signal that the frontend should use demo data
    if (prospects.length === 0 && messages.length === 0) {
      return res.status(200).json({ live: false, reason: "no_data" });
    }

    // Build funnel from prospect statuses
    const statusCounts = {};
    prospects.forEach(function (p) {
      var s = (p.status || "new").toLowerCase();
      statusCounts[s] = (statusCounts[s] || 0) + 1;
    });

    const funnel = {
      total_prospects: prospects.length,
      researched: prospects.filter(function (p) { return p.research_status === "complete"; }).length,
      enrolled: statusCounts.enrolled || statusCounts.active || 0,
      contacted: statusCounts.contacted || 0,
      replied: statusCounts.replied || 0,
      interested: statusCounts.interested || 0,
      converted: statusCounts.converted || 0,
    };

    // Build leaderboard from top-scored prospects
    const leaderboard = prospects.slice(0, 10).map(function (p) {
      return {
        id: p.id,
        name: ((p.first_name || "") + " " + (p.last_name || "")).trim(),
        company: p.company_name || "",
        pillar: p.pillar || "",
        lead_score: p.lead_score || 0,
        fit_score: p.fit_score || 0,
        engagement_score: p.engagement_score || 0,
        status: p.status || "new",
        last_contact: p.last_contacted_at || "",
      };
    });

    // Build approvals list from pending approvals
    const approvalsList = approvals.map(function (a) {
      var prospect = prospects.find(function (p) { return p.id === a.prospect_id; }) || {};
      return {
        id: a.id,
        prospect: ((prospect.first_name || "") + " " + (prospect.last_name || "")).trim() || "Unknown",
        company: prospect.company_name || "",
        pillar: prospect.pillar || "",
        channel: a.channel || "linkedin",
        preview: (a.message_body || "").substring(0, 150),
        model: a.ai_model || "AI",
        submitted: a.created_at || "",
      };
    });

    // Build AI usage from logs
    const aiBreakdown = {};
    logs.forEach(function (l) {
      var key = (l.provider || "unknown") + "|" + (l.task || "unknown");
      if (!aiBreakdown[key]) {
        aiBreakdown[key] = { provider: l.provider, task: l.task, calls: 0, tokens: 0 };
      }
      aiBreakdown[key].calls += 1;
      aiBreakdown[key].tokens += (l.input_tokens || 0) + (l.output_tokens || 0);
    });

    return res.status(200).json({
      live: true,
      generated_at: new Date().toISOString(),
      funnel: funnel,
      leaderboard: leaderboard,
      approvals: approvalsList,
      ai_usage: {
        total_calls: logs.length,
        breakdown: Object.values(aiBreakdown),
      },
      prospect_count: prospects.length,
    });
  } catch (err) {
    return errorResponse(res, 500, "An unexpected error occurred", err);
  }
};
