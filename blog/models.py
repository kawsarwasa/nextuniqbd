from pathlib import Path

from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models import ProtectedError
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.utils import timezone


def delete_file_if_unused(model, field_name, file_name, exclude_pk=None):
    if not file_name:
        return

    queryset = model.objects.filter(**{field_name: file_name})
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)

    if queryset.exists():
        return

    if default_storage.exists(file_name):
        default_storage.delete(file_name)


class BlogCategory(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name", "id"]
        verbose_name = "Blog Category"
        verbose_name_plural = "Blog Categories"
        db_table = "blog_category"

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "blog-category"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    def save(self, *args, **kwargs):
        self.slug = self.build_unique_slug(self.name, instance=self)
        super().save(*args, **kwargs)

    def safe_delete(self):
        with transaction.atomic():
            try:
                self.delete()
                return True
            except ProtectedError:
                self.is_active = False
                self.save(update_fields=["is_active", "updated_at"])
                return False


class BlogTag(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Blog Tag"
        verbose_name_plural = "Blog Tags"
        db_table = "blog_tag"

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "blog-tag"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    def save(self, *args, **kwargs):
        self.slug = self.build_unique_slug(self.name, instance=self)
        super().save(*args, **kwargs)

    def safe_delete(self):
        self.delete()
        return True


class BlogPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.PROTECT,
        related_name="posts",
    )
    tags = models.ManyToManyField(
        BlogTag,
        blank=True,
        related_name="posts",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=275, unique=True, blank=True)
    author_name = models.CharField(max_length=120, default="Dashboard User")
    excerpt = models.TextField(blank=True)
    content = models.TextField(blank=True)
    featured_image = models.ImageField(upload_to="blog/posts/featured/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    allow_comments = models.BooleanField(default=True)
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at", "-id"]
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"
        db_table = "blog_post"

    def __str__(self):
        return self.title

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "blog-post"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    def save(self, *args, **kwargs):
        old_featured_image = None
        if self.pk:
            old_featured_image = (
                BlogPost.objects.filter(pk=self.pk).values_list("featured_image", flat=True).first()
            )

        self.slug = self.build_unique_slug(self.title, instance=self)

        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        elif self.status != self.Status.PUBLISHED and self.published_at and not self.pk:
            self.published_at = None

        super().save(*args, **kwargs)

        new_featured_image = self.featured_image.name if self.featured_image else None
        if old_featured_image and old_featured_image != new_featured_image:
            delete_file_if_unused(BlogPost, "featured_image", old_featured_image, exclude_pk=self.pk)

    def delete(self, *args, **kwargs):
        featured_image_name = self.featured_image.name if self.featured_image else None
        if self.featured_image:
            self.featured_image.close()
        super().delete(*args, **kwargs)
        delete_file_if_unused(BlogPost, "featured_image", featured_image_name)

    @property
    def primary_image(self):
        if self.featured_image:
            return self.featured_image

        card_images = getattr(self, "card_images", None)
        if card_images is not None:
            return card_images[0].image if card_images else None

        prefetched_images = getattr(self, "_prefetched_objects_cache", {}).get("images")
        if prefetched_images is not None:
            ordered_images = sorted(prefetched_images, key=lambda image: (image.sort_order, image.id))
            return ordered_images[0].image if ordered_images else None

        first_image = self.images.order_by("sort_order", "id").first()
        return first_image.image if first_image else None

    @property
    def comment_total(self):
        if hasattr(self, "_comment_count"):
            return self._comment_count

        prefetched_comments = getattr(self, "_prefetched_objects_cache", {}).get("comments")
        if prefetched_comments is not None:
            return len(prefetched_comments)
        return self.comments.count()


class BlogPostImage(models.Model):
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="blog/posts/gallery/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Blog Post Image"
        verbose_name_plural = "Blog Post Images"
        db_table = "blog_post_image"

    def __str__(self):
        file_stem = slugify(Path(self.image.name).stem) if self.image else self.pk
        return f"{self.post.title} image {file_stem}"


class BlogComment(models.Model):
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author_name = models.CharField(max_length=120)
    author_email = models.EmailField(blank=True)
    body = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Blog Comment"
        verbose_name_plural = "Blog Comments"
        db_table = "blog_comment"

    def __str__(self):
        return f"{self.author_name} on {self.post.title}"


@receiver(post_delete, sender=BlogPostImage)
def delete_blog_post_image_file(sender, instance, **kwargs):
    if instance.image:
        delete_file_if_unused(BlogPostImage, "image", instance.image.name, exclude_pk=instance.pk)
