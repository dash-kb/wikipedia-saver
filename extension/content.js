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

  let pageIsSaved = false;

  const setState = (state, text) => {
    button.dataset.state = state;
    button.textContent = text;
  };

  const showSavedState = () => {
    pageIsSaved = true;
    button.title = "This page is saved in your local Wikipedia archive";
    setState("saved", "Saved");
  };

  const showUnsavedState = () => {
    pageIsSaved = false;
    button.title = "Save this Wikipedia page to your local git archive";
    setState("", "Save to local wiki");
  };

  const checkSavedStatus = async () => {
    try {
      const result = await chrome.runtime.sendMessage({
        type: "check-wikipedia-page",
        url: window.location.href
      });
      if (result && result.ok && result.payload.saved) {
        showSavedState();
      } else {
        showUnsavedState();
      }
    } catch (_error) {
      showUnsavedState();
      button.title = "Start the Wikipedia Saver local server to check library status";
    }
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

      if (result.payload.changed) {
        setState("saved", pageIsSaved ? "Refreshed" : "Saved");
      } else {
        setState("saved", "Already current");
      }
      pageIsSaved = true;
      window.setTimeout(showSavedState, 2400);
    } catch (error) {
      setState("error", "Server offline");
      button.title = `${error.message}. Start the Wikipedia Saver local server.`;
      window.setTimeout(() => {
        if (pageIsSaved) {
          showSavedState();
        } else {
          showUnsavedState();
        }
      }, 3600);
    } finally {
      button.disabled = false;
    }
  });

  button.addEventListener("mouseenter", () => {
    if (pageIsSaved && !button.disabled) {
      setState("saved", "Refresh save");
    }
  });

  button.addEventListener("mouseleave", () => {
    if (pageIsSaved && !button.disabled) {
      showSavedState();
    }
  });

  checkSavedStatus();
})();
