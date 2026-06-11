"""Step A of the adapter-scaffolding workflow (design doc §10): deterministic
capture of a site's form controls.

    uv run python manage.py scaffold_adapter --url <submission_url> --key <site_key> [--headed]

Writes broadcast/adapters/_scaffold/<site_key>/{schema.json,page.png,adapter.py.draft}.
Step B (writing the real fill_and_submit) is the scaffolding skill —
see broadcast/adapters/_scaffold/SKILL.md.
"""
import json
import pathlib

from django.core.management.base import BaseCommand, CommandError
from playwright.sync_api import sync_playwright

from broadcast.runner import CHROMIUM_ARGS

SCAFFOLD_DIR = pathlib.Path(__file__).resolve().parents[2] / "adapters" / "_scaffold"

CAPTURE_JS = """
() => {
  const controls = [];
  const labelFor = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return lab.textContent.trim();
    }
    const wrapping = el.closest("label");
    if (wrapping) return wrapping.textContent.trim();
    return el.getAttribute("aria-label") || el.getAttribute("placeholder") || "";
  };
  const locatorFor = (el, label) => {
    if (label) return `page.get_by_label(${JSON.stringify(label)})`;
    if (el.id) return `page.locator("#" + ${JSON.stringify(el.id)})`;
    if (el.name) return `page.locator(${JSON.stringify(`[name='${el.name}']`)})`;
    return "";
  };
  document.querySelectorAll("input, textarea, select").forEach((el) => {
    if (el.type === "hidden") return;
    const label = labelFor(el);
    const control = {
      tag: el.tagName.toLowerCase(),
      type: el.type || "",
      name: el.name || "",
      id: el.id || "",
      label,
      required: el.required || false,
      locator: locatorFor(el, label),
    };
    if (el.tagName === "SELECT") {
      control.options = Array.from(el.options).map((o) => o.textContent.trim());
      control.multiple = el.multiple;
    }
    controls.push(control);
  });
  return controls;
}
"""

DRAFT_TEMPLATE = '''from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import TRIANGLE, Eligibility

# TODO: static category mapping for this site — pick from schema.json <select> options.
_CAT_MAP = {{}}

# TODO: map canonical fields to the labels captured in schema.json.
_FIELDS = {{
{field_stubs}
}}


class {class_name}(SiteAdapter):
    key = "{key}"
    name = "TODO"
    submission_url = "{url}"
    requires_auth = False
    # TODO: set real eligibility (see the site rules table, design doc §6).
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())

    def fill_and_submit(self, page, ev, ctx):
        return standard_fill_and_submit(
            self, page, ev, ctx,
            fields=_FIELDS,
            cat_map=_CAT_MAP,
            categories_label=None,   # TODO
            image_label=None,        # TODO
            submit_button="Submit",  # TODO
        )
'''


class Command(BaseCommand):
    help = "Capture a site's submission form (schema.json + page.png + adapter draft)."

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True, help="submission form URL")
        parser.add_argument("--key", required=True, help="site_key for the new adapter")
        parser.add_argument("--headed", action="store_true", help="show the browser")

    def handle(self, *args, **options):
        key = options["key"]
        if not key.replace("_", "").isalnum():
            raise CommandError("--key must be a snake_case identifier")
        out_dir = SCAFFOLD_DIR / key
        out_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not options["headed"], args=CHROMIUM_ARGS)
            try:
                page = browser.new_context().new_page()
                page.goto(options["url"], timeout=60_000)
                page.wait_for_load_state("domcontentloaded")
                controls = page.evaluate(CAPTURE_JS)
                page.screenshot(path=str(out_dir / "page.png"), full_page=True)
            finally:
                browser.close()

        (out_dir / "schema.json").write_text(json.dumps(controls, indent=2))

        field_stubs = "\n".join(
            f'    # TODO map: {c["tag"]}[{c["type"]}] name={c["name"]!r} → '
            f'FieldSpec({c["label"]!r}{", required=True" if c["required"] else ""}),'
            for c in controls
        ) or "    # (no controls detected — the form may render via JS after interaction)"
        class_name = "".join(part.capitalize() for part in key.split("_")) + "Adapter"
        (out_dir / "adapter.py.draft").write_text(DRAFT_TEMPLATE.format(
            field_stubs=field_stubs, class_name=class_name, key=key, url=options["url"],
        ))

        self.stdout.write(self.style.SUCCESS(
            f"captured {len(controls)} controls → {out_dir}/\n"
            "Next: run the scaffolding skill (broadcast/adapters/_scaffold/SKILL.md) "
            "to turn the draft into a real adapter, then verify with broadcast_dry_run."
        ))
