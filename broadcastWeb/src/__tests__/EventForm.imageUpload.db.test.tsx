import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { useState } from "react";
import EventForm from "../components/EventForm";
import type { EventDraft } from "../models/broadcastModels";

// vi.hoisted so the mock fn reference is available inside the hoisted vi.mock factory.
const { uploadImageMock } = vi.hoisted(() => ({
  uploadImageMock: vi.fn(),
}));

vi.mock("../services/broadcastApi", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, msg: string) {
      super(msg);
      this.status = status;
    }
  },
  uploadImage: uploadImageMock,
}));

afterEach(cleanup);

const baseDraft: EventDraft = {
  draft_id: "d1",
  title: "",
  description: "",
  start_datetime: "",
  end_datetime: "",
  all_day: false,
  venue_name: "",
  address_line1: "",
  state: "NC",
  zip: "",
  locality: [],
  categories: [],
  event_url: "",
  ticket_url: "",
  price: "",
  is_free: false,
  image_url: "",
  organizer_name: "",
  contact_email: "",
  contact_phone: "",
};

// Mirrors App.tsx's handleDraftChange: the parent owns the merge against its
// own current state via the functional-updater contract (48.3).
function Harness() {
  const [draft, setDraft] = useState<EventDraft>(baseDraft);
  return (
    <EventForm
      draft={draft}
      onChange={(updater) => setDraft(updater)}
      disabled={false}
      auth={{ jwt: "t" }}
    />
  );
}

describe("48.3: stale-closure race during image upload", () => {
  it("preserves a mid-upload edit and the resulting image_url once a slow upload resolves", async () => {
    let resolveUpload!: (v: { url: string }) => void;
    uploadImageMock.mockReturnValue(
      new Promise<{ url: string }>((resolve) => {
        resolveUpload = resolve;
      }),
    );

    render(<Harness />);

    const file = new File(["fake-bytes"], "photo.png", { type: "image/png" });
    // jsdom doesn't implement image decoding — stub the natural dimensions the
    // component reads off the Image element before it proceeds to upload.
    Object.defineProperty(HTMLImageElement.prototype, "naturalWidth", {
      configurable: true,
      get: () => 100,
    });
    Object.defineProperty(HTMLImageElement.prototype, "naturalHeight", {
      configurable: true,
      get: () => 100,
    });
    const originalImage = window.Image;
    class InstantImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_v: string) {
        // Fire onload synchronously so readImageDimensions resolves immediately.
        this.onload?.();
      }
    }
    // @ts-expect-error -- test stub, not a full Image implementation
    window.Image = InstantImage;

    const fileInput = document.getElementById("image-file") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    await waitFor(() => expect(uploadImageMock).toHaveBeenCalled());
    expect(screen.getByText(/Uploading…/i)).toBeInTheDocument();

    // Mid-flight edit — dispatched while the upload promise is still pending.
    const titleInput = screen.getByLabelText(/Event Title/i) as HTMLInputElement;
    fireEvent.change(titleInput, { target: { value: "Mid-upload edit" } });
    expect(titleInput).toHaveValue("Mid-upload edit");

    // Now let the slow upload resolve.
    await act(async () => {
      resolveUpload({ url: "https://cdn.example.com/photo.png" });
      await Promise.resolve();
      await Promise.resolve();
    });

    // Both the mid-flight edit and the upload's image_url must survive —
    // pre-48.3 this reverted the title back to "" because the upload handler
    // spread a stale `draft` captured at the render when the file was picked.
    await waitFor(() => {
      expect((screen.getByLabelText(/Event Title/i) as HTMLInputElement).value).toBe(
        "Mid-upload edit",
      );
    });
    // alt="" makes the <img> presentational (excluded from the a11y tree), so
    // query it directly rather than via getByRole("img").
    await waitFor(() => {
      const img = document.querySelector(".image-preview img");
      expect(img).toHaveAttribute("src", "https://cdn.example.com/photo.png");
    });

    window.Image = originalImage;
  });
});
