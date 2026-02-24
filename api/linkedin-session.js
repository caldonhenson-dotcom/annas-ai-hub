/**
 * Vercel Serverless Function — LinkedIn Session Management
 * ========================================================
 * Handles LinkedIn authentication via li_at session cookie capture.
 *
 *   POST   — Validate + encrypt + store LinkedIn session
 *   GET    — Check current session status
 *   DELETE — Invalidate (logout)
 *
 * Environment variables:
 *   SUPABASE_URL              — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — Supabase service role key (write access)
 *   LINKEDIN_ENCRYPTION_KEY   — 32-byte hex string for AES-256-GCM
 */

const crypto = require("crypto");

// ---- Encryption helpers ----------------------------------------------------

function encrypt(text, keyHex) {
  const key = Buffer.from(keyHex, "hex");
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  let encrypted = cipher.update(text, "utf8", "hex");
  encrypted += cipher.final("hex");
  const tag = cipher.getAuthTag().toString("hex");
  return iv.toString("hex") + ":" + encrypted + ":" + tag;
}

function decrypt(blob, keyHex) {
  const key = Buffer.from(keyHex, "hex");
  const [ivHex, encHex, tagHex] = blob.split(":");
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    key,
    Buffer.from(ivHex, "hex"),
  );
  decipher.setAuthTag(Buffer.from(tagHex, "hex"));
  let decrypted = decipher.update(encHex, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return decrypted;
}

// ---- Supabase REST helpers -------------------------------------------------

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

// ---- LinkedIn validation ---------------------------------------------------

async function validateLinkedIn(liAt, csrfToken) {
  const resp = await fetch(
    "https://www.linkedin.com/voyager/api/me",
    {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        Accept: "application/vnd.linkedin.normalized+json+2.1",
        "Accept-Language": "en-US,en;q=0.9",
        "x-restli-protocol-version": "2.0.0",
        "x-li-lang": "en_US",
        "csrf-token": csrfToken,
        Cookie: `li_at=${liAt}; JSESSIONID="${csrfToken}"`,
      },
    },
  );

  if (!resp.ok) {
    return { valid: false, status: resp.status };
  }

  const data = await resp.json();
  // Extract profile info from the response
  const mini =
    data.included?.find((i) => i.$type === "com.linkedin.voyager.identity.shared.MiniProfile") ||
    data.miniProfile ||
    {};
  const firstName = mini.firstName || data.firstName || "";
  const lastName = mini.lastName || data.lastName || "";
  const profileId =
    mini.publicIdentifier ||
    mini.dashEntityUrn?.split(":").pop() ||
    data.publicIdentifier ||
    "";

  return {
    valid: true,
    display_name: `${firstName} ${lastName}`.trim() || "LinkedIn User",
    profile_id: profileId,
  };
}

// ---- Handlers --------------------------------------------------------------

