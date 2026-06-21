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
    if (fields.length) {
      await waitFor(() => document.querySelector(fields[0].selector), 8000);
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
    radio: checkInput,
    checkbox: checkInput,
    file: fileHint,
    select2: fillSelect2,
    terms: acceptTerms,
    manual_widget: scrollHint,
  };

  function fillInput(field) {
    if (!field.value) return;
    const el = resolveInput(field.selector);
    if (!el) return;
    setNativeValue(el, field.value);
  }

  function checkInput(field) {
    const el = document.querySelector(field.selector);
    if (!el) return;
    if (!el.checked) {
      el.checked = true;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function fileHint(field) {
    // Browsers forbid programmatic file selection — flag it for the human.
    const el = document.querySelector(field.selector);
    if (el) {
      el.scrollIntoView({ block: "center" });
      outline(el, "#c0392b");
    }
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
})();
