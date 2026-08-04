// Detects the Commons Broadcast browser extension and relays fill requests to
// it. The extension is only reachable from Chromium browsers where it's
// installed; everything degrades gracefully to "not installed" elsewhere.
import { useCallback, useEffect, useRef, useState } from "react";

import type { Recipe } from "../models/broadcastModels";

// One or more extension IDs, comma-separated — lets the dev (unpacked) and the
// published Web Store builds coexist in env. We ping each and use whichever is
// actually installed (see resolved id below).
const EXTENSION_IDS: string[] = (
  (import.meta.env.VITE_BROADCAST_EXTENSION_ID as string | undefined) ?? ""
)
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

export const WEB_STORE_URL =
  "https://chromewebstore.google.com/detail/the-commons-%E2%80%94-broadcast/jidmhdmlbjfnblbheglmodhpcjhafjmi";

interface PingResponse {
  ok?: boolean;
  version?: string;
}

// Minimal shape of a chrome.runtime.Port, typed just enough for the fill-ack
// channel below.
interface ChromePort {
  postMessage: (message: unknown) => void;
  disconnect: () => void;
  onMessage: { addListener: (cb: (message: unknown) => void) => void };
  onDisconnect: { addListener: (cb: () => void) => void };
}

interface ChromeRuntime {
  sendMessage: (
    extensionId: string,
    message: unknown,
    callback: (response?: PingResponse) => void,
  ) => void;
  connect: (extensionId: string, connectInfo?: { name?: string }) => ChromePort;
  lastError?: { message?: string };
}

function getRuntime(): ChromeRuntime | undefined {
  const c = (window as unknown as { chrome?: { runtime?: ChromeRuntime } })
    .chrome;
  return c?.runtime;
}

export interface ExtensionState {
  installed: boolean;
  extensionId: string | undefined;
  // Begin polling for the extension (once/sec for ~60s). Call after sending the
  // user to install it; resolves the moment a ping succeeds.
  recheck: () => void;
}

const POLL_INTERVAL_MS = 1000;
const POLL_ATTEMPTS = 60;

export function useExtension(): ExtensionState {
  const [installed, setInstalled] = useState(false);
  const [resolvedId, setResolvedId] = useState<string | undefined>(undefined);
  const installedRef = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const ping = useCallback((): void => {
    const runtime = getRuntime();
    if (!runtime || EXTENSION_IDS.length === 0) return;
    for (const id of EXTENSION_IDS) {
      try {
        runtime.sendMessage(id, { type: "ping" }, (response) => {
          // Reading lastError suppresses the "no receiving end" console error
          // Chrome logs when an extension isn't installed.
          const err = getRuntime()?.lastError;
          if (!err && response?.ok && !installedRef.current) {
            installedRef.current = true;
            setInstalled(true);
            setResolvedId(id);
          }
        });
      } catch {
        /* not a Chromium runtime — treat as not installed */
      }
    }
  }, []);

  const recheck = useCallback(() => {
    if (installedRef.current || pollRef.current) return;
    let attempts = 0;
    ping();
    pollRef.current = setInterval(() => {
      attempts += 1;
      if (installedRef.current || attempts >= POLL_ATTEMPTS) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        return;
      }
      ping();
    }, POLL_INTERVAL_MS);
  }, [ping]);

  useEffect(() => {
    ping();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [ping]);

  return { installed, extensionId: resolvedId, recheck };
}

export function sendFill(extensionId: string, recipe: Recipe): Promise<boolean> {
  return new Promise((resolve) => {
    const runtime = getRuntime();
    if (!runtime) {
      resolve(false);
      return;
    }
    try {
      runtime.sendMessage(
        extensionId,
        { type: "fill", payload: recipe },
        (response) => {
          const err = getRuntime()?.lastError;
          resolve(!err && Boolean(response?.ok));
        },
      );
    } catch {
      resolve(false);
    }
  });
}

// Per-field outcome of a fill, posted by content.js's runFill once it's done
// (success or thrown) — see broadcastExtension/content.js's `finally` block.
// Mirrors the unmatchedTerms/venueMatchNotes accounting already surfaced in
// the on-page review banner, so the SPA and the banner agree on what happened.
export interface FillAckSummary {
  ok: boolean;
  error?: string;
  fieldsTotal: number;
  fieldsFailed: number;
  unmatchedTerms: { field: string; term: string }[];
  venueMatchNotes: { field: string; matched: string }[];
  imageAttempted: boolean;
  imageOk: boolean;
}

export type FillAckResult =
  // The extension/tab never confirmed it even opened — same class of failure
  // sendFill's boolean already reports.
  | { kind: "dispatch-failed" }
  // content.js's runFill ran to completion (or threw) and told us so.
  | { kind: "complete"; summary: FillAckSummary }
  // No word from content.js within the timeout — the fill may well have
  // worked (the tab could still be mid-fill, or the ack message got lost),
  // so this is deliberately not the same as "failed".
  | { kind: "timeout" };

// How long we wait for content.js's completion ack before giving up and
// reporting "unconfirmed". A single-site content-script fill (category
// select2 widgets in particular loop per term with their own multi-second
// waits — see fillSelect2Multi) can legitimately run longer than the
// backend's own stuck-worker threshold (RUNNING_STUCK_MS, 90s in App.tsx),
// since that threshold guards a server-orchestrated multi-target job rather
// than one foreground tab. Comfortably above worst-case observed fill time
// without making the happy path (which resolves on the ack, not the timeout)
// any slower.
export const FILL_ACK_TIMEOUT_MS = 120_000;

// Like sendFill, but waits for content.js's own completion signal instead of
// resolving as soon as the extension has opened the destination tab. Opens a
// long-lived port to the extension (mirrors the fetch-image port pattern
// already used between content.js and background.js) so background.js can
// push the ack back down once it arrives, rather than the SPA polling for it.
export function sendFillWithAck(extensionId: string, recipe: Recipe): Promise<FillAckResult> {
  return new Promise((resolve) => {
    const runtime = getRuntime();
    if (!runtime || typeof runtime.connect !== "function") {
      resolve({ kind: "dispatch-failed" });
      return;
    }

    let settled = false;
    let port: ChromePort | undefined;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        port?.disconnect();
      } catch {
        /* already gone */
      }
      resolve({ kind: "timeout" });
    }, FILL_ACK_TIMEOUT_MS);

    try {
      port = runtime.connect(extensionId, { name: "fill" });
    } catch {
      clearTimeout(timer);
      resolve({ kind: "dispatch-failed" });
      return;
    }

    port.onMessage.addListener((message) => {
      if (settled) return;
      const msg = message as { type?: string; summary?: FillAckSummary };
      if (msg && msg.type === "fill-complete" && msg.summary) {
        settled = true;
        clearTimeout(timer);
        try {
          port?.disconnect();
        } catch {
          /* already gone */
        }
        resolve({ kind: "complete", summary: msg.summary });
      }
      // Other message types (e.g. "dispatched") just confirm the tab opened —
      // not completion, so keep waiting.
    });

    port.onDisconnect.addListener(() => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ kind: "dispatch-failed" });
    });

    try {
      port.postMessage({ type: "fill", payload: recipe });
    } catch {
      settled = true;
      clearTimeout(timer);
      resolve({ kind: "dispatch-failed" });
    }
  });
}
