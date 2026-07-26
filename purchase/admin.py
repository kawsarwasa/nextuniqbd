from django.contrib import admin

from .models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("purchase_id", "purchase_date", "category", "brand", "supplier_name", "total_amount")
    search_fields = ("purchase_id", "supplier_name", "supplier_phone")
    list_filter = ("category", "brand")
    inlines = [PurchaseItemInline]
