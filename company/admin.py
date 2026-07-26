from django.contrib import admin

from .models import CompanyProfile


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("company_name", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
