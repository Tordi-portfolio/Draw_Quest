from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse

from .models import (
    Announcement,
    DepositRequest,
    DepositSettings,
    PointTransaction,
    Profile,
    Submission,
    Task,
    Withdrawal,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "balance", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    # Balance only changes through approvals / credits so the ledger stays accurate.
    readonly_fields = ("balance",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "reward", "is_active", "deadline", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("title", "description")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "reward", "status", "created_at", "reviewed_by")
    list_filter = ("status",)
    search_fields = ("user__username", "task__title")
    readonly_fields = ("reward", "status", "reviewed_by", "reviewed_at")
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="Approve selected (credits users)")
    def approve_selected(self, request, queryset):
        done = 0
        for sub in queryset:
            try:
                sub.approve(request.user)
                done += 1
            except ValueError:
                pass
        self.message_user(request, f"Approved {done} submission(s).", messages.SUCCESS)

    @admin.action(description="Reject selected")
    def reject_selected(self, request, queryset):
        done = 0
        for sub in queryset:
            try:
                sub.reject(request.user, "Rejected by admin.")
                done += 1
            except ValueError:
                pass
        self.message_user(request, f"Rejected {done} submission(s).", messages.SUCCESS)


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "kind", "note", "created_at")
    list_filter = ("kind",)
    search_fields = ("user__username", "note")
    readonly_fields = ("user", "amount", "kind", "note", "submission", "created_by")

    def has_add_permission(self, request):
        return False


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    """Read-only here: review withdrawals in the admin panel so refunds and
    status changes always go through the safe, audited code path."""

    list_display = ("user", "amount", "method", "status", "created_at", "reviewed_by")
    list_filter = ("status", "method")
    search_fields = ("user__username", "payment_reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DepositSettings)
class DepositSettingsAdmin(admin.ModelAdmin):
    """Where you set the wallet address users see on the deposit page.
    Superusers only, one row only. Django's History button records every change."""

    fields = ("wallet_address", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")

    def changelist_view(self, request, extra_context=None):
        obj = DepositSettings.objects.first()
        if obj:
            return redirect(reverse("admin:core_depositsettings_change", args=[obj.pk]))
        return redirect(reverse("admin:core_depositsettings_add"))

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser and not DepositSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    """Read-only here: verify and credit deposits in the admin panel so the
    balance and ledger always change through the safe code path."""

    list_display = ("user", "amount", "credited_amount", "status", "created_at", "reviewed_by")
    list_filter = ("status",)
    search_fields = ("user__username", "tx_hash")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
