"""Base contract every site adapter implements.

Hard rules (design doc §8):
1. Only use `ev` fields or static constants defined in the adapter. Never
   invent event content. No runtime LLM.
2. Missing required field → return needs_manual with a clear error.
3. CAPTCHA / bot-check / login wall → needs_manual. Never bypass.
4. Respect ctx.dry_run: fill but never click final submit.
5. Screenshot before (and after, on success) submit.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from broadcast.routing import Eligibility
    from broadcast.schema import CanonicalEvent

# Field types the shared Playwright loop (_helpers.apply_specs) can fill itself.
# Everything else (radio/checkbox/file/select2/terms/manual_widget) is driven
# by per-adapter imperative code on the server path and by the browser-extension
# content script on the manual path.
FILLABLE_TYPES = frozenset({"text", "textarea", "date", "time", "select"})

# Recipe field types that are always emitted by recipe(), even when their
# resolved value is empty — the manual-review content script needs to know they
# exist (and how to drive them) regardless.
_ALWAYS_EMIT_TYPES = frozenset(
    {"radio", "checkbox", "file", "select2", "terms", "manual_widget"}
)


@dataclass
class RunContext:
    dry_run: bool
    screenshot_dir: str
    download_dir: str
    submission_id: str = ""
    timeout_ms: int = 30_000


@dataclass
class TargetResult:
    status: str  # "succeeded" | "failed" | "needs_manual" | "skipped"
    external_url: str = ""
    error: str = ""
    screenshot_path: str = ""


@dataclass
class RecipeField:
    """One form field, declared once and consumed by both paths.

    `resolve` maps a CanonicalEvent to the pre-formatted string the field
    expects (use the same `_helpers` formatters the imperative code uses so the
    two paths can't diverge). `recipe_only` fields are exported in recipe() but
    skipped by the shared Playwright fill loop (their server-side handling lives
    in the adapter's imperative code).
    """
    selector: str
    type: str
    resolve: Callable[["CanonicalEvent"], str]
    required: bool = False
    label: str = ""
    hint: str = ""
    recipe_only: bool = False

    def value_for(self, ev: "CanonicalEvent") -> str:
        try:
            value = self.resolve(ev)
        except Exception:
            return ""
        return "" if value is None else str(value)


class SiteAdapter:
    key: str
    name: str
    submission_url: str
    requires_auth: bool = False
    eligibility: "Eligibility"

    # Declarative field map. Adapters that support manual review populate this;
    # override recipe_field_specs() when the set of fields depends on the event.
    recipe_fields: list[RecipeField] = []
    submit_selector: str = ""
    captcha_hint: str = ""

    def fill_and_submit(self, page: "Page", ev: "CanonicalEvent", ctx: RunContext) -> TargetResult:
        raise NotImplementedError

    def recipe_field_specs(self, ev: "CanonicalEvent") -> list[RecipeField]:
        """Fields for this event. Default: the static list. Override when the
        field set is event-dependent (conditional times, per-locality checkboxes)."""
        return self.recipe_fields

    def recipe(self, ev: "CanonicalEvent") -> dict:
        """JSON the manual-review extension fills. Plain (no serializer)."""
        fields = []
        for spec in self.recipe_field_specs(ev):
            value = spec.value_for(ev)
            if not value and not spec.required and spec.type not in _ALWAYS_EMIT_TYPES:
                continue
            fields.append({
                "selector": spec.selector,
                "type": spec.type,
                "value": value,
                "required": spec.required,
                "label": spec.label,
                "hint": spec.hint or None,
            })
        return {
            "site_key": self.key,
            "name": self.name,
            "url": self.submission_url,
            "fields": fields,
            "captcha_hint": self.captcha_hint or None,
            "submit_selector": self.submit_selector,
        }
