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

  async function runFill(recipe) {
    const fields = recipe.fields || [];
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
        console.warn("Commons Broadcast: field failed", field.selector, e);
      }
    }
    showBanner(recipe);
    highlightTargets(recipe);
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
    date: fillInput,
    time: fillInput,
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

  // Fetch image through the background worker (CORS bypass) and assign via
  // DataTransfer. Falls back to a visual hint on error.
  async function fillFile(field) {
    if (!field.value) return;
    const el = document.querySelector(field.selector);
    if (!el) return; // no file input found — nothing to highlight either

    try {
      const resp = await chrome.runtime.sendMessage({
        type: "fetch-image",
        url: field.value,
      });
      if (!resp || !resp.ok || !resp.dataUrl) {
        throw new Error(resp ? resp.error : "no response from background");
      }

      const mime = resp.dataUrl.split(";")[0].replace("data:", "") || "image/jpeg";
      const urlPath = field.value.split("?")[0];
      const name = urlPath.split("/").pop() || `event-image.${mime.split("/")[1] || "jpg"}`;

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
      return; // success — no fallback needed
    } catch (e) {
      console.warn("Commons Broadcast: image auto-upload failed, falling back to hint:", e);
    }

    fileHintFallback(el);
    showImageErrorBanner();
  }

  function fileHintFallback(el) {
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    outline(el, "#c0392b");
  }

  // Hardcoded select2 driver (Triangle Weekender venue/organizer). Fragile by
  // design — fix on break.
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
    await sleep(400);
    const search = document.querySelector(".select2-dropdown .select2-search__field");
    if (!search) return;
    setNativeValue(search, field.value);
    search.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
    await sleep(1000);

    const options = [
      ...document.querySelectorAll(".select2-dropdown li.select2-results__option"),
    ];
    const norm = field.value.trim().toLowerCase();
    let match = null;
    let create = null;
    for (const opt of options) {
      const label = (opt.textContent || "").trim().toLowerCase();
      if (label.startsWith("create")) {
        create = opt;
        continue;
      }
      if (label && (label.includes(norm) || norm.includes(label))) {
        match = match || opt;
      }
    }
    const chosen = match || create || options[0];
    if (chosen) chosen.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  }

  // Multi-taxonomy select2 driver (Tribe Events categories/tags). field.value is
  // a comma-separated list; unmatched terms are skipped silently.
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
      try {
        const searchInput = container.querySelector(".select2-search__field");
        if (!searchInput) continue;

        searchInput.click();
        await sleep(100);
        setNativeValue(searchInput, term);
        searchInput.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));

        await sleep(1200);

        // The dropdown is body-appended.
        const options = [
          ...document.querySelectorAll(
            ".select2-dropdown li.select2-results__option:not(.select2-results__option--disabled)"
          ),
        ];
        const norm = term.trim().toLowerCase();
        let match = null;
        for (const opt of options) {
          const label = (opt.textContent || "").trim().toLowerCase();
          if (!label) continue;
          if (label.includes(norm) || norm.includes(label)) {
            match = match || opt;
          }
        }

        if (match) {
          match.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          await sleep(300); // let select2 register the selection
        } else {
          document.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
          );
          setNativeValue(searchInput, "");
          await sleep(150);
        }
      } catch (_) {
        // Never throw out of the term loop — skip and continue.
      }
    }
  }

  // react-select typeahead driver (ABC11 Category). field.value is a comma-
  // separated list; unmatched terms are skipped silently.
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
        ].filter((o) => (o.textContent || "").trim());
        const first =
          options.find((o) => o.getAttribute("aria-disabled") !== "true") ||
          options[0];

        if (first) {
          // react-select selects on mousedown.
          first.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
          first.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          first.click();
          await sleep(300);
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
    const captcha = recipe.captcha_hint
      ? ` Captcha: ${recipe.captcha_hint}.`
      : "";
    bar.textContent =
      `The Commons: fields filled.${captcha} Review, solve any captcha, then click Submit yourself.`;
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
    bar.textContent = "Image submission error, please manually add the image.";
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
