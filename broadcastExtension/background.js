// Service worker. Dormant until the SPA sends a {type:"fill"} message; then it
// opens the target form in a new tab and injects content.js once, after which
// it forgets the tab (one-shot). No content scripts run on normal browsing.

const VERSION = chrome.runtime.getManifest().version;

// SPA origins permitted to drive the extension. Keep in sync with
// externally_connectable.matches in manifest.json.
const ALLOWED_ORIGINS = [
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "https://broadcast.thecommons.town"
];

// tabId -> storage nonce, so we only inject into tabs we opened ourselves.
// Persisted to chrome.storage.session (like the recipe itself, see handleFill)
// rather than kept in a module-level object: if the worker is torn down
// between chrome.tabs.create and the tab's onUpdated "complete" event, a
// plain in-memory map loses the entry and the tab silently never gets
// injected (suite 48.9).
function tabKey(tabId) {
  return `tab:${tabId}`;
}

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

// SPA tabs that opened a "fill" port and are waiting on content.js's
// completion ack, keyed by the tabId we opened for them. A live port keeps
// this service worker alive for the duration of the fill (same rationale as
// the fetch-image port below), so this map surviving a worker restart is a
// non-issue — the port itself wouldn't have survived one either.
const fillAckPorts = new Map();

// Long-lived channel from the SPA (ticket 48.2): lets background.js push the
// real completion ack back to the tab that requested the fill, instead of the
// SPA inferring success from "the tab opened" (the bug this ticket fixes).
chrome.runtime.onConnectExternal.addListener((port) => {
  const origin = port.sender && port.sender.origin;
  if (!origin || !ALLOWED_ORIGINS.includes(origin) || port.name !== "fill") {
    port.disconnect();
    return;
  }
  let openedTabId = null;
  port.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "fill" || !msg.payload) return;
    handleFill(msg.payload).then(
      (tabId) => {
        openedTabId = tabId;
        fillAckPorts.set(tabId, port);
        safePostMessage(port, { type: "dispatched", tabId });
      },
      (err) => {
        safePostMessage(port, { type: "dispatch-error", error: String(err) });
        try {
          port.disconnect();
        } catch (_) {
          /* already gone */
        }
      },
    );
  });
  port.onDisconnect.addListener(() => {
    if (openedTabId !== null) fillAckPorts.delete(openedTabId);
  });
});

async function handleFill(recipe) {
  if (!recipe.url) throw new Error("recipe has no url");
  const nonce = crypto.randomUUID();
  await chrome.storage.session.set({ [nonce]: recipe });
  const tab = await chrome.tabs.create({ url: recipe.url });
  await chrome.storage.session.set({ [tabKey(tab.id)]: nonce });
  return tab.id;
}

// content.js's completion signal (runFill's `finally`, whether the fill
// succeeded or threw) — forward it down the SPA's waiting port, if any. A
// site opened via the one-shot sendMessage path (sendFill, no ack requested)
// has no entry here, which is fine — that caller never expects this message.
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "commons-fill-complete" || !sender.tab) return;
  const port = fillAckPorts.get(sender.tab.id);
  if (!port) return;
  fillAckPorts.delete(sender.tab.id);
  safePostMessage(port, { type: "fill-complete", summary: msg.summary });
  try {
    port.disconnect();
  } catch (_) {
    /* already gone */
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, info) => {
  if (info.status !== "complete") return;
  const key = tabKey(tabId);
  const pending = await chrome.storage.session.get(key);
  const nonce = pending[key];
  if (!nonce) return;
  await chrome.storage.session.remove(key); // one-shot — back to dormant

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
  chrome.storage.session.remove(tabKey(tabId));
});

// Internal channel from content scripts (not the SPA) for fetching event
// images past page CORS via the worker's host_permissions. A long-lived port
// (rather than one-shot sendMessage) keeps the service worker alive for the
// duration of the fetch, and makes worker teardown observable to the sender
// via onDisconnect instead of surfacing only as a generic "message channel
// closed" error (suite 48.1).
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "fetch-image") return;
  port.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "fetch-image" || !msg.url) return;
    fetchImageAsDataUrl(msg.url).then(
      (dataUrl) => safePostMessage(port, { ok: true, dataUrl }),
      (err) => safePostMessage(port, { ok: false, error: String(err) }),
    );
  });
});

function safePostMessage(port, msg) {
  try {
    port.postMessage(msg);
  } catch (_) {
    // The tab (and its content script) is already gone — nothing to deliver to.
  }
}

async function fetchImageAsDataUrl(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} fetching image`);
  const blob = await response.blob();
  if (!blob.type || !blob.type.startsWith("image/")) {
    throw new Error(`expected an image, got content-type "${blob.type || "unknown"}"`);
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
}
