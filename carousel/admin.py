from django.contrib import admin

from sitepages.models import HeroSlide


@admin.register(HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "content_alignment", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "content_alignment")
    search_fields = ("name", "title", "eyebrow", "description")
