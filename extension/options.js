const form = document.getElementById("settings-form");
const input = document.getElementById("refresh-interval-days");
const status = document.getElementById("status");

function setStatus(text, state = "") {
  status.textContent = text;
  status.dataset.state = state;
}

async function loadSettings() {
  try {
    const result = await chrome.runtime.sendMessage({ type: "get-settings" });
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Could not load settings");
    }
    input.value = result.payload.settings.refresh_interval_days;
    setStatus("Settings loaded.");
  } catch (error) {
    input.value = "7";
    setStatus(`${error.message}. Start the Wikipedia Saver local server.`, "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const refreshIntervalDays = Number.parseInt(input.value, 10);

  try {
    const result = await chrome.runtime.sendMessage({
      type: "update-settings",
      settings: { refresh_interval_days: refreshIntervalDays }
    });
    if (!result || !result.ok) {
      throw new Error((result && result.error) || "Could not save settings");
    }
    input.value = result.payload.settings.refresh_interval_days;
    setStatus("Saved.");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

loadSettings();