async function handleAuth(req, res) {
  const { li_at, csrf_token } = req.body || {};

  if (!li_at || typeof li_at !== "string" || li_at.length < 50) {
    return res
      .status(400)
      .json({ error: "Invalid li_at cookie (must be 50+ characters)" });
  }
  // Strip surrounding quotes from JSESSIONID if present
  const cleanCsrf = (csrf_token || "").replace(/^"|"$/g, "");
  if (!cleanCsrf || cleanCsrf.length < 10) {
    return res
      .status(400)
      .json({ error: "Invalid JSESSIONID / csrf_token (must be 10+ characters)" });
  }

  const encKey = process.env.LINKEDIN_ENCRYPTION_KEY;
  if (!encKey || encKey.length !== 64) {
    return res
      .status(500)
      .json({ error: "LINKEDIN_ENCRYPTION_KEY not configured (need 32-byte hex)" });
  }

  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!svcKey) {
    return res
      .status(500)
      .json({ error: "SUPABASE_SERVICE_ROLE_KEY not configured" });
  }

  // Validate against LinkedIn
  const validation = await validateLinkedIn(li_at, cleanCsrf);
  if (!validation.valid) {
    return res.status(401).json({
      error: "LinkedIn session invalid or expired",
      linkedin_status: validation.status,
    });
  }

  // Encrypt credentials
  const encLiAt = encrypt(li_at, encKey);
  const encCsrf = encrypt(cleanCsrf, encKey);

  // Invalidate old sessions
  await fetch(
    supabaseUrl("linkedin_sessions?is_valid=eq.true"),
    {
      method: "PATCH",
      headers: supabaseHeaders(),
      body: JSON.stringify({ is_valid: false }),
    },
  );

  // Store new session
  const expiresAt = new Date(
    Date.now() + 365 * 24 * 60 * 60 * 1000,
  ).toISOString();
  const insertResp = await fetch(supabaseUrl("linkedin_sessions"), {
    method: "POST",
    headers: supabaseHeaders(),
    body: JSON.stringify({
      li_at: encLiAt,
      csrf_token: encCsrf,
      profile_id: validation.profile_id,
      display_name: validation.display_name,
      is_valid: true,
      expires_at: expiresAt,
      last_validated: new Date().toISOString(),
    }),
  });

  if (!insertResp.ok) {
    const errText = await insertResp.text();
    console.error("Supabase insert error:", errText);
    return res
      .status(500)
      .json({ error: "Failed to store session", detail: errText });
  }

  return res.status(200).json({
    authenticated: true,
    display_name: validation.display_name,
    profile_id: validation.profile_id,
    expires_at: expiresAt,
  });
}

async function handleStatus(req, res) {
  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!svcKey) {
    return res.status(200).json({ authenticated: false, reason: "not_configured" });
  }

  const resp = await fetch(
    supabaseUrl(
      "linkedin_sessions?is_valid=eq.true&order=created_at.desc&limit=1&select=profile_id,display_name,is_valid,expires_at,created_at,last_validated",
    ),
    { headers: supabaseHeaders() },
  );

  if (!resp.ok) {
    return res.status(200).json({ authenticated: false, reason: "db_error" });
  }

  const rows = await resp.json();
  if (!rows || rows.length === 0) {
    return res.status(200).json({ authenticated: false });
  }

  const session = rows[0];
  const expired = new Date(session.expires_at) < new Date();

  return res.status(200).json({
    authenticated: !expired,
    display_name: session.display_name,
    profile_id: session.profile_id,
    expires_at: session.expires_at,
    created_at: session.created_at,
    last_validated: session.last_validated,
    expired,
  });
}

async function handleLogout(req, res) {
  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!svcKey) {
    return res.status(500).json({ error: "Not configured" });
  }

  await fetch(supabaseUrl("linkedin_sessions?is_valid=eq.true"), {
    method: "PATCH",
    headers: supabaseHeaders(),
    body: JSON.stringify({ is_valid: false }),
  });

  return res.status(200).json({ status: "logged_out" });
}

async function handleHeartbeat(req, res) {
  const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!svcKey) {
    return res.status(500).json({ error: "Not configured" });
  }

  await fetch(supabaseUrl("linkedin_sessions?is_valid=eq.true"), {
    method: "PATCH",
    headers: supabaseHeaders(),
    body: JSON.stringify({ last_validated: new Date().toISOString() }),
  });

  return res.status(200).json({ status: "heartbeat_ok", timestamp: new Date().toISOString() });
}

// ---- Main handler ----------------------------------------------------------

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  try {
    if (req.method === "POST") {
      // Check if this is a heartbeat
      if (req.body && req.body.action === "heartbeat") {
        return handleHeartbeat(req, res);
      }
      return handleAuth(req, res);
    }
    if (req.method === "GET") {
      return handleStatus(req, res);
    }
    if (req.method === "DELETE") {
      return handleLogout(req, res);
    }
    return res.status(405).json({ error: "Method not allowed" });
  } catch (err) {
    console.error("Unhandled error:", err);
    return res
      .status(500)
      .json({ error: "Internal error", detail: String(err) });
  }
};
