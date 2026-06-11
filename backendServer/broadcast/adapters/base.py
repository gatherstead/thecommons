"""Base contract every site adapter implements.

Hard rules (design doc §8):
1. Only use `ev` fields or static constants defined in the adapter. Never
   invent event content. No runtime LLM.
2. Missing required field → return needs_manual with a clear error.
3. CAPTCHA / bot-check / login wall → needs_manual. Never bypass.
4. Respect ctx.dry_run: fill but never click final submit.
5. Screenshot before (and after, on success) submit.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from broadcast.routing import Eligibility
    from broadcast.schema import CanonicalEvent


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


class SiteAdapter:
    key: str
    name: str
    submission_url: str
    requires_auth: bool = False
    eligibility: "Eligibility"

    def fill_and_submit(self, page: "Page", ev: "CanonicalEvent", ctx: RunContext) -> TargetResult:
        raise NotImplementedError
