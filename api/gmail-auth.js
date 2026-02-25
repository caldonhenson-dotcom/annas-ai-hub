/**
 * Vercel Serverless Function — Gmail OAuth 2.0
 * =============================================
 * Handles: auth-url, callback, status, send, read
 *
 * Environment variables:
 *   GOOGLE_CLIENT_ID       — OAuth 2.0 client ID
 *   GOOGLE_CLIENT_SECRET   — OAuth 2.0 client secret
 *   GOOGLE_REDIRECT_URI    — callback URL
 *   ENCRYPTION_KEY         — 32-byte hex key for token encryption
 *   SUPABASE_URL           — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — Supabase service role key
 */

const crypto = require("crypto");
const { setCors, getSupabaseUrl, supabaseHeaders, errorResponse } = require("./_helpers");

const SCOPES = [
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/gmail.labels",
].join(" ");

// ---- AES-256-GCM encryption (same pattern as linkedin-session.js) --------

function encrypt(text, hexKey) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", Buffer.from(hexKey, "hex"), iv);
  let enc = cipher.update(text, "utf8", "hex");
  enc += cipher.final("hex");
  const tag = cipher.getAuthTag().toString("hex");
  return iv.toString("hex") + ":" + enc + ":" + tag;
}

function decrypt(blob, hexKey) {
  const [ivHex, encHex, tagHex] = blob.split(":");
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    Buffer.from(hexKey, "hex"),
    Buffer.from(ivHex, "hex")
  );
  decipher.setAuthTag(Buffer.from(tagHex, "hex"));
  let dec = decipher.update(encHex, "hex", "utf8");
  dec += decipher.final("utf8");
  return dec;
}

// ---- Supabase token storage -----------------------------------------------

async function storeTokens(userId, tokens, encKey) {
  const encrypted = encrypt(JSON.stringify(tokens), encKey);
  const url = getSupabaseUrl() + "/rest/v1/gmail_sessions";
  const body = { user_id: userId, tokens_encrypted: encrypted, updated_at: new Date().toISOString() };
  // Upsert by user_id
  await fetch(url + "?user_id=eq." + encodeURIComponent(userId), {
    method: "DELETE", headers: supabaseHeaders(),
  });
  await fetch(url, {
    method: "POST", headers: supabaseHeaders(), body: JSON.stringify(body),
  });
}

async function loadTokens(userId, encKey) {
  const url = getSupabaseUrl() + "/rest/v1/gmail_sessions?user_id=eq." + encodeURIComponent(userId) + "&limit=1";
  const r = await fetch(url, { headers: supabaseHeaders() });
  if (!r.ok) return null;
  const rows = await r.json();
  if (!rows || rows.length === 0) return null;
  try {
    return JSON.parse(decrypt(rows[0].tokens_encrypted, encKey));
  } catch (e) { return null; }
}

// ---- OAuth helpers --------------------------------------------------------

function getConfig() {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const redirectUri = process.env.GOOGLE_REDIRECT_URI;
  const encKey = process.env.ENCRYPTION_KEY;
  if (!clientId || !clientSecret || !redirectUri) return null;
  if (!encKey || encKey.length !== 64) return null;
  return { clientId, clientSecret, redirectUri, encKey };
}

async function exchangeCode(code, cfg) {
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code, client_id: cfg.clientId, client_secret: cfg.clientSecret,
      redirect_uri: cfg.redirectUri, grant_type: "authorization_code",
    }),
  });
  if (!r.ok) throw new Error("Token exchange failed: " + (await r.text()));
  return r.json();
}

async function refreshAccessToken(refreshToken, cfg) {
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      refresh_token: refreshToken, client_id: cfg.clientId,
      client_secret: cfg.clientSecret, grant_type: "refresh_token",
    }),
  });
  if (!r.ok) throw new Error("Token refresh failed");
  return r.json();
}

