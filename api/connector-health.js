/**
 * Vercel Serverless Function — Connector Health Check
 * ====================================================
 * Checks health of all server-side connectors in parallel.
 * Returns { groq: true, hubspot: false, ... }
 *
 * GET /api/connector-health
 */

const { setCors, rateLimit, errorResponse } = require("./_helpers");

async function checkGroq() {
  var key = process.env.GROQ_API_KEY;
  if (!key) return false;
  try {
    var r = await fetch("https://api.groq.com/openai/v1/models", {
      headers: { Authorization: "Bearer " + key },
    });
    return r.ok;
  } catch (e) { return false; }
}

async function checkHubSpot() {
  var token = process.env.HUBSPOT_ACCESS_TOKEN;
  if (!token) return false;
  try {
    var r = await fetch("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", {
      headers: { Authorization: "Bearer " + token },
    });
    return r.ok;
  } catch (e) { return false; }
}

async function checkMonday() {
  var key = process.env.MONDAY_API_KEY;
  if (!key) return false;
  try {
    var r = await fetch("https://api.monday.com/v2", {
      method: "POST",
      headers: { Authorization: key, "Content-Type": "application/json" },
      body: JSON.stringify({ query: "{ me { name } }" }),
    });
    return r.ok;
  } catch (e) { return false; }
}

async function checkSupabase() {
  var url = process.env.SUPABASE_URL;
  var key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return false;
  try {
    var r = await fetch(url + "/rest/v1/?limit=0", {
      headers: { apikey: key, Authorization: "Bearer " + key },
    });
    return r.ok;
  } catch (e) { return false; }
}

async function checkGmail() {
  // Check if Gmail OAuth tokens exist in Supabase
  var url = process.env.SUPABASE_URL;
  var key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key || !process.env.GOOGLE_CLIENT_ID) return false;
  try {
    var r = await fetch(
      url + "/rest/v1/gmail_sessions?select=id&is_valid=eq.true&limit=1",
      { headers: { apikey: key, Authorization: "Bearer " + key } }
    );
    if (!r.ok) return false;
    var data = await r.json();
    return Array.isArray(data) && data.length > 0;
  } catch (e) { return false; }
}

async function checkCompaniesHouse() {
  try {
    var r = await fetch("https://api.company-information.service.gov.uk/search/companies?q=test&items_per_page=1");
    return r.status !== 500;
  } catch (e) { return false; }
}

async function checkWebScraper() {
  // Web scraper is available if Groq is available (uses AI to parse)
  return !!process.env.GROQ_API_KEY;
}

module.exports = async function handler(req, res) {
  setCors(req, res);

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "GET") return res.status(405).json({ error: "Method not allowed" });
  if (!rateLimit(req, 10)) return res.status(429).json({ error: "Too many requests" });

  try {
    var [groq, hubspot, monday, supabase, gmail, companiesHouse, webScraper] =
      await Promise.all([
        checkGroq(),
        checkHubSpot(),
        checkMonday(),
        checkSupabase(),
        checkGmail(),
        checkCompaniesHouse(),
        checkWebScraper(),
      ]);

    return res.status(200).json({
      groq: groq,
      hubspot: hubspot,
      monday: monday,
      supabase: supabase,
      gmail: gmail,
      "companies-house": companiesHouse,
      "web-scraper": webScraper,
    });
  } catch (err) {
    return errorResponse(res, 500, "Health check failed", err);
  }
};
