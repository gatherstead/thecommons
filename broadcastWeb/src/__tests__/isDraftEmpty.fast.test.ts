import { describe, expect, it } from "vitest";

import { isDraftEmpty } from "../App";
import type { EventDraft } from "../models/broadcastModels";

const EMPTY: EventDraft = {
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

describe("isDraftEmpty", () => {
  it("returns true for the canonical empty draft", () => {
    expect(isDraftEmpty(EMPTY)).toBe(true);
  });

  it("treats state='NC' as empty (it's the default)", () => {
    expect(isDraftEmpty({ ...EMPTY, state: "NC" })).toBe(true);
  });

  it("treats state='' as empty", () => {
    expect(isDraftEmpty({ ...EMPTY, state: "" })).toBe(true);
  });

  it("returns false when title is filled", () => {
    expect(isDraftEmpty({ ...EMPTY, title: "Some Event" })).toBe(false);
  });

  it("returns false when description is filled", () => {
    expect(isDraftEmpty({ ...EMPTY, description: "Details here" })).toBe(false);
  });

  it("returns false when start_datetime is set", () => {
    expect(isDraftEmpty({ ...EMPTY, start_datetime: "2026-10-17T16:00" })).toBe(false);
  });

  it("returns false when end_datetime is set", () => {
    expect(isDraftEmpty({ ...EMPTY, end_datetime: "2026-10-17T23:00" })).toBe(false);
  });

  it("returns false when all_day is true", () => {
    expect(isDraftEmpty({ ...EMPTY, all_day: true })).toBe(false);
  });

  it("returns false when venue_name is filled", () => {
    expect(isDraftEmpty({ ...EMPTY, venue_name: "The Venue" })).toBe(false);
  });

  it("returns false when address_line1 is filled", () => {
    expect(isDraftEmpty({ ...EMPTY, address_line1: "1 Main St" })).toBe(false);
  });

  it("returns false when state differs from NC or blank", () => {
    expect(isDraftEmpty({ ...EMPTY, state: "CA" })).toBe(false);
  });

  it("returns false when zip is filled", () => {
    expect(isDraftEmpty({ ...EMPTY, zip: "27701" })).toBe(false);
  });

  it("returns false when locality is non-empty", () => {
    expect(isDraftEmpty({ ...EMPTY, locality: ["durham"] })).toBe(false);
  });

  it("returns false when categories is non-empty", () => {
    expect(isDraftEmpty({ ...EMPTY, categories: ["music"] })).toBe(false);
  });

  it("returns false when is_free is true", () => {
    expect(isDraftEmpty({ ...EMPTY, is_free: true })).toBe(false);
  });

  it("returns false when event_url is set", () => {
    expect(isDraftEmpty({ ...EMPTY, event_url: "https://example.com" })).toBe(false);
  });

  // Contact details are session-sticky operator data, not event content, so a
  // saved contact must NOT make the form look non-empty (it would block AI Autofill).
  it("ignores organizer_name (session-sticky contact, not event content)", () => {
    expect(isDraftEmpty({ ...EMPTY, organizer_name: "The Org" })).toBe(true);
  });

  it("ignores contact_email and contact_phone (session-sticky contact)", () => {
    expect(isDraftEmpty({ ...EMPTY, contact_email: "a@b.com", contact_phone: "919-555-0100" })).toBe(
      true,
    );
  });

  it("returns true when optional fields are undefined (as EventDraft allows)", () => {
    const draft: EventDraft = {
      title: "",
      description: "",
      start_datetime: "",
      all_day: false,
      venue_name: "",
      address_line1: "",
      state: "NC",
      zip: "",
      locality: [],
      categories: [],
      is_free: false,
    };
    expect(isDraftEmpty(draft)).toBe(true);
  });

  it("returns false for a fully populated DEV_FIXTURE-style draft", () => {
    const filled: EventDraft = {
      title: "Bull City BOOs Fest",
      description: "Join The MAKRS Society...",
      start_datetime: "2026-10-17T16:00",
      end_datetime: "2026-10-17T23:00",
      all_day: false,
      venue_name: "Durham Central Park",
      address_line1: "501 Foster St",
      state: "NC",
      zip: "27701",
      locality: ["durham"],
      categories: ["festival", "music"],
      event_url: "https://makrs.com",
      ticket_url: "",
      price: "",
      is_free: true,
      image_url: "",
      organizer_name: "The MAKRS Society",
      contact_email: "info@makrs.com",
      contact_phone: "",
    };
    expect(isDraftEmpty(filled)).toBe(false);
  });
});
