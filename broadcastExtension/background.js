// Service worker. Dormant until the SPA sends a {type:"fill"} message; then it
// opens the target form in a new tab and injects content.js once, after which
// it forgets the tab (one-shot). No content scripts run on normal browsing.

const VERSION = chrome.runtime.getManifest().version;

// SPA origins permitted to drive the extension. Keep in sync with
// externally_connectable.matches in manifest.json.
const ALLOWED_ORIGINS = [
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "https://broadcast.thecommons.town/",
  "https://broadcast.thecommons.town/*"
];

// tabId -> storage nonce, so we only inject into tabs we opened ourselves.
const pendingTabs = {};

chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (!sender.origin || !ALLOWED_ORIGINS.includes(sender.origin)) {
    sendResponse({ ok: false, error: "origin not allowed" });
    return false;
  }
  if (msg && msg.type === "ping") {
    sendResponse({ ok: true, version: VERSION });
    return false;
  }
  if (msg && msg.type === "fill" && msg.payload) {
    handleFill(msg.payload).then(
      () => sendResponse({ ok: true }),
      (err) => sendResponse({ ok: false, error: String(err) }),
    );
    return true; // keep the channel open for the async response
  }
  sendResponse({ ok: false, error: "unknown message" });
  return false;
});

async function handleFill(recipe) {
  if (!recipe.url) throw new Error("recipe has no url");
  const nonce = crypto.randomUUID();
  await chrome.storage.session.set({ [nonce]: recipe });
  const tab = await chrome.tabs.create({ url: recipe.url });
  pendingTabs[tab.id] = nonce;
}

chrome.tabs.onUpdated.addListener(async (tabId, info) => {
  const nonce = pendingTabs[tabId];
  if (!nonce || info.status !== "complete") return;
  delete pendingTabs[tabId]; // one-shot — back to dormant

  const stored = await chrome.storage.session.get(nonce);
  const recipe = stored[nonce];
  await chrome.storage.session.remove(nonce);
  if (!recipe) return;

  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
    await chrome.tabs.sendMessage(tabId, { type: "commons-fill", recipe });
  } catch (e) {
    console.error("Commons Broadcast: injection failed", e);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  delete pendingTabs[tabId];
});

// Internal messages from injected content scripts (not the SPA). Currently
// handles one operation: fetching an image URL and returning it as a data URL
// so content.js can build a File and assign it to a file input via DataTransfer.
// The service worker has "https://*/*" host_permissions so it bypasses the
// page's CORS policy — event images are arbitrary user-supplied URLs.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "fetch-image" && msg.url) {
    fetchImageAsDataUrl(msg.url).then(
      (dataUrl) => sendResponse({ ok: true, dataUrl }),
      (err) => sendResponse({ ok: false, error: String(err) }),
    );
    return true; // keep channel open for the async response
  }
  return false;
});

async function fetchImageAsDataUrl(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} fetching image`);
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
}
