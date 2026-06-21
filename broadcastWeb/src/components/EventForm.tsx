import type { EventDraft } from "../models/broadcastModels";
import { CATEGORIES, LOCALITIES } from "../models/broadcastModels";

interface Props {
  draft: EventDraft;
  onChange: (draft: EventDraft) => void;
  disabled: boolean;
}

function priceError(price: string | undefined): string {
  const v = (price ?? "").trim();
  if (!v) return "";
  if (v.toLowerCase() === "free")
    return "This event is free — tick the 'This event is free' checkbox instead.";
  if (/[a-z]/i.test(v))
    return "Price must be a number (e.g. 5 or 10.50).";
  const num = parseFloat(v);
  if (isNaN(num))
    return "Price must be a number (e.g. 5 or 10.50).";
  if (num < 0)
    return "Price cannot be negative.";
  if (/\.\d{3,}/.test(v))
    return "Price can have at most two decimal places.";
  return "";
}

function timeError(start: string, end: string | undefined): string {
  if (!start || !end) return "";
  if (new Date(end) <= new Date(start))
    return "End time must be after start time.";
  return "";
}

export default function EventForm({ draft, onChange, disabled }: Props) {
  const set = <K extends keyof EventDraft>(key: K, value: EventDraft[K]) =>
    onChange({ ...draft, [key]: value });

  const toggleCategory = (value: string) => {
    const has = draft.categories.includes(value);
    set(
      "categories",
      has ? draft.categories.filter((c) => c !== value) : [...draft.categories, value],
    );
  };

  const toggleLocality = (value: string) => {
    const has = draft.locality.includes(value);
    set(
      "locality",
      has ? draft.locality.filter((l) => l !== value) : [...draft.locality, value],
    );
  };

  const handlePriceChange = (value: string) => {
    const updates: Partial<EventDraft> = { price: value };
    const num = parseFloat(value.trim());
    if (!isNaN(num) && num > 0) updates.is_free = false;
    onChange({ ...draft, ...updates });
  };

  const priceErr = priceError(draft.price);
  const timeErr = timeError(draft.start_datetime, draft.end_datetime);

  return (
    <div className="field-grid">
      <div className="field span-2">
        <label htmlFor="title">
          Event Title <span className="required-mark">*</span>
        </label>
        <input
          id="title"
          type="text"
          value={draft.title}
          onChange={(e) => set("title", e.target.value)}
          disabled={disabled}
          maxLength={300}
        />
      </div>

      <div className="field span-2">
        <label htmlFor="description">
          Description <span className="required-mark">*</span>
        </label>
        <textarea
          id="description"
          value={draft.description}
          onChange={(e) => set("description", e.target.value)}
          disabled={disabled}
        />
        <p className="hint">Plain text. Sites with length limits get a truncated copy.</p>
      </div>

      <div className="field">
        <label htmlFor="start">
          Starts <span className="required-mark">*</span>
        </label>
        <input
          id="start"
          type="datetime-local"
          value={draft.start_datetime}
          onChange={(e) => set("start_datetime", e.target.value)}
          disabled={disabled}
        />
      </div>

      <div className="field">
        <label htmlFor="end">Ends</label>
        <input
          id="end"
          type="datetime-local"
          value={draft.end_datetime ?? ""}
          onChange={(e) => set("end_datetime", e.target.value)}
          disabled={disabled}
        />
        {timeErr && <p className="field-error">{timeErr}</p>}
      </div>

      <div className="field checkbox-row">
        <input
          id="all-day"
          type="checkbox"
          checked={draft.all_day}
          onChange={(e) => set("all_day", e.target.checked)}
          disabled={disabled}
        />
        <label htmlFor="all-day">All-day event</label>
      </div>

      <div className="field">
        <label htmlFor="venue">
          Venue Name <span className="required-mark">*</span>
        </label>
        <input
          id="venue"
          type="text"
          value={draft.venue_name}
          onChange={(e) => set("venue_name", e.target.value)}
          disabled={disabled}
          maxLength={200}
        />
      </div>

      <div className="field">
        <label htmlFor="address">
          Street Address <span className="required-mark">*</span>
        </label>
        <input
          id="address"
          type="text"
          value={draft.address_line1}
          onChange={(e) => set("address_line1", e.target.value)}
          disabled={disabled}
          maxLength={200}
        />
      </div>

      <div className="field">
        <label htmlFor="state">State</label>
        <input
          id="state"
          type="text"
          value={draft.state}
          onChange={(e) => set("state", e.target.value)}
          disabled={disabled}
          maxLength={2}
        />
      </div>

      <div className="field">
        <label htmlFor="zip">
          ZIP <span className="required-mark">*</span>
        </label>
        <input
          id="zip"
          type="text"
          value={draft.zip}
          onChange={(e) => set("zip", e.target.value)}
          disabled={disabled}
          maxLength={10}
        />
      </div>

      <div className="field span-2">
        <fieldset className="category-set">
          <legend>
            Locality (routing) <span className="required-mark">*</span>
          </legend>
          <div className="category-options">
            {LOCALITIES.map((l) => (
              <span key={l.value} className="checkbox-row">
                <input
                  id={`loc-${l.value}`}
                  type="checkbox"
                  checked={draft.locality.includes(l.value)}
                  onChange={() => toggleLocality(l.value)}
                  disabled={disabled}
                />
                <label htmlFor={`loc-${l.value}`}>{l.label}</label>
              </span>
            ))}
          </div>
          <p className="hint">Select all areas this event is relevant to — determines which calendars it reaches.</p>
        </fieldset>
      </div>

      <div className="field span-2">
        <fieldset className="category-set">
          <legend>
            Categories (routing) <span className="required-mark">*</span>
          </legend>
          <div className="category-options">
            {CATEGORIES.map((c) => (
              <span key={c.value} className="checkbox-row">
                <input
                  id={`cat-${c.value}`}
                  type="checkbox"
                  checked={draft.categories.includes(c.value)}
                  onChange={() => toggleCategory(c.value)}
                  disabled={disabled}
                />
                <label htmlFor={`cat-${c.value}`}>{c.label}</label>
              </span>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="field">
        <label htmlFor="event-url">Event Page URL</label>
        <input
          id="event-url"
          type="url"
          value={draft.event_url ?? ""}
          onChange={(e) => set("event_url", e.target.value)}
          disabled={disabled}
        />
      </div>

      <div className="field">
        <label htmlFor="ticket-url">Ticket URL</label>
        <input
          id="ticket-url"
          type="url"
          value={draft.ticket_url ?? ""}
          onChange={(e) => set("ticket_url", e.target.value)}
          disabled={disabled}
        />
      </div>

      <div className="field">
        <label htmlFor="price">Price</label>
        <input
          id="price"
          type="text"
          value={draft.price ?? ""}
          onChange={(e) => handlePriceChange(e.target.value)}
          disabled={disabled}
          placeholder="e.g. 10 or 10.50"
          maxLength={60}
        />
        {priceErr && <p className="field-error">{priceErr}</p>}
      </div>

      <div className="field checkbox-row">
        <input
          id="is-free"
          type="checkbox"
          checked={draft.is_free}
          onChange={(e) => {
            const checked = e.target.checked;
            onChange({ ...draft, is_free: checked, price: checked ? "0.00" : draft.price });
          }}
          disabled={disabled}
        />
        <label htmlFor="is-free">This event is free</label>
      </div>

      <div className="field">
        <label htmlFor="image-url">Image URL</label>
        <input
          id="image-url"
          type="url"
          value={draft.image_url ?? ""}
          onChange={(e) => set("image_url", e.target.value)}
          disabled={disabled}
        />
        <p className="hint">Sites that take an upload receive this image as a file.</p>
      </div>

      <div className="field">
        <label htmlFor="organizer">Organizer Name</label>
        <input
          id="organizer"
          type="text"
          value={draft.organizer_name ?? ""}
          onChange={(e) => set("organizer_name", e.target.value)}
          disabled={disabled}
          maxLength={200}
        />
      </div>

      <div className="field">
        <label htmlFor="email">Contact Email</label>
        <input
          id="email"
          type="email"
          value={draft.contact_email ?? ""}
          onChange={(e) => set("contact_email", e.target.value)}
          disabled={disabled}
        />
      </div>

      <div className="field">
        <label htmlFor="phone">Contact Phone</label>
        <input
          id="phone"
          type="tel"
          value={draft.contact_phone ?? ""}
          onChange={(e) => set("contact_phone", e.target.value)}
          disabled={disabled}
          maxLength={40}
        />
      </div>
    </div>
  );
}
