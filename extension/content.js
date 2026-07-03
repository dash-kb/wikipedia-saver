(function () {
  const BUTTON_ID = "local-wikipedia-saver-button";

  if (document.getElementById(BUTTON_ID)) {
    return;
  }

  const button = document.createElement("button");
  button.id = BUTTON_ID;
  button.type = "button";
  button.textContent = "Save to local wiki";
  button.title = "Save this Wikipedia page to your local git archive";
  document.body.appendChild(button);

  const setState = (state, text) => {
    button.dataset.state = state;
    button.textContent = text;
  };

  button.addEventListener("click", async () => {
    setState("saving", "Saving...");
    button.disabled = true;

    try {
      const result = await chrome.runtime.sendMessage({
        type: "save-wikipedia-page",
        url: window.location.href
      });
      if (!result || !result.ok) {
        throw new Error((result && result.error) || "Save failed");
      }

      setState("saved", result.payload.changed ? "Saved" : "Already saved");
      window.setTimeout(() => setState("", "Save to local wiki"), 2400);
    } catch (error) {
      setState("error", "Server offline");
      button.title = `${error.message}. Start the Wikipedia Saver local server.`;
      window.setTimeout(() => {
        button.title = "Save this Wikipedia page to your local git archive";
        setState("", "Save to local wiki");
      }, 3600);
    } finally {
      button.disabled = false;
    }
  });
})();