async function getValidToken(userId, cfg) {
  const tokens = await loadTokens(userId, cfg.encKey);
  if (!tokens) return null;
  // Check if access token is expired (with 5 min buffer)
  if (tokens.expires_at && Date.now() > tokens.expires_at - 300000) {
    if (!tokens.refresh_token) return null;
    const fresh = await refreshAccessToken(tokens.refresh_token, cfg);
    const updated = {
      access_token: fresh.access_token,
      refresh_token: tokens.refresh_token,
      expires_at: Date.now() + (fresh.expires_in || 3600) * 1000,
    };
    await storeTokens(userId, updated, cfg.encKey);
    return updated.access_token;
  }
  return tokens.access_token;
}

// ---- Main handler ---------------------------------------------------------

module.exports = async function handler(req, res) {
  setCors(req, res);
  if (req.method === "OPTIONS") return res.status(204).end();

  const action = req.query.action || req.body?.action;
  const cfg = getConfig();

  try {
    switch (action) {
      case "auth-url": {
        if (!cfg) return errorResponse(res, 500, "Gmail OAuth not configured");
        const params = new URLSearchParams({
          client_id: cfg.clientId, redirect_uri: cfg.redirectUri,
          response_type: "code", scope: SCOPES,
          access_type: "offline", prompt: "consent",
        });
        return res.json({ url: "https://accounts.google.com/o/oauth2/v2/auth?" + params });
      }

      case "callback": {
        if (!cfg) return errorResponse(res, 500, "Gmail OAuth not configured");
        const code = req.query.code;
        if (!code) return errorResponse(res, 400, "Missing authorization code");
        const tokens = await exchangeCode(code, cfg);
        const userId = "default"; // Single-tenant for now
        await storeTokens(userId, {
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token,
          expires_at: Date.now() + (tokens.expires_in || 3600) * 1000,
        }, cfg.encKey);
        // Return success page that closes the popup
        res.setHeader("Content-Type", "text/html");
        return res.send("<html><body><h2>Gmail connected!</h2>"
          + "<p>You can close this window.</p>"
          + "<script>window.opener&&window.opener.postMessage('gmail-connected','*');setTimeout(function(){window.close()},2000)</script>"
          + "</body></html>");
      }

      case "status": {
        if (!cfg) return res.json({ connected: false, reason: "not-configured" });
        const tokens = await loadTokens("default", cfg.encKey);
        return res.json({ connected: !!tokens, hasRefresh: !!(tokens && tokens.refresh_token) });
      }

      case "send": {
        if (req.method !== "POST") return errorResponse(res, 405, "POST required");
        if (!cfg) return errorResponse(res, 500, "Gmail not configured");
        const token = await getValidToken("default", cfg);
        if (!token) return errorResponse(res, 401, "Gmail not connected");
        const { to, subject, body } = req.body;
        if (!to || !subject) return errorResponse(res, 400, "Missing to or subject");
        // Build RFC 2822 message
        const raw = Buffer.from(
          "To: " + to + "\r\nSubject: " + subject + "\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + (body || "")
        ).toString("base64url");
        const gmailR = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
          method: "POST",
          headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
          body: JSON.stringify({ raw }),
        });
        if (!gmailR.ok) return errorResponse(res, 502, "Gmail send failed: " + (await gmailR.text()));
        return res.json({ success: true, messageId: (await gmailR.json()).id });
      }

      case "read": {
        if (req.method !== "POST") return errorResponse(res, 405, "POST required");
        if (!cfg) return errorResponse(res, 500, "Gmail not configured");
        const token2 = await getValidToken("default", cfg);
        if (!token2) return errorResponse(res, 401, "Gmail not connected");
        const q = req.body.query || "is:inbox";
        const max = Math.min(req.body.maxResults || 10, 20);
        const gmailR2 = await fetch(
          "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=" + encodeURIComponent(q) + "&maxResults=" + max,
          { headers: { Authorization: "Bearer " + token2 } }
        );
        if (!gmailR2.ok) return errorResponse(res, 502, "Gmail read failed");
        return res.json(await gmailR2.json());
      }

      default:
        return errorResponse(res, 400, "Unknown action: " + action);
    }
  } catch (err) {
    return errorResponse(res, 500, "Gmail auth error", err);
  }
};
