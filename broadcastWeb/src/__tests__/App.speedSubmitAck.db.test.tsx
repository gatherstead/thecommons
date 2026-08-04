import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Ticket 48.2: the "Populate Forms!" (speed-submit) flow must only ever show
// "filled" once content.js's completion ack confirms the fill actually ran —
// never just because the destination tab opened. These tests exercise the
// three outcomes of sendFillWithAck as surfaced through App.tsx's UI.

const { useSessionMock, fetchJwtMock, getAccessMock, getJobMock, directRecipeMock, sendFillWithAckMock } =
  vi.hoisted(() => ({
    useSessionMock: vi.fn(() => ({ data: null as Record<string, unknown> | null, isPending: false })),
    fetchJwtMock: vi.fn(async () => null as string | null),
    getAccessMock: vi.fn(async () => ({
      tier: 0 as 0 | 1 | 2,
      is_trial: false,
      uses_remaining: null as number | null,
    })),
    getJobMock: vi.fn(async () => null),
    directRecipeMock: vi.fn(async () => ({
      site_key: "abc11",
      name: "ABC11",
      url: "https://example.com/submit",
      fields: [],
      captcha_hint: null,
      submit_selector: "#submit",
    })),
    sendFillWithAckMock: vi.fn(),
  }));

vi.mock("../lib/authClient", () => ({
  authClient: {
    useSession: useSessionMock,
    signIn: { email: vi.fn(async () => ({ data: null, error: null })) },
    signUp: { email: vi.fn(async () => ({ data: null, error: null })) },
    signOut: vi.fn(async () => {}),
  },
  fetchJwt: fetchJwtMock,
}));

vi.mock("../services/broadcastApi", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, msg: string) {
      super(msg);
      this.status = status;
    }
  },
  SessionExpiredError: class SessionExpiredError extends Error {},
  setTokenRefreshListener: vi.fn(),
  authHeaders: () => ({}),
  getAccess: getAccessMock,
  previewBroadcast: vi.fn(async () => ({ eligible: [], excluded: [] })),
  directSubmit: vi.fn(async () => ({ status: "ok", draft_id: "x" })),
  getJob: getJobMock,
  retryJob: vi.fn(async () => ({})),
  submitReal: vi.fn(async () => ({})),
  cancelJob: vi.fn(async () => ({})),
  aiAutofill: vi.fn(async () => ({ event: {} })),
  directRecipe: directRecipeMock,
  getManualRecipe: vi.fn(async () => ({})),
  openScreenshot: vi.fn(async () => {}),
}));

vi.mock("../hooks/useExtension", async () => {
  const actual = await vi.importActual<typeof import("../hooks/useExtension")>(
    "../hooks/useExtension",
  );
  return {
    ...actual,
    useExtension: () => ({ installed: true, extensionId: "ext-1", recheck: vi.fn() }),
    sendFillWithAck: sendFillWithAckMock,
  };
});

const draftFixture = {
  draft_id: "d1",
  title: "Test Event",
  description: "Test description",
  start_datetime: "2026-01-01T10:00",
  end_datetime: "",
  all_day: false,
  venue_name: "Venue",
  address_line1: "1 Main St",
  state: "NC",
  zip: "27701",
  locality: ["durham"],
  categories: ["music"],
  event_url: "",
  ticket_url: "",
  price: "",
  is_free: true,
  image_url: "",
  organizer_name: "Acme Org",
  contact_email: "acme@example.com",
  contact_phone: "919-555-0100",
};

const renderAtDestinations = async () => {
  localStorage.setItem(
    "broadcast:draft:v2",
    JSON.stringify({
      draft: draftFixture,
      preview: { eligible: [{ site_key: "abc11", name: "ABC11" }], excluded: [] },
      selected: ["abc11"],
    }),
  );
  localStorage.setItem(
    "broadcast:session:v2",
    JSON.stringify({
      organizer_name: draftFixture.organizer_name,
      contact_email: draftFixture.contact_email,
      contact_phone: draftFixture.contact_phone,
    }),
  );
  useSessionMock.mockReturnValue({
    data: { user: { email: "operator@thecommons.town" } },
    isPending: false,
  });
  fetchJwtMock.mockResolvedValue("fake.jwt.token");
  getAccessMock.mockResolvedValue({ tier: 2, is_trial: false, uses_remaining: null });
  vi.resetModules();
  const { default: FreshApp } = await import("../App");
  const utils = render(<FreshApp />);
  await waitFor(() => {
    expect(screen.getByRole("button", { name: /Populate Forms!/i })).toBeEnabled();
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /Populate Forms!/i }));
  });
  return { ...utils };
};

beforeEach(() => {
  sendFillWithAckMock.mockReset();
  directRecipeMock.mockClear();
  localStorage.clear();
});

afterEach(cleanup);

describe("speed-submit fill ack (48.2)", () => {
  it("shows 'filled' only once the completion ack confirms ok:true", async () => {
    sendFillWithAckMock.mockResolvedValue({
      kind: "complete",
      summary: {
        ok: true,
        fieldsTotal: 3,
        fieldsFailed: 0,
        unmatchedTerms: [],
        venueMatchNotes: [],
        imageAttempted: true,
        imageOk: true,
      },
    });

    await renderAtDestinations();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "ABC11" }));
    });

    await waitFor(() => {
      expect(screen.getByText("filled")).toBeInTheDocument();
    });
  });

  it("shows a failure, not 'filled', when the ack reports ok:false (broken mid-run)", async () => {
    sendFillWithAckMock.mockResolvedValue({
      kind: "complete",
      summary: {
        ok: false,
        error: "boom",
        fieldsTotal: 3,
        fieldsFailed: 2,
        unmatchedTerms: [],
        venueMatchNotes: [],
        imageAttempted: false,
        imageOk: false,
      },
    });

    await renderAtDestinations();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "ABC11" }));
    });

    await waitFor(() => {
      expect(screen.getByText("fill failed")).toBeInTheDocument();
    });
    expect(screen.queryByText("filled")).toBeNull();
  });

  it("shows the unconfirmed state, not 'filled', when the ack times out", async () => {
    sendFillWithAckMock.mockResolvedValue({ kind: "timeout" });

    await renderAtDestinations();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "ABC11" }));
    });

    await waitFor(() => {
      expect(screen.getByText(/couldn.t confirm — check the tab/i)).toBeInTheDocument();
    });
    expect(screen.queryByText("filled")).toBeNull();
  });
});
