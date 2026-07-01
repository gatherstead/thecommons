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

interface ChromeRuntime {
  sendMessage: (
    extensionId: string,
    message: unknown,
    callback: (response?: PingResponse) => void,
  ) => void;
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
