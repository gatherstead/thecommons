// Injected on demand by background.js (never via static content_scripts). Reads
// the recipe, fills every field it can, and leaves the captcha + submit button
// for the human. It never clicks submit.

(() => {
  if (window.__commonsBroadcastRan) return;
  window.__commonsBroadcastRan = true;

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "commons-fill" && msg.recipe) {
      runFill(msg.recipe).catch((e) => console.error("Commons Broadcast:", e));
    }
  });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitFor(predicate, timeoutMs) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        if (predicate()) return true;
      } catch (_) {
        /* keep polling */
      }
      await sleep(150);
    }
    return false;
  }

  // Terms from a select2_multi/react_select field that matched nothing in the
  // destination vocabulary — surfaced in the review banner so a mis-mapped
  // category never fails silently again (see suite 46.1).
  const unmatchedTerms = [];

  // select2 "Create or Find" widgets (venue/organizer) where we reused an
  // existing option instead of creating a new one — surfaced as a
  // non-blocking note in the review banner (suite 48.6) so a human can catch
  // a bad reuse before submitting.
  const venueMatchNotes = [];

  // Image upload outcome (see fillFile) — surfaced in the completion ack so
  // the SPA never reports FILLED when the image silently fell back to the
  // manual hint (suite 48.2).
  let imageAttempted = false;
  let imageOk = false;

  async function runFill(recipe) {
    unmatchedTerms.length = 0;
    venueMatchNotes.length = 0;
    imageAttempted = false;
    imageOk = false;

    let fieldsTotal = 0;
    let fieldsFailed = 0;
    let ranOk = true;
    let errorMessage;

    // The banner is one completion signal for the human at the keyboard; the
    // ack below is the completion signal for the SPA (ticket 48.2) — status
    // there must never be inferred from "the fill was dispatched" the way it
    // used to be. Both must render/send even if a field handler hangs or
    // throws unexpectedly, so a partial fill is never mistaken for a
    // complete one (suite 48.1 / 48.2).
    try {
      const fields = recipe.fields || [];
      fieldsTotal = fields.length;
      // Some forms render after page "complete"; adapters can specify a
      // ready_selector, otherwise we fall back to the first field.
      const readySel = recipe.ready_selector || (fields[0] && fields[0].selector);
      if (readySel) {
        await waitFor(() => document.querySelector(readySel), 15000);
      }
      for (const field of fields) {
        const handler = HANDLERS[field.type] || HANDLERS.manual_widget;
        try {
          await handler(field);
        } catch (e) {
          fieldsFailed += 1;
          console.warn("Commons Broadcast: field failed", field.selector, e);
        }
      }
      if (unmatchedTerms.length) {
        console.warn("Commons Broadcast: unmatched category terms", unmatchedTerms);
      }
    } catch (e) {
      // A field handler catches its own errors above — this only fires for
      // something breaking runFill itself (e.g. the ready_selector wait
      // throwing). Recorded, not rethrown, so the finally block below still
      // runs and the SPA still gets a definitive ack instead of hanging.
      ranOk = false;
      errorMessage = String((e && e.message) || e);
      console.error("Commons Broadcast:", e);
    } finally {
      showBanner(recipe);
      highlightTargets(recipe);
      sendCompletionAck({
        ok: ranOk && fieldsFailed === 0,
        error: errorMessage,
        fieldsTotal,
        fieldsFailed,
        unmatchedTerms: unmatchedTerms.slice(),
        venueMatchNotes: venueMatchNotes.slice(),
        imageAttempted,
        imageOk,
      });
    }
  }

  // Fire-and-forget to the background worker — it forwards this to whatever
  // SPA tab is waiting on a "fill" port (see background.js). No response is
  // expected; if the message can't be delivered (e.g. no listener because
  // this fill was dispatched via the older one-shot sendFill), that's fine —
  // the SPA-side timeout is the backstop for a missing ack either way.
  function sendCompletionAck(summary) {
    try {
      chrome.runtime.sendMessage({ type: "commons-fill-complete", summary });
    } catch (e) {
      console.warn("Commons Broadcast: could not send completion ack", e);
    }
  }

  // --- value setters -------------------------------------------------------

  function setNativeValue(el, value) {
    // Use the prototype setter so React/controlled inputs see the change.
    const proto =
      el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : el instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value");
    if (setter && setter.set) setter.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Some selectors target a <label> (e.g. abc11 #eventStartDate-label) — fall
  // back to the input the label points at.
  function resolveInput(selector) {
    const el = document.querySelector(selector);
    if (el && el.tagName === "LABEL") {
      const forId = el.getAttribute("for");
      if (forId) return document.getElementById(forId) || el;
      return el.querySelector("input, textarea, select") || el;
    }
    return el;
  }

  // --- per-type handlers ---------------------------------------------------

  const HANDLERS = {
    text: fillInput,
    textarea: fillInput,
    date: fillInputVerified,
    time: fillInputVerified,
    select: fillInput,
    froala: fillFroala,
    radio: checkInput,
    checkbox: checkInput,
    file: fillFile,
    select2: fillSelect2,
    select2_multi: fillSelect2Multi,
    react_select: fillReactSelect,
    terms: acceptTerms,
    manual_widget: scrollHint,
  };

  function fillInput(field) {
    if (!field.value) return;
    const el = resolveInput(field.selector);
    if (!el) return;
    setNativeValue(el, field.value);
  }

  // Destinations reformat date/time values on commit (e.g. "4:00 pm" ->
  // "4:00pm"), so a strict === against what we wrote never matches — compare
  // through this normalizer instead.
  function normalizeFieldValue(v) {
    return String(v == null ? "" : v)
      .toLowerCase()
      .replace(/\s+/g, "");
  }

  // date/time fields on some forms (e.g. ABC11's Trumba/Fluent UI widgets)
  // self-populate with a near-current default shortly after load, racing our
  // write. Re-read after a short wait and retry if a later default clobbered
  // us. On forms that don't race (e.g. Triangle Weekender's jQuery-UI
  // pickers), the first re-read matches and this is a no-op past attempt 1.
  async function fillInputVerified(field) {
    if (!field.value) return;
    const el = resolveInput(field.selector);
    if (!el) return;

    const attempts = 3;
    const delaysMs = [250, 500, 900];
    const wanted = normalizeFieldValue(field.value);
    for (let i = 0; i < attempts; i++) {
      setNativeValue(el, field.value);
      await sleep(delaysMs[i] || delaysMs[delaysMs.length - 1]);

      // Success — value committed. Destinations reformat what we write (e.g.
      // "4:00 pm" -> "4:00pm"), so compare loosely rather than by ===.
      if (normalizeFieldValue(el.value) === wanted) return;

      if (normalizeFieldValue(el.value) !== wanted) {
        // Value was accepted by the DOM but a controlled React component may
        // not have committed it to state — nudge it with Enter + blur.
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
        el.dispatchEvent(new Event("blur", { bubbles: true }));
        el.dispatchEvent(new Event("focusout", { bubbles: true }));
        await sleep(100);
        if (normalizeFieldValue(el.value) === wanted) return;
      }
    }
    console.warn(
      "Commons Broadcast: date/time field did not hold its value after retries",
      field.selector,
      "expected",
      field.value,
      "got",
      el.value
    );
  }

  // Froala's JS API is unreachable from the content-script world; write directly
  // to the iframe body and fire synthetic events so Froala syncs its ng-model.
  function fillFroala(field) {
    if (!field.value) return;
    const box = findFroalaBox(field.selector);
    if (!box) return;
    const iframe = box.querySelector("iframe.fr-iframe");
    const body = iframe && iframe.contentDocument && iframe.contentDocument.body;
    const html = "<p>" + escapeHtml(field.value).replace(/\n/g, "<br>") + "</p>";
    if (body) {
      body.innerHTML = html;
      for (const type of ["input", "keydown", "keyup", "blur"]) {
        body.dispatchEvent(new Event(type, { bubbles: true }));
      }
    }
    // Some Froala configs read the source <textarea> on submit.
    const orig = document.querySelector(field.selector);
    if (orig && orig.tagName === "TEXTAREA") setNativeValue(orig, field.value);
  }

  function findFroalaBox(selector) {
    const el = document.querySelector(selector);
    if (!el) return null;
    if (el.classList && el.classList.contains("fr-box")) return el;
    let sib = el.nextElementSibling;
    while (sib) {
      if (sib.classList && sib.classList.contains("fr-box")) return sib;
      sib = sib.nextElementSibling;
    }
    return (el.parentElement && el.parentElement.querySelector(".fr-box")) || null;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function checkInput(field) {
    const el = document.querySelector(field.selector);
    if (!el) return;
    if (!el.checked) {
      el.checked = true;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  // Round-trip a message to the background worker over a long-lived port
  // instead of one-shot sendMessage. The open port keeps the service worker
  // alive for the duration of the async work on the other end, and its
  // onDisconnect fires if the worker is torn down mid-flight anyway — turning
  // a silent "message channel closed" failure into an observable rejection.
  // A timeout guards against a hang with no error at all (worker wedged
  // without ever disconnecting the port).
  function sendPortMessageWithTimeout(portName, message, timeoutMs) {
    return new Promise((resolve, reject) => {
      let settled = false;
      let port;

      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        try {
          port && port.disconnect();
        } catch (_) {
          /* already gone */
        }
        reject(new Error(`timed out waiting for "${portName}" response`));
      }, timeoutMs);

      try {
        port = chrome.runtime.connect({ name: portName });
      } catch (e) {
        clearTimeout(timer);
        reject(e);
        return;
      }

      port.onMessage.addListener((response) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try {
          port.disconnect();
        } catch (_) {
          /* already gone */
        }
        resolve(response);
      });

      port.onDisconnect.addListener(() => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        const err = chrome.runtime.lastError;
        reject(
          new Error(
            "background worker disconnected before responding" +
              (err ? `: ${err.message}` : "")
          )
        );
      });

      port.postMessage(message);
    });
  }

  // Fetch image through the background worker (CORS bypass) and assign via
  // DataTransfer. Falls back to a visual hint on error.
  async function fillFile(field) {
    if (!field.value) return;
    const el = document.querySelector(field.selector);
    if (!el) return; // no file input found — nothing to highlight either

    imageAttempted = true;
    try {
      const resp = await sendPortMessageWithTimeout(
        "fetch-image",
        { type: "fetch-image", url: field.value },
        15000
      );
      if (!resp || !resp.ok || !resp.dataUrl) {
        throw new Error(resp ? resp.error : "no response from background");
      }

      const mime = resp.dataUrl.split(";")[0].replace("data:", "") || "image/jpeg";
      const name = fileNameFor(field.value, mime);

      const b64 = resp.dataUrl.split(",")[1];
      const byteStr = atob(b64);
      const ab = new ArrayBuffer(byteStr.length);
      const ia = new Uint8Array(ab);
      for (let i = 0; i < byteStr.length; i++) ia[i] = byteStr.charCodeAt(i);
      const file = new File([ab], name, { type: mime });

      const dt = new DataTransfer();
      dt.items.add(file);
      el.files = dt.files;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.scrollIntoView({ block: "center" });
      imageOk = true;
      return; // success — no fallback needed
    } catch (e) {
      console.warn("Commons Broadcast: image auto-upload failed, falling back to hint:", e);
    }

    fileHintFallback(el);
    showImageErrorBanner();
  }

  // Plausible image extensions only — a Drive/Dropbox "share" URL basename
  // (e.g. "view") is not one, so we synthesize a name from the MIME type
  // instead of ever producing an extensionless filename.
  const _IMAGE_EXT_RE = /\.(jpe?g|png|gif|webp|bmp|svg|avif|heic|heif)$/i;

  function fileNameFor(url, mime) {
    const urlPath = url.split("?")[0].split("#")[0];
    const base = urlPath.split("/").pop() || "";
    if (base && _IMAGE_EXT_RE.test(base)) return base;
    const ext = (mime.split("/")[1] || "jpg").split("+")[0];
    return `event-image.${ext}`;
  }

  function fileHintFallback(el) {
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    outline(el, "#c0392b");
  }

  // Bounded poll for a select2 dropdown's results to actually be ready — its
  // option list (and, for AJAX widgets, a re-filtered list after typing)
  // loads asynchronously and renders nothing in the interim, so a fixed sleep
  // races it (suite 48.4/48.6). "Ready" = at least one non-loading result.
  function waitForSelect2Ready(timeoutMs) {
    return waitFor(() => {
      const opts = document.querySelectorAll(".select2-dropdown li.select2-results__option");
      if (!opts.length) return false;
      for (const o of opts) {
        if (/searching|loading/i.test(o.textContent || "")) return false;
      }
      return true;
    }, timeoutMs);
  }

  // select2 result labels sometimes carry a trailing count (see
  // normalizeSelect2Label below) and Weekender's venue vocabulary carries
  // address-suffixed duplicates of the same place, e.g. "Durham Central Park"
  // vs "Durham Central Park @ 501 Foster St" — strip that suffix too before
  // comparing.
  function normalizeVenueLabel(text) {
    return (text || "")
      .replace(/\(\d+\)\s*$/, "")
      .replace(/\s*@\s*.+$/, "")
      .trim()
      .toLowerCase()
      .replace(/&/g, "and")
      .replace(/[’']/g, "")
      .replace(/[–—]/g, "-")
      .replace(/\s+/g, " ")
      .trim();
  }

  function venueTokenSet(text) {
    return new Set(
      normalizeVenueLabel(text)
        .replace(/[^\w\s-]/g, " ")
        .split(/\s+/)
        .filter(Boolean)
    );
  }

  function sameTokenSet(a, b) {
    if (a.size !== b.size) return false;
    for (const t of a) if (!b.has(t)) return false;
    return true;
  }

  // Ranked matcher for the venue/organizer "Create or Find" widgets (suite
  // 48.6). Tiers: exact normalized match, then prefix, then a normalized
  // token-set match — never plain substring, keeping suite 46's anchoring
  // discipline. Ties within a tier prefer the shortest label (the bare venue
  // name over an address-suffixed variant).
  function rankedVenueMatch(options, query, getLabel) {
    const normQuery = normalizeVenueLabel(query);
    if (!normQuery) return null;
    const queryTokens = venueTokenSet(query);

    const exact = [];
    const prefix = [];
    const token = [];
    for (const opt of options) {
      const rawLabel = (getLabel(opt) || "").trim();
      const normLabel = normalizeVenueLabel(rawLabel);
      if (!normLabel) continue;
      if (normLabel === normQuery) exact.push({ opt, rawLabel });
      else if (normLabel.startsWith(normQuery)) prefix.push({ opt, rawLabel });
      else if (sameTokenSet(venueTokenSet(rawLabel), queryTokens)) token.push({ opt, rawLabel });
    }
    for (const tier of [exact, prefix, token]) {
      if (tier.length) {
        tier.sort((a, b) => a.rawLabel.length - b.rawLabel.length);
        return tier[0];
      }
    }
    return null;
  }

  // Hardcoded select2 driver (Triangle Weekender/Chatham Arts "Create or
  // Find" venue/organizer widgets). Fragile by design — fix on break. Reuses
  // an existing option on a ranked match (see rankedVenueMatch) instead of
  // always falling through to "Create: <text>" — the live vocabularies are
  // huge (~1653 venues, ~1959 organizers) and every unmatched reuse creates a
  // duplicate on a public calendar. Never invents an option: the "Create"
  // sentinel (-1 OrganizerID) is preserved as the fallback path.
  async function fillSelect2(field) {
    if (!field.value) return;
    const id = field.selector.replace(/^#/, "");
    const $ = window.jQuery;
    let opened = false;
    if ($ && $("#" + id).data && $("#" + id).data("select2")) {
      try {
        $("#" + id).select2("open");
        opened = true;
      } catch (_) {
        opened = false;
      }
    }
    if (!opened) {
      const select = document.getElementById(id);
      const container = select && select.parentElement
        ? select.parentElement.querySelector(".select2-selection")
        : null;
      if (container) container.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    }
    await waitForSelect2Ready(4000);
    const search = document.querySelector(".select2-dropdown .select2-search__field");
    if (!search) return;
    setNativeValue(search, field.value);
    search.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
    // AJAX-backed widget — typing re-queries the server, so wait again for a
    // ready (non-loading) result set rather than a fixed sleep.
    await waitForSelect2Ready(3000);

    const options = [
      ...document.querySelectorAll(".select2-dropdown li.select2-results__option"),
    ];
    let create = null;
    const candidates = [];
    for (const opt of options) {
      const label = (opt.textContent || "").trim();
      if (label.toLowerCase().startsWith("create")) {
        create = opt;
        continue;
      }
      candidates.push(opt);
    }
    const ranked = rankedVenueMatch(candidates, field.value, (opt) => opt.textContent);
    const chosen = ranked ? ranked.opt : create || options[0];
    if (ranked) {
      venueMatchNotes.push({ field: field.label || field.selector, matched: ranked.rawLabel });
    }
    if (chosen) chosen.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  }

  // select2 result labels sometimes carry a trailing count, e.g.
  // "Music (12)" — strip it, normalize a few punctuation variants the verified
  // vocabularies use (&, /, apostrophes, en-dashes), and collapse whitespace
  // before comparing.
  function normalizeSelect2Label(text) {
    return (text || "")
      .replace(/\(\d+\)\s*$/, "")
      .replace(/&/g, "and")
      .replace(/[’']/g, "")
      .replace(/[–—]/g, "-")
      .replace(/\//g, " ")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  // Ranked match against a list of option elements: exact normalized match
  // first, then a prefix match (candidate label starts with the search term).
  // No substring/token-set fallback — with ABC11's slash-compounds and TW's 62
  // terms that produces false positives (e.g. "Market" pulling in "Art Market
  // and Exhibition"), and the corrected category maps make it unnecessary.
  function bestLabelMatch(options, term, getLabel) {
    const norm = normalizeSelect2Label(term);
    if (!norm) return null;
    let prefix = null;
    for (const opt of options) {
      const label = normalizeSelect2Label(getLabel(opt));
      if (!label) continue;
      if (label === norm) return opt;
      if (!prefix && label.startsWith(norm)) prefix = opt;
    }
    return prefix;
  }

  // Multi-taxonomy select2 driver (Tribe Events categories). field.value is a
  // comma-separated list; a term is chosen on an exact (normalized) label
  // match, else a prefix match (see bestLabelMatch) — loose substring matching
  // pulled in unrelated site terms (e.g. "Market" matching "Art Market and
  // Exhibition"). The search box never actually filters the AJAX dropdown (it
  // always renders the full ~62-term vocabulary), so we match against whatever
  // renders rather than waiting on a query that never fires. Unmatched terms
  // are reported via unmatchedTerms, never silently dropped.
  //
  // suite 48.4: the same event filled 3x produced 12/0/4 matched terms. The
  // options list here (like the venue/organizer list above) loads
  // asynchronously and renders nothing until the dropdown actually opens —
  // the old code assumed a single click was enough and then raced that load
  // with a fixed 250ms sleep. When the open+render happened to land inside
  // that window every term matched (12); when it landed late for the *first*
  // term the query ran against zero rendered options and every term in that
  // run failed (0); a load that finished mid-loop explains the partial (4).
  // Nothing here points at the matcher itself (bestLabelMatch) — it's a pure
  // function over whatever options are handed to it. Fix: replace the fixed
  // sleep with a bounded poll on a real readiness condition (waitForSelect2Ready,
  // shared with fillSelect2 above) before reading the option list.
  async function fillSelect2Multi(field) {
    const terms = (field.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!terms.length) return;

    // The <select> is aria-hidden; the visible select2 container is next sibling.
    const selectEl = document.querySelector(field.selector);
    if (!selectEl) return;
    const container = selectEl.nextElementSibling;
    if (!container || !container.classList.contains("select2-container")) return;

    for (const term of terms) {
      let resolved = false; // set once this term is either matched or explicitly recorded as unmatched
      try {
        const searchInput = container.querySelector(".select2-search__field");
        if (!searchInput) continue;

        searchInput.click();
        // The full ~62-term vocabulary loads asynchronously and renders
        // nothing until the widget opens — poll for real readiness instead of
        // a fixed sleep (see the 48.4 note above).
        const ready = await waitForSelect2Ready(4000);
        if (!ready) {
          // Kept (not temporary): distinguishes "widget never finished
          // loading" from "term genuinely absent from the vocabulary" — both
          // land in unmatchedTerms below, but only this one means the site
          // was slow/unresponsive rather than the category map being wrong.
          console.warn("Commons Broadcast: select2 options never became ready for term", term);
        }

        setNativeValue(searchInput, term);
        searchInput.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));

        // The typed term never actually filters this dropdown (bug A) — the
        // options polled for above are already the full list, so no further
        // wait is needed once `ready` is true.
        const options = ready
          ? [
              ...document.querySelectorAll(
                ".select2-dropdown li.select2-results__option:not(.select2-results__option--disabled)"
              ),
            ]
          : [];
        const match = bestLabelMatch(options, term, (opt) => opt.textContent);

        if (match) {
          match.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          await sleep(300); // let select2 register the selection
          resolved = true;
        } else {
          unmatchedTerms.push({ field: field.label || field.selector, term });
          resolved = true;
          document.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
          );
          setNativeValue(searchInput, "");
          await sleep(150);
        }
      } catch (e) {
        // Never throw out of the term loop — but never let a term vanish
        // silently either (that was the core defect, suite 48.4). Record it
        // as unmatched below if the try block didn't already resolve it.
        console.warn("Commons Broadcast: category term errored", term, e);
      } finally {
        if (!resolved) {
          unmatchedTerms.push({ field: field.label || field.selector, term });
        }
      }
    }
  }

  // react-select typeahead driver (ABC11 Category). field.value is a comma-
  // separated list; a term is chosen on an exact (normalized) label match,
  // else a prefix match (see bestLabelMatch), against the controlled
  // vocabulary. Unmatched terms are reported via unmatchedTerms, never
  // silently dropped.
  async function fillReactSelect(field) {
    const terms = (field.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!terms.length) return;

    const input = document.querySelector(field.selector);
    if (!input) return;

    for (const term of terms) {
      try {
        input.focus();
        // react-select filters off the input's value change.
        setNativeValue(input, term);
        await sleep(900); // let the menu render/filter

        const options = [
          ...document.querySelectorAll(
            ".customSelect__option, [class*='__option']"
          ),
        ].filter(
          (o) =>
            (o.textContent || "").trim() && o.getAttribute("aria-disabled") !== "true"
        );
        const match = bestLabelMatch(options, term, (opt) => opt.textContent);

        if (match) {
          // react-select selects on mousedown.
          match.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
          match.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          match.click();
          await sleep(300);
        } else {
          unmatchedTerms.push({ field: field.label || field.selector, term });
        }
        setNativeValue(input, "");
        await sleep(150);
      } catch (_) {
        // Never throw out of the term loop — skip and continue.
      }
    }
  }

  // Hardcoded terms acceptance (Triangle Weekender): scroll the terms region to
  // the bottom so the plugin enables the checkbox, then check it.
  async function acceptTerms(field) {
    const region = document.querySelector(".tec-event-terms-description");
    if (region) {
      region.scrollTop = region.scrollHeight;
      region.dispatchEvent(new Event("scroll", { bubbles: true }));
      await sleep(300);
    }
    const box = document.querySelector(field.selector);
    if (!box) return;
    box.disabled = false;
    if (!box.checked) {
      box.checked = true;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function scrollHint(field) {
    const el = document.querySelector(field.selector);
    if (el) {
      el.scrollIntoView({ block: "center" });
      outline(el, "#d35400");
    }
  }

  // --- visual aids ---------------------------------------------------------

  function outline(el, color) {
    el.style.outline = `3px solid ${color}`;
    el.style.outlineOffset = "2px";
  }

  function highlightTargets(recipe) {
    if (recipe.submit_selector) {
      const submit = document.querySelector(recipe.submit_selector);
      if (submit) outline(submit, "#27ae60");
    }
  }

  function showBanner(recipe) {
    if (document.getElementById("commons-broadcast-banner")) return;
    const bar = document.createElement("div");
    bar.id = "commons-broadcast-banner";
    const unmatched = unmatchedTerms.length
      ? ` Not applied — not found in this site's list, set manually: ${unmatchedTerms
          .map((u) => u.term)
          .join(", ")}.`
      : "";
    const venueNotes = venueMatchNotes.length
      ? ` ${venueMatchNotes
          .map((n) => `${n.field} matched to existing "${n.matched}"`)
          .join("; ")}.`
      : "";
    bar.textContent =
      `The Commons is filling this form — sit back and relax.${unmatched}${venueNotes} When it's done, review everything, solve any captcha, then click Submit yourself.`;
    Object.assign(bar.style, {
      position: "fixed",
      top: "0",
      left: "0",
      right: "0",
      zIndex: "2147483647",
      background: "#1b1b1b",
      color: "#f5f0e6",
      font: "16px/1.5 Georgia, 'Times New Roman', serif",
      padding: "12px 16px",
      textAlign: "center",
      boxShadow: "0 2px 8px rgba(0,0,0,.3)",
    });
    document.documentElement.appendChild(bar);
  }

  function showImageErrorBanner() {
    if (document.getElementById("commons-broadcast-image-error")) return;
    const bar = document.createElement("div");
    bar.id = "commons-broadcast-image-error";
    bar.textContent =
      "The Commons: couldn't fetch that image. Upload it manually below, or paste a direct image link (ending in .jpg/.png/etc.) instead of a page link.";
    Object.assign(bar.style, {
      position: "fixed",
      top: "44px",
      left: "0",
      right: "0",
      zIndex: "2147483647",
      background: "#c0392b",
      color: "#fff",
      font: "16px/1.5 Georgia, 'Times New Roman', serif",
      padding: "10px 16px",
      textAlign: "center",
      boxShadow: "0 2px 8px rgba(0,0,0,.3)",
    });
    document.documentElement.appendChild(bar);
  }
})();
