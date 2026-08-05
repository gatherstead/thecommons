import { afterEach, describe, expect, it, vi } from "vitest";

import { sendFillWithAck, FILL_ACK_TIMEOUT_MS } from "../hooks/useExtension";
import type { Recipe } from "../models/broadcastModels";

// Ticket 48.2: FILLED must only ever be reported once content.js's own
// completion ack arrives — never inferred from the extension having merely
// opened the destination tab. These tests exercise sendFillWithAck's three
// outcomes in isolation from the rest of the fill UI.

const RECIPE: Recipe = {
  site_key: "abc11",
  name: "ABC11",
  url: "https://example.com/submit",
  fields: [],
  captcha_hint: null,
  submit_selector: "#submit",
};

type Listener = (message: unknown) => void;

function fakePort() {
  const messageListeners: Listener[] = [];
  const disconnectListeners: (() => void)[] = [];
  return {
    postMessage: vi.fn(),
    disconnect: vi.fn(() => {
      disconnectListeners.forEach((cb) => cb());
    }),
    onMessage: { addListener: (cb: Listener) => messageListeners.push(cb) },
    onDisconnect: { addListener: (cb: () => void) => disconnectListeners.push(cb) },
    // test helpers, not part of the real chrome.runtime.Port shape
    _emitMessage: (msg: unknown) => messageListeners.forEach((cb) => cb(msg)),
    _emitDisconnect: () => disconnectListeners.forEach((cb) => cb()),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("sendFillWithAck", () => {
  it("resolves complete with the ack summary once content.js confirms", async () => {
    const port = fakePort();
    const connect = vi.fn(() => port);
    vi.stubGlobal("chrome", { runtime: { connect } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    expect(connect).toHaveBeenCalledWith("ext-id", { name: "fill" });
    expect(port.postMessage).toHaveBeenCalledWith({ type: "fill", payload: RECIPE });

    const summary = {
      ok: true,
      fieldsTotal: 5,
      fieldsFailed: 0,
      unmatchedTerms: [],
      venueMatchNotes: [],
      imageAttempted: true,
      imageOk: true,
    };
    port._emitMessage({ type: "fill-complete", summary });

    await expect(promise).resolves.toEqual({ kind: "complete", summary });
    expect(port.disconnect).toHaveBeenCalled();
  });

  it("resolves complete with ok:false when the fill was broken mid-run", async () => {
    const port = fakePort();
    vi.stubGlobal("chrome", { runtime: { connect: vi.fn(() => port) } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    const summary = {
      ok: false,
      error: "boom",
      fieldsTotal: 5,
      fieldsFailed: 2,
      unmatchedTerms: [],
      venueMatchNotes: [],
      imageAttempted: false,
      imageOk: false,
    };
    port._emitMessage({ type: "fill-complete", summary });

    const result = await promise;
    expect(result).toEqual({ kind: "complete", summary });
    if (result.kind === "complete") {
      expect(result.summary.ok).toBe(false);
    }
  });

  it("resolves timeout when no ack arrives within FILL_ACK_TIMEOUT_MS", async () => {
    vi.useFakeTimers();
    const port = fakePort();
    vi.stubGlobal("chrome", { runtime: { connect: vi.fn(() => port) } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    await vi.advanceTimersByTimeAsync(FILL_ACK_TIMEOUT_MS);

    await expect(promise).resolves.toEqual({ kind: "timeout" });
    expect(port.disconnect).toHaveBeenCalled();
  });

  it("does not time out early — an ack just under the deadline still wins", async () => {
    vi.useFakeTimers();
    const port = fakePort();
    vi.stubGlobal("chrome", { runtime: { connect: vi.fn(() => port) } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    await vi.advanceTimersByTimeAsync(FILL_ACK_TIMEOUT_MS - 1000);
    const summary = {
      ok: true,
      fieldsTotal: 1,
      fieldsFailed: 0,
      unmatchedTerms: [],
      venueMatchNotes: [],
      imageAttempted: false,
      imageOk: false,
    };
    port._emitMessage({ type: "fill-complete", summary });

    await expect(promise).resolves.toEqual({ kind: "complete", summary });
  });

  it("resolves dispatch-failed when the port disconnects before any ack", async () => {
    const port = fakePort();
    vi.stubGlobal("chrome", { runtime: { connect: vi.fn(() => port) } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    port._emitDisconnect();

    await expect(promise).resolves.toEqual({ kind: "dispatch-failed" });
  });

  it("resolves dispatch-failed when there is no extension runtime at all", async () => {
    vi.stubGlobal("chrome", undefined);
    await expect(sendFillWithAck("ext-id", RECIPE)).resolves.toEqual({
      kind: "dispatch-failed",
    });
  });

  it("ignores a 'dispatched' message and keeps waiting for the real completion ack", async () => {
    const port = fakePort();
    vi.stubGlobal("chrome", { runtime: { connect: vi.fn(() => port) } });

    const promise = sendFillWithAck("ext-id", RECIPE);
    port._emitMessage({ type: "dispatched", tabId: 7 });

    // Still pending — give the microtask queue a turn and confirm no resolution yet.
    let settled = false;
    promise.then(() => {
      settled = true;
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(settled).toBe(false);

    const summary = {
      ok: true,
      fieldsTotal: 1,
      fieldsFailed: 0,
      unmatchedTerms: [],
      venueMatchNotes: [],
      imageAttempted: false,
      imageOk: false,
    };
    port._emitMessage({ type: "fill-complete", summary });
    await expect(promise).resolves.toEqual({ kind: "complete", summary });
  });
});
