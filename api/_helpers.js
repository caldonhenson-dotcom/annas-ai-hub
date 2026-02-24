/**
 * Shared helpers for Vercel Serverless Functions
 * ================================================
 * CORS restriction, rate limiting, Supabase helpers, error handling.
 */

// ---- Allowed origins --------------------------------------------------------

const ALLOWED_ORIGINS = [
  "https://annas-ai-hub.vercel.app",
  "http://localhost:3000",
  "http://localhost:8001",
];

function setCors(req, res) {
  var origin = req.headers.origin || "";
  // Allow any *.vercel.app preview deploy
  if (
    ALLOWED_ORIGINS.includes(origin) ||
    /^https:\/\/annas-ai-hub[a-z0-9-]*\.vercel\.app$/.test(origin)
  ) {
    res.setHeader("Access-Control-Allow-Origin", origin);
  } else {
    // No CORS header = browser blocks cross-origin request
    res.setHeader("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0]);
  }
  res.setHeader("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

// ---- Rate limiting (per-instance sliding window) ----------------------------
// NOTE: Vercel cold-starts reset this. For production, use Upstash Redis.

var _buckets = {};
var WINDOW_MS = 60000; // 1 minute

function rateLimit(req, maxRequests) {
  var ip =
    (req.headers["x-forwarded-for"] || "").split(",")[0].trim() ||
    req.socket?.remoteAddress ||
    "unknown";
  var now = Date.now();
  var key = ip;

  if (!_buckets[key]) {
    _buckets[key] = [];
  }

  // Prune old entries
  _buckets[key] = _buckets[key].filter(function (t) {
    return t > now - WINDOW_MS;
  });

  if (_buckets[key].length >= maxRequests) {
    return false; // Rate limited
  }

  _buckets[key].push(now);

  // Cleanup stale IPs every 100 requests
  if (Math.random() < 0.01) {
    var staleKeys = Object.keys(_buckets).filter(function (k) {
      return (
        _buckets[k].length === 0 ||
        _buckets[k][_buckets[k].length - 1] < now - WINDOW_MS * 2
      );
    });
    staleKeys.forEach(function (k) {
      delete _buckets[k];
    });
  }

  return true;
}

// ---- Supabase helpers -------------------------------------------------------

function getSupabaseUrl() {
  var url = process.env.SUPABASE_URL;
  if (!url) {
    throw new Error("SUPABASE_URL environment variable is not configured");
  }
  return url;
}

function supabaseHeaders() {
  var key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  return {
    apikey: key,
    Authorization: "Bearer " + key,
    "Content-Type": "application/json",
    Prefer: "return=representation",
  };
}

function supabaseUrl(path) {
  return getSupabaseUrl() + "/rest/v1/" + path;
}

// ---- Error response ---------------------------------------------------------

function errorResponse(res, statusCode, publicMessage, internalErr) {
  if (internalErr) {
    console.error(publicMessage + ":", internalErr);
  }
  return res.status(statusCode).json({ error: publicMessage });
}

// ---- Input sanitisation for AI prompts --------------------------------------

function sanitizeForPrompt(text) {
  if (!text) return "";
  return String(text)
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "") // strip control chars
    .substring(0, 500); // cap length
}

// ---- Exports ----------------------------------------------------------------

module.exports = {
  setCors,
  rateLimit,
  getSupabaseUrl,
  supabaseHeaders,
  supabaseUrl,
  errorResponse,
  sanitizeForPrompt,
};
