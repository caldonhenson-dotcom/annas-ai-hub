/**
 * Content script — runs on Annas AI Hub pages.
 * Broadcasts the extension ID so the dashboard can use chrome.runtime.sendMessage().
 */
(function () {
  // Post the extension ID to the page
  window.postMessage(
    {
      type: "ANNAS_LI_EXT_READY",
      extensionId: chrome.runtime.id,
    },
    "*"
  );

  // Also listen for the page requesting the ID (in case it loaded before this script)
  window.addEventListener("message", function (event) {
    if (event.data && event.data.type === "ANNAS_LI_EXT_PING") {
      window.postMessage(
        {
          type: "ANNAS_LI_EXT_READY",
          extensionId: chrome.runtime.id,
        },
        "*"
      );
    }
  });
})();
