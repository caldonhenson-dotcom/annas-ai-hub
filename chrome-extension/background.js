/**
 * Annas AI Hub — LinkedIn Connector (Background Service Worker)
 * =============================================================
 * Listens for messages from the dashboard page (via externally_connectable)
 * and reads LinkedIn cookies using the chrome.cookies API.
 *
 * Message protocol:
 *   Request:  { action: "GET_LINKEDIN_COOKIES" }
 *   Response: { success: true, li_at: "...", csrf_token: "..." }
 *          or { success: false, error: "..." }
 */

chrome.runtime.onMessageExternal.addListener(
  function (request, sender, sendResponse) {
    if (request.action !== "GET_LINKEDIN_COOKIES") {
      sendResponse({ success: false, error: "Unknown action" });
      return true;
    }

    // Read both cookies in parallel
    Promise.all([
      chrome.cookies.get({ url: "https://www.linkedin.com", name: "li_at" }),
      chrome.cookies.get({ url: "https://www.linkedin.com", name: "JSESSIONID" }),
    ])
      .then(function (results) {
        var liAtCookie = results[0];
        var jsessionCookie = results[1];

        if (!liAtCookie || !liAtCookie.value) {
          sendResponse({
            success: false,
            error:
              "No LinkedIn session found. Make sure you are logged into LinkedIn in this browser.",
          });
          return;
        }

        if (!jsessionCookie || !jsessionCookie.value) {
          sendResponse({
            success: false,
            error:
              "JSESSIONID cookie not found. Try refreshing LinkedIn and trying again.",
          });
          return;
        }

        // Clean the JSESSIONID — LinkedIn wraps it in URL-encoded quotes
        var csrf = decodeURIComponent(jsessionCookie.value).replace(/"/g, "");

        sendResponse({
          success: true,
          li_at: liAtCookie.value,
          csrf_token: csrf,
        });
      })
      .catch(function (err) {
        sendResponse({
          success: false,
          error: "Cookie read failed: " + (err.message || String(err)),
        });
      });

    // Return true to indicate we'll respond asynchronously
    return true;
  }
);
