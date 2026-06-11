# Skill: Generate a Broadcast Site Adapter

Dev-time only. LLM use is allowed **here** — never in the runtime path. The
adapter you produce must be fully deterministic: every value it posts comes
from the `CanonicalEvent` or from static constants defined in the adapter file.

## Inputs

After running Step A:

```bash
cd backendServer
uv run python manage.py scaffold_adapter --url <submission_url> --key <site_key> [--headed]
```

you have, in `broadcast/adapters/_scaffold/<site_key>/`:

- `schema.json` — every form control: tag, type, name/id, label, required, `<select>` options, best-guess locator
- `page.png` — full-page screenshot of the form
- `adapter.py.draft` — starter adapter with one TODO per detected control

Reference material:

- `broadcast/schema.py` — the canonical event fields you may map from (nothing else)
- `broadcast/routing.py` — controlled `locality`/`categories` vocabularies and `Eligibility`
- The site rules table in `DESIGN_BROADCAST.md` §6 — the eligibility for this site
- `broadcast/adapters/_generic.py` — the standard flow most adapters can reuse
- `broadcast/adapters/triangle_on_the_cheap.py` — a finished example

## Procedure

1. Read `schema.json` and look at `page.png`. Identify which control receives
   each canonical field (title, description, start date/time, venue, address,
   URLs, price, contacts, image upload).
2. Build `_FIELDS`: a `dict[str, FieldSpec]` mapping canonical field names
   (see `_generic._field_values`) to the **labels captured in schema.json**.
   Mark a field `required=True` only if the site marks it required.
3. Build `_CAT_MAP`: map our controlled category slugs to this site's actual
   `<select>` option strings from `schema.json`. Only include real options —
   if a category has no sensible mapping, leave it out (routing/eligibility
   handles exclusion; never invent an option).
4. Set `eligibility` from the §6 site rules table.
5. If the form is a plain labeled form, finish via `standard_fill_and_submit`.
   If it needs multi-step navigation, custom widgets (date pickers, rich-text
   editors), or iframe embeds, write `fill_and_submit` by hand using the
   captured locators — but keep the hard rules:
   - dry-run never clicks final submit
   - CAPTCHA / bot-check / login wall → `needs_manual` (use `_helpers.has_captcha`)
   - missing required data → `needs_manual` with a clear error
   - screenshot before submit, and after on success (`_helpers.take_screenshot`)
6. Move the finished file to `broadcast/adapters/<site_key>.py` and register it
   in `broadcast/adapters/__init__.py` (`_TIER1` list).

## Verify

```bash
uv run python manage.py broadcast_dry_run --site <site_key> --fixture pittsboro_music.json
```

Inspect the screenshot. Only after a clean **real-site dry run** may the
adapter be used for live submissions.
