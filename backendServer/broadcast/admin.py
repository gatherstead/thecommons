import secrets
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline

from broadcast.access import hash_code
from broadcast.models import (
    AccessCode,
    AccessCodeRedemption,
    AccessCodeUse,
    BroadcastAccess,
    BroadcastSubmission,
    BroadcastTarget,
    SalesCodeSlot,
)
from broadcast.sales_codes import ensure_sales_slots, rotate_sales_slot, start_trial_clock


class BroadcastTargetInline(TabularInline):
    model = BroadcastTarget
    extra = 0
    fields = (
        "site_key",
        "status",
        "attempts",
        "dry_run",
        "external_url",
        "error",
        "screenshot_path",
    )
    readonly_fields = fields
    can_delete = False


@admin.register(BroadcastSubmission)
class BroadcastSubmissionAdmin(ModelAdmin):
    list_display = ("title", "client_label", "locality", "status", "created_at", "finished_at")
    list_filter = ("status", "client_label", "locality")
    search_fields = ("title", "venue_name")
    readonly_fields = ("id", "created_at", "started_at", "finished_at")
    inlines = [BroadcastTargetInline]


@admin.register(BroadcastTarget)
class BroadcastTargetAdmin(ModelAdmin):
    list_display = ("site_key", "submission", "status", "attempts", "dry_run", "finished_at")
    list_filter = ("status", "site_key", "dry_run")
    search_fields = ("submission__title", "site_key")
    readonly_fields = ("id", "submission", "started_at", "finished_at")


class AccessCodeUseInline(TabularInline):
    model = AccessCodeUse
    extra = 0
    fields = ("draft_id", "created_at")
    readonly_fields = fields
    can_delete = False
    verbose_name_plural = "Trial preview uses (anonymous, by draft)"


class AccessCodeRedemptionInline(TabularInline):
    model = AccessCodeRedemption
    extra = 0
    fields = ("email", "created_at")
    readonly_fields = fields
    can_delete = False
    verbose_name_plural = "Upgrade redemptions (by account email)"


class AccessCodeAdminForm(forms.ModelForm):
    trial_days = forms.IntegerField(
        required=False,
        min_value=1,
        help_text="Trial codes only — sets the expiry to N days from creation. "
        "Leave blank to fall back to the 3-day default (trial) or no expiry (upgrade).",
    )

    class Meta:
        model = AccessCode
        fields = ["label", "kind", "tier", "max_uses", "is_active", "expires_at"]
        help_texts = {
            "tier": "Ignored for trial codes — trial codes are always tier 2.",
            "max_uses": "Trial: distinct previews. Upgrade: distinct accounts. "
            "Leave blank for unlimited.",
        }


@admin.register(AccessCode)
class AccessCodeAdmin(ModelAdmin):
    """Self-serve code generation — the raw code is shown on creation and stays copyable on the row.

    Also hosts the sales dashboard (3 evergreen codes, one per tier — see
    SalesCodeSlot) as a panel above the changelist table via list_before_template.
    """

    form = AccessCodeAdminForm
    list_before_template = "admin/broadcast/accesscode/sales_slots.html"
    list_display = (
        "label",
        "code",
        "kind",
        "tier",
        "use_count",
        "max_uses",
        "is_active",
        "expires_at",
        "created_at",
    )
    list_filter = ("kind", "tier", "is_active")
    search_fields = ("label", "code")
    readonly_fields = ("code", "code_hash", "created_at", "updated_at")
    inlines = [AccessCodeUseInline, AccessCodeRedemptionInline]

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["label", "kind", "tier", "trial_days", "max_uses", "is_active", "expires_at"]
        return [
            "label",
            "kind",
            "tier",
            "max_uses",
            "is_active",
            "expires_at",
            "code",
            "code_hash",
            "created_at",
            "updated_at",
        ]

    def use_count(self, obj):
        if obj.kind == AccessCode.KIND_TRIAL:
            n = obj.uses.count()
            return f"{n} preview{'s' if n != 1 else ''}"
        n = obj.redemptions.count()
        return f"{n} account{'s' if n != 1 else ''}"

    use_count.short_description = "Used"  # type: ignore[attr-defined]

    def save_model(self, request, obj, form, change):
        raw = None
        if not change:
            raw = secrets.token_urlsafe(24)
            obj.code = raw
            obj.code_hash = hash_code(raw)
            trial_days = form.cleaned_data.get("trial_days")
            if trial_days:
                obj.expires_at = timezone.now() + timedelta(days=trial_days)
            elif obj.kind == AccessCode.KIND_TRIAL and not obj.expires_at:
                obj.expires_at = timezone.now() + timedelta(days=3)
        super().save_model(request, obj, form, change)
        if raw is not None:
            self.message_user(
                request,
                f"Access code for '{obj.label or '(no label)'}': {raw} "
                "— also visible on this row's Code column anytime.",
                level=messages.SUCCESS,
            )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["sales_slots"] = ensure_sales_slots()
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        custom = [
            path(
                "rotate-sales-slot/<str:slot>/",
                self.admin_site.admin_view(self.rotate_sales_slot_view),
                name="broadcast_accesscode_rotate_slot",
            ),
        ]
        return custom + super().get_urls()

    def rotate_sales_slot_view(self, request, slot):
        """POST-only JSON endpoint backing the sales dashboard's Copy button.

        Called after the browser has already copied the *current* code to the
        clipboard — this starts that code's trial clock (its 3 days run from
        hand-off, not from whenever it happened to be minted) and then
        generates the *next* one so the box is pre-loaded for next time. The
        just-copied code is left active, not revoked.
        """
        if request.method != "POST":
            return JsonResponse({"detail": "POST required"}, status=405)
        if slot not in dict(SalesCodeSlot.SLOT_CHOICES):
            return JsonResponse({"detail": "unknown slot"}, status=404)
        copied = SalesCodeSlot.objects.select_related("access_code").filter(slot=slot).first()
        if copied is not None:
            start_trial_clock(copied)
        rotated = rotate_sales_slot(slot)
        return JsonResponse({"slot": slot, "raw_code": rotated.raw_code})


@admin.register(BroadcastAccess)
class BroadcastAccessAdmin(ModelAdmin):
    """Permanent per-account tier grants — set by redeeming an upgrade code, or manually here."""

    list_display = ("email", "tier", "updated_at")
    list_filter = ("tier",)
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at")
