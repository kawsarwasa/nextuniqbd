from django.contrib import admin

from .models import Brand, Category, Product, ProductImage, ProductReview, StockTransaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "icon_class",
        "sort_order",
        "is_active",
        "show_on_homepage",
        "updated_at",
    )
    list_filter = ("is_active", "show_on_homepage")
    search_fields = ("name", "slug", "short_description", "icon_class")
    ordering = ("sort_order", "name", "id")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "is_active",
        "show_on_homepage",
        "updated_at",
    )
    list_filter = ("is_active", "show_on_homepage")
    search_fields = ("name", "slug", "description")
    ordering = ("-id",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductReviewInline(admin.TabularInline):
    model = ProductReview
    extra = 0
    fields = (
        "reviewer_name",
        "title",
        "rating",
        "verified_purchase",
        "review_date",
        "helpful_yes",
        "helpful_no",
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "brand",
        "sku",
        "status",
        "regular_price",
        "current_price",
        "availability",
        "track_stock",
        "stock_quantity",
        "low_stock_threshold",
        "updated_at",
    )
    search_fields = ("name", "sku", "availability")
    list_filter = ("status", "category", "brand")
    ordering = ("-id",)
    readonly_fields = ("sku",)
    inlines = [ProductImageInline, ProductReviewInline]


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "transaction_type",
        "quantity_change",
        "balance_after",
        "reference",
        "created_by",
        "created_at",
    )
    list_filter = ("transaction_type",)
    search_fields = ("product__name", "product__sku", "reference", "note")
    readonly_fields = ("created_at",)
    ordering = ("-created_at", "-id")


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "reviewer_name",
        "title",
        "rating",
        "verified_purchase",
        "review_date",
    )
    list_filter = ("rating", "verified_purchase", "review_date")
    search_fields = ("product__name", "reviewer_name", "title", "body")
    ordering = ("-review_date", "-id")
