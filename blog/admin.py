from django.contrib import admin

from .models import BlogCategory, BlogComment, BlogPost, BlogPostImage, BlogTag


class BlogPostImageInline(admin.TabularInline):
    model = BlogPostImage
    extra = 0


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(BlogTag)
class BlogTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "allow_comments", "published_at", "updated_at")
    list_filter = ("status", "allow_comments", "category")
    search_fields = ("title", "slug", "author_name", "excerpt")
    filter_horizontal = ("tags",)
    inlines = [BlogPostImageInline]


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ("author_name", "post", "is_approved", "created_at")
    list_filter = ("is_approved", "post__category")
    search_fields = ("author_name", "author_email", "body", "post__title")
