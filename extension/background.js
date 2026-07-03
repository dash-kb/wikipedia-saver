const SERVER_BASE_URL = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (
    !message ||
    ![
      "save-wikipedia-page",
      "check-wikipedia-page",
      "get-settings",
      "update-settings"
    ].includes(message.type)
  ) {
    return false;
  }

  const endpointByType = {
    "save-wikipedia-page": "/save",
    "check-wikipedia-page": "/status",
    "get-settings": "/settings",
    "update-settings": "/settings"
  };
  const body = message.type === "update-settings" ? message.settings : { url: message.url };

  fetch(`${SERVER_BASE_URL}${endpointByType[message.type]}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Save failed");
      }
      sendResponse({ ok: true, payload });
    })
    .catch((error) => {
      sendResponse({ ok: false, error: error.message });
    });

  return true;
});
