from django.contrib import admin

from .models import OrderStatusHistory


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "changed_at", "changed_by", "source")
    list_filter = ("status", "source")
    search_fields = ("order__order_id", "order__full_name", "changed_by__username")
    readonly_fields = ("order", "status", "changed_at", "changed_by", "note", "source", "created_at")
    ordering = ("-changed_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
