# Validated Patterns

Patterns logged here have been **confirmed in a real session against live code**. Do not add speculative or theoretical advice — only gotchas that bit us in practice.

## Format

```
### <short title>
- **Pattern:** …
- **Where it applies:** …
- **Gotcha:** …
- **Confirmed:** <date>
```

---

## Entries

### Gemini town mismatch silently drops events at publish time

- **Pattern:** During ingestion, `standardize_event()` in `ingestion/standardizer.py` calls Gemini to normalize raw event fields and stores the model's free-text `town` string on the `StagedEvent`. Later, `publish_all_approved()` in `ingestion/services.py` (line 14) resolves that string to a `Town` DB row by slugifying it (`staged.town.lower().replace(' ', '-')`) and querying `Town.objects.filter(slug=…).first()`. If no matching `Town` row exists, the function logs a warning and calls `continue` — the `StagedEvent` is left in the `approved` state but is never published, and no exception or return signal surfaces to the caller.
- **Where it applies:** `backendServer/ingestion/standardizer.py` (Gemini normalization step) + `backendServer/ingestion/services.py::publish_all_approved` (publish loop, around line 46–53). Also affects `ingest_direct_submission` in the same file (same town-slug lookup pattern).
- **Gotcha:** An approved event can vanish silently. The only trace is a `WARNING` log line: `"Dropping staged event '…' — no Town matches slug '…'"`. This happens whenever Gemini returns a town name variant (e.g. `"Chapel Hill, NC"`, `"ch"`, or an unrecognized town) that doesn't slugify to an existing `Town.slug`. Check the `Town` table first when published counts are lower than approved counts.
- **Confirmed:** 2026-07-08
