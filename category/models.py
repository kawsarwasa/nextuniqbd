from io import BytesIO
from pathlib import Path
import secrets
import string

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Avg
from django.db.models import ProtectedError
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from PIL import Image, ImageOps

from .image_derivatives import generate_product_image_derivatives, product_image_variant_url


class Category(models.Model):
    IMAGE_SIZE = (600, 600)
    DEFAULT_ICON_CLASS = "fa fa-tag"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    short_description = models.CharField(max_length=255, blank=True)
    icon_class = models.CharField(max_length=64, blank=True, default=DEFAULT_ICON_CLASS)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    show_on_homepage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"], name="cat_home_active_sort"),
        ]
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        db_table = "category_category"

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "category"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    @staticmethod
    def _delete_image_file(file_name):
        if not file_name:
            return

        if Category.objects.filter(image=file_name).exists():
            return

        storage = Category._meta.get_field("image").storage
        if storage.exists(file_name):
            storage.delete(file_name)

    def _normalize_image(self):
        if not self.image:
            return

        self.image.open()
        image = None
        contained_image = None
        background = None
        output = BytesIO()

        try:
            image = Image.open(self.image)
            image = ImageOps.exif_transpose(image)

            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

            contained_image = ImageOps.contain(image, self.IMAGE_SIZE, Image.Resampling.LANCZOS)
            background = Image.new("RGB", self.IMAGE_SIZE, "white")
            offset = (
                (self.IMAGE_SIZE[0] - contained_image.width) // 2,
                (self.IMAGE_SIZE[1] - contained_image.height) // 2,
            )

            if contained_image.mode == "RGBA":
                background.paste(contained_image, offset, contained_image)
            else:
                background.paste(contained_image, offset)

            background.save(output, format="JPEG", quality=90, optimize=True)
            output.seek(0)

            file_stem = slugify(Path(self.image.name).stem) or "category"
            self.image.save(f"{file_stem}.jpg", ContentFile(output.read()), save=False)
        finally:
            if image is not None:
                image.close()
            if contained_image is not None:
                contained_image.close()
            if background is not None:
                background.close()
            output.close()
            self.image.close()

    def save(self, *args, **kwargs):
        old_image_name = None
        if self.pk:
            old_image_name = Category.objects.filter(pk=self.pk).values_list("image", flat=True).first()

        self.slug = self.build_unique_slug(self.name, instance=self)

        if self.image and (
            not getattr(self.image, "_committed", True) or old_image_name != self.image.name
        ):
            self._normalize_image()

        super().save(*args, **kwargs)

        new_image_name = self.image.name if self.image else None
        if old_image_name and old_image_name != new_image_name:
            self._delete_image_file(old_image_name)

    def delete(self, *args, **kwargs):
        image_name = self.image.name if self.image else None
        if self.image:
            self.image.close()
        super().delete(*args, **kwargs)
        if image_name:
            self._delete_image_file(image_name)

    def safe_delete(self):
        with transaction.atomic():
            try:
                self.delete()
                return True
            except ProtectedError:
                self.is_active = False
                self.show_on_homepage = False
                self.save(update_fields=["is_active", "show_on_homepage", "updated_at"])
                return False


