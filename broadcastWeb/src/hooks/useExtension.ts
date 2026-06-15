// Detects the Commons Broadcast browser extension and relays fill requests to
// it. The extension is only reachable from Chromium browsers where it's
// installed; everything degrades gracefully to "not installed" elsewhere.
import { useEffect, useState } from "react";

import type { Recipe } from "../models/broadcastModels";

const EXTENSION_ID = import.meta.env.VITE_BROADCAST_EXTENSION_ID as
  | string
  | undefined;

// Unlisted Chrome Web Store install link. TODO: replace once the listing exists.
export const WEB_STORE_URL =
  "https://chromewebstore.google.com/detail/the-commons-broadcast";

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
}

export function useExtension(): ExtensionState {
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const runtime = getRuntime();
    if (!runtime || !EXTENSION_ID) return;
    try {
      runtime.sendMessage(EXTENSION_ID, { type: "ping" }, (response) => {
        // Reading lastError suppresses the "no receiving end" console error
        // Chrome logs when the extension isn't installed.
        const err = getRuntime()?.lastError;
        if (!err && response?.ok) setInstalled(true);
      });
    } catch {
      /* not a Chromium runtime — treat as not installed */
    }
  }, []);

  return { installed, extensionId: EXTENSION_ID };
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
