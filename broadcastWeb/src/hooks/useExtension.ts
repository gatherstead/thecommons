// Detects the Commons Broadcast browser extension and relays fill requests to
// it. The extension is only reachable from Chromium browsers where it's
// installed; everything degrades gracefully to "not installed" elsewhere.
import { useCallback, useEffect, useRef, useState } from "react";

import type { Recipe } from "../models/broadcastModels";

// One or more extension IDs, comma-separated — lets the dev (unpacked) and the
// published Web Store builds coexist in env. We ping every configured id and
// prefer whichever advertises the fill-ack capability, so the resolved build
// is deterministic (and not stale) when both are installed (see ping() below).
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
  // Explicit capability list (e.g. "fill-ack" for the onConnectExternal port
  // channel) rather than a version-string comparison, so preference logic
  // stays correct even if a future build regresses a capability.
  caps?: string[];
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

  // Pings every configured ID and picks by *capability*, not by who answers
  // first. With two builds installed side by side (an unpacked dev copy and
  // the Web Store one — easy to end up with, and they look identical in
  // chrome://extensions apart from the ID), racing on "first responder"
  // could resolve to a stale build lacking the fill-ack port channel
  // (background.js's onConnectExternal). The SPA would then open a port
  // nothing listens on and the fill would die instantly. So: survey every
  // id, and once the survey completes prefer whichever advertised
  // "fill-ack", falling back to any responder if none did.
  //
  // Reported "installed" state upgrades responsively rather than waiting on
  // the whole survey: the moment *any* id answers we flip installed/resolved
  // immediately (so the UI doesn't stall on the slowest configured id), then
  // once every id has answered we upgrade resolvedId to the ack-capable one
  // if the initial responder wasn't it. We only ever upgrade, never
  // downgrade — an ack-capable resolution is never replaced by a non-capable
  // one. Gating the whole function on installedRef.current at the top means
  // a resolved hook never re-surveys — recheck()'s 1s poll naturally stops
  // once installedRef.current flips.
  const ping = useCallback(async (): Promise<void> => {
    const runtime = getRuntime();
    if (!runtime || EXTENSION_IDS.length === 0 || installedRef.current) return;

    let firstResponderId: string | undefined;

    const survey = EXTENSION_IDS.map(
      (id) =>
        new Promise<{ id: string; caps: string[] } | null>((resolve) => {
          try {
            runtime.sendMessage(id, { type: "ping" }, (response) => {
              // Reading lastError suppresses the "no receiving end" console
              // error Chrome logs when an extension isn't installed.
              const err = getRuntime()?.lastError;
              if (err || response?.ok !== true) {
                resolve(null);
                return;
              }
              if (!firstResponderId) {
                firstResponderId = id;
                if (!installedRef.current) {
                  installedRef.current = true;
                  setInstalled(true);
                  setResolvedId(id);
                }
              }
              resolve({ id, caps: response.caps ?? [] });
            });
          } catch {
            /* not a Chromium runtime — treat as not installed */
            resolve(null);
          }
        }),
    );

    const results = (await Promise.all(survey)).filter(
      (r): r is { id: string; caps: string[] } => r !== null,
    );
    const ackCapable = results.find((r) => r.caps.includes("fill-ack"));
    if (ackCapable) setResolvedId(ackCapable.id);
  }, []);

  const recheck = useCallback(() => {
    if (installedRef.current || pollRef.current) return;
    let attempts = 0;
    void ping();
    pollRef.current = setInterval(() => {
      attempts += 1;
      if (installedRef.current || attempts >= POLL_ATTEMPTS) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        return;
      }
      void ping();
    }, POLL_INTERVAL_MS);
  }, [ping]);

  useEffect(() => {
    void ping();
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
//
// Falls back to the older one-shot sendFill (fire-and-forget, no ack) when
// the ack channel itself never got off the ground — most commonly a stale
// extension build predating background.js's onConnectExternal handler for
// the "fill" port. Without this fallback that build regresses to a hard
// failure (ticket 51.6): "not available" and no tab opens, even though the
// one-shot {type:"fill"} runtime.onMessageExternal path the stale build
// *does* still handle would have opened the destination fine. A successful
// fallback resolves "timeout", not "complete" — we still have no completion
// ack, only confirmation (sendFill's boolean) that the tab opened.
function fallbackToOneShot(extensionId: string, recipe: Recipe): Promise<FillAckResult> {
  return sendFill(extensionId, recipe).then((dispatched) =>
    dispatched ? { kind: "timeout" } : { kind: "dispatch-failed" }
  );
}

export function sendFillWithAck(extensionId: string, recipe: Recipe): Promise<FillAckResult> {
  return new Promise((resolve) => {
    const runtime = getRuntime();
    if (!runtime || typeof runtime.connect !== "function") {
      // No connect() at all — the port was never opened, so nothing could
      // have been dispatched. Safe to retry via the one-shot path.
      void fallbackToOneShot(extensionId, recipe).then(resolve);
      return;
    }

    let settled = false;
    let port: ChromePort | undefined;
    // Set once background.js confirms (via a "dispatched" port message) that
    // handleFill actually ran. onDisconnect can in principle fire *after*
    // that — e.g. the destination tab's own navigation tearing the port down
    // — so a blind retry on every onDisconnect risks opening a second tab
    // for the same recipe. The other three dispatch-failed paths (no
    // connect(), connect() throwing, postMessage throwing) provably never
    // reached handleFill and are unconditionally safe to retry.
    let dispatched = false;

    const settle = (result: FillAckResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        port?.disconnect();
      } catch {
        /* already gone */
      }
      resolve(result);
    };

    const settleWithFallback = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        port?.disconnect();
      } catch {
        /* already gone */
      }
      void fallbackToOneShot(extensionId, recipe).then(resolve);
    };

    const timer = setTimeout(() => settle({ kind: "timeout" }), FILL_ACK_TIMEOUT_MS);

    try {
      port = runtime.connect(extensionId, { name: "fill" });
    } catch {
      clearTimeout(timer);
      void fallbackToOneShot(extensionId, recipe).then(resolve);
      return;
    }

    port.onMessage.addListener((message) => {
      if (settled) return;
      const msg = message as { type?: string; summary?: FillAckSummary };
      if (msg?.type === "dispatched") {
        // Confirms handleFill ran — from here on, onDisconnect must NOT
        // trigger a fallback retry.
        dispatched = true;
        return;
      }
      if (msg?.type === "fill-complete" && msg.summary) {
        settle({ kind: "complete", summary: msg.summary });
      }
    });

    port.onDisconnect.addListener(() => {
      if (settled) return;
      if (dispatched) {
        settle({ kind: "dispatch-failed" });
        return;
      }
      settleWithFallback();
    });

    try {
      port.postMessage({ type: "fill", payload: recipe });
    } catch {
      settleWithFallback();
    }
  });
}