class Brand(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="brands/logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    show_on_homepage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        db_table = "category_brand"

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "brand"
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
                self.show_on_homepage = False
                self.save(update_fields=["is_active", "show_on_homepage", "updated_at"])
                return False


class Product(models.Model):
    SKU_PREFIX = "NUB"
    SKU_LENGTH = 12
    SKU_RANDOM_LENGTH = SKU_LENGTH - len(SKU_PREFIX)
    SKU_ALPHABET = string.ascii_uppercase + string.digits

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        INACTIVE = "inactive", "Inactive"

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=275, unique=True, blank=True)
    regular_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    sku = models.CharField(max_length=SKU_LENGTH, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField(default=False)
    availability = models.CharField(max_length=100, blank=True)
    track_stock = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    short_description = models.TextField(blank=True)
    full_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Product"
        verbose_name_plural = "Products"
        db_table = "category_product"
        indexes = [
            models.Index(
                fields=["status", "category", "-created_at"],
                name="prod_home_status_cat_date",
            ),
            models.Index(
                fields=["status", "is_featured", "-created_at"],
                name="prod_home_featured_date",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name="product_stock_quantity_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(low_stock_threshold__gte=0),
                name="product_low_threshold_nonnegative",
            ),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "product"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    @classmethod
    def generate_sku_candidate(cls):
        suffix = "".join(
            secrets.choice(cls.SKU_ALPHABET) for _ in range(cls.SKU_RANDOM_LENGTH)
        )
        return f"{cls.SKU_PREFIX}{suffix}"

    @classmethod
    def is_valid_sku(cls, value):
        if not isinstance(value, str) or len(value) != cls.SKU_LENGTH:
            return False
        return value.startswith(cls.SKU_PREFIX) and all(
            character in cls.SKU_ALPHABET for character in value[len(cls.SKU_PREFIX):]
        )

    @classmethod
    def generate_unique_sku(cls):
        sku = cls.generate_sku_candidate()
        while cls.objects.filter(sku=sku).exists():
            sku = cls.generate_sku_candidate()
        return sku

    def save(self, *args, **kwargs):
        self.slug = self.build_unique_slug(self.name, instance=self)
        if not self.is_valid_sku(self.sku):
            self.sku = self.generate_unique_sku()
        if self.track_stock:
            self.availability = "In Stock" if self.stock_quantity > 0 else "Out of Stock"
        super().save(*args, **kwargs)

    @property
    def stock_status(self):
        if not self.track_stock:
            return "not_tracked"
        if self.stock_quantity == 0:
            return "out_of_stock"
        if self.stock_quantity <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"

    @property
    def stock_status_label(self):
        if self.stock_status == "not_tracked":
            return "Not Tracked"
        if self.stock_status == "out_of_stock":
            return "Out of Stock"
        return "In Stock"

    @property
    def is_low_stock(self):
        return self.stock_status == "low_stock"

    @property
    def discount_percentage(self):
        if self.regular_price and self.current_price < self.regular_price:
            return round((self.regular_price - self.current_price) / self.regular_price * 100)
        return None

    @property
    def primary_image(self):
        card_images = getattr(self, "card_images", None)
        if card_images is not None:
            return card_images[0] if card_images else None

        prefetched_images = getattr(self, "_prefetched_objects_cache", {}).get("images")
        if prefetched_images is not None:
            ordered_images = sorted(prefetched_images, key=lambda image: (image.sort_order, image.id))
            return ordered_images[0] if ordered_images else None
        return self.images.order_by("sort_order", "id").first()

    @property
    def review_count(self):
        if hasattr(self, "_review_count"):
            return self._review_count

        prefetched_reviews = getattr(self, "_prefetched_objects_cache", {}).get("reviews")
        if prefetched_reviews is not None:
            return len(prefetched_reviews)
        return self.reviews.count()

    @property
    def average_rating(self):
        if hasattr(self, "_average_rating"):
            return round(self._average_rating or 0, 1)

        prefetched_reviews = getattr(self, "_prefetched_objects_cache", {}).get("reviews")
        if prefetched_reviews is not None:
            if not prefetched_reviews:
                return 0
            return round(sum(review.rating for review in prefetched_reviews) / len(prefetched_reviews), 1)

        return round(self.reviews.aggregate(avg_rating=Avg("rating"))["avg_rating"] or 0, 1)


class StockTransaction(models.Model):
    class TransactionType(models.TextChoices):
        OPENING_STOCK = "opening_stock", "Opening Stock"
        MANUAL_ADJUSTMENT = "manual_adjustment", "Manual Adjustment"
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        PURCHASE_RETURN = "purchase_return", "Purchase Return"
        SALE_RETURN = "sale_return", "Sale Return"
        ORDER_CANCELLATION = "order_cancellation", "Order Cancellation"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_transactions",
    )
    transaction_type = models.CharField(max_length=32, choices=TransactionType.choices)
    quantity_change = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reference = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_stock_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Stock Transaction"
        verbose_name_plural = "Stock Transactions"
        db_table = "category_stock_transaction"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_change__gt=0) | models.Q(quantity_change__lt=0),
                name="stocktxn_quantity_change_nonzero",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "-created_at"], name="stocktxn_product_date"),
        ]

    def __str__(self):
        return f"{self.product.name}: {self.get_transaction_type_display()} ({self.quantity_change:+d})"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        db_table = "category_product_image"
        indexes = [
            models.Index(fields=["product", "sort_order"], name="prodimg_product_sort"),
        ]

    def __str__(self):
        return f"{self.product.name} image {self.pk}"

    @property
    def card_url(self):
        return product_image_variant_url(self.image, "card")

    @property
    def detail_url(self):
        return product_image_variant_url(self.image, "detail")

    def save(self, *args, **kwargs):
        image_changed = bool(self.image) and (
            not getattr(self.image, "_committed", True)
            or not self.pk
            or "image" in (kwargs.get("update_fields") or ())
        )
        super().save(*args, **kwargs)
        if image_changed:
            generate_product_image_derivatives(self.image)


class ProductReview(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    reviewer_name = models.CharField(max_length=120)
    reviewer_email = models.EmailField(blank=True)
    title = models.CharField(max_length=180)
    body = models.TextField()
    rating = models.PositiveSmallIntegerField()
    verified_purchase = models.BooleanField(default=False)
    helpful_yes = models.PositiveIntegerField(default=0)
    helpful_no = models.PositiveIntegerField(default=0)
    review_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-review_date", "-id"]
        verbose_name = "Product Review"
        verbose_name_plural = "Product Reviews"
        db_table = "category_product_review"

    def __str__(self):
        return f"{self.product.name} review by {self.reviewer_name}"

    @property
    def reviewer_initials(self):
        parts = [part[:1].upper() for part in self.reviewer_name.split() if part]
        return "".join(parts[:2]) or "RV"

    @property
    def empty_stars(self):
        return max(5 - self.rating, 0)


@receiver(post_delete, sender=ProductImage)
def delete_product_image_file(sender, instance, **kwargs):
    if not instance.image or not instance.image.name:
        return

    # Keep sidecar variants in sync with their source image.  Check for another
    # record using the same file name before removing anything from storage.
    if ProductImage.objects.filter(image=instance.image.name).exists():
        return

    storage = instance.image.storage
    for name in (
        instance.image.name,
        product_image_variant_name(instance.image.name, "card"),
        product_image_variant_name(instance.image.name, "detail"),
    ):
        if storage.exists(name):
            storage.delete(name)
