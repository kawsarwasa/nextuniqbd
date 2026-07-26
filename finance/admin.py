from decimal import Decimal

from django.contrib import admin
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .models import CashTransaction, DueAccount, DuePayment, TransactionSource, TransactionCategory


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category_type", "is_active", "created_at")
    list_filter = ("category_type", "is_active")
    search_fields = ("name",)
    ordering = ("category_type", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_date",
        "transaction_type",
        "category",
        "amount",
        "payment_method",
        "reference",
        "source_type",
        "linked_due_payment",
        "created_by",
        "created_at",
    )
    list_filter = ("transaction_type", "category", "payment_method", "source_type", "transaction_date")
    search_fields = ("description", "reference", "category__name", "created_by__username", "created_by__email")
    date_hierarchy = "transaction_date"
    list_select_related = ("category", "created_by", "due_payment")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Due payment")
    def linked_due_payment(self, obj):
        return obj.due_payment if obj.source_type == TransactionSource.DUE_PAYMENT else "—"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.source_type != TransactionSource.MANUAL:
            readonly.extend(
                [
                    "transaction_date",
                    "transaction_type",
                    "category",
                    "description",
                    "amount",
                    "payment_method",
                    "reference",
                    "source_type",
                    "created_by",
                ]
            )
        return tuple(dict.fromkeys(readonly))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.source_type != TransactionSource.MANUAL:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(DueAccount)
class DueAccountAdmin(admin.ModelAdmin):
    list_display = (
        "due_date",
        "party_name",
        "due_type",
        "original_amount",
        "paid_amount_display",
        "balance_due_display",
        "status_display_value",
        "due_deadline",
        "created_by",
    )
    list_filter = ("due_type", "due_date", "due_deadline")
    search_fields = ("party_name", "phone", "description", "reference")
    date_hierarchy = "due_date"
    list_select_related = ("created_by",)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("created_by")
            .annotate(
                _paid_amount=Coalesce(
                    Sum("payments__amount"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )

    @admin.display(description="Paid amount", ordering="_paid_amount")
    def paid_amount_display(self, obj):
        return obj.paid_amount

    @admin.display(description="Balance due")
    def balance_due_display(self, obj):
        return obj.balance_due

    @admin.display(description="Status")
    def status_display_value(self, obj):
        return obj.status_display


@admin.register(DuePayment)
class DuePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_date",
        "due",
        "amount",
        "payment_method",
        "reference",
        "cash_transaction",
        "created_by",
        "created_at",
    )
    list_filter = ("payment_method", "payment_date", "due__due_type")
    search_fields = ("due__party_name", "reference", "notes")
    date_hierarchy = "payment_date"
    list_select_related = ("due", "created_by", "cash_transaction")
    readonly_fields = (
        "due",
        "payment_date",
        "amount",
        "payment_method",
        "reference",
        "notes",
        "cash_transaction",
        "created_by",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
