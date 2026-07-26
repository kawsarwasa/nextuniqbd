from io import BytesIO
from pathlib import Path
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.template.defaultfilters import slugify
from django.utils import timezone
from PIL import Image, ImageOps

User = get_user_model()


class RoleProfile(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="role_profile",
    )
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group__name", "group__id"]
        verbose_name = "Role Profile"
        verbose_name_plural = "Role Profiles"

    def __str__(self):
        return self.group.name


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="dashboard_profile",
    )
    image = models.ImageField(upload_to="user_profiles/", blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__id"]
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return self.user.email or self.user.username

    @staticmethod
    def _delete_image_file(file_name, *, defer_on_permission_error=False):
        if not file_name:
            return

        if UserProfile.objects.filter(image=file_name).exists():
            return

        storage = UserProfile._meta.get_field("image").storage
        if storage.exists(file_name):
            try:
                file_path = Path(storage.path(file_name))
                file_path.chmod(0o666)
                file_path.unlink(missing_ok=True)
            except (AttributeError, NotImplementedError):
                storage.delete(file_name)
            except PermissionError:
                if defer_on_permission_error:
                    transaction.on_commit(lambda: UserProfile._delete_image_file(file_name))
                else:
                    raise

    def save(self, *args, **kwargs):
        old_image_name = None
        old_profile = None
        if self.pk:
            old_profile = UserProfile.objects.filter(pk=self.pk).only("image").first()
            old_image_name = old_profile.image.name if old_profile and old_profile.image else None

        super().save(*args, **kwargs)

        new_image_name = self.image.name if self.image else None
        if old_profile and old_profile.image:
            old_profile.image.close()
        if old_image_name and old_image_name != new_image_name:
            self._delete_image_file(old_image_name, defer_on_permission_error=True)

    def delete(self, *args, **kwargs):
        image_name = self.image.name if self.image else None
        if self.image:
            self.image.close()
        super().delete(*args, **kwargs)
        if image_name:
            self._delete_image_file(image_name, defer_on_permission_error=True)


class AbandonedCheckout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Converted"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abandoned_checkouts",
    )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    full_name = models.CharField(max_length=150, null=True, blank=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    district = models.CharField(max_length=120, null=True, blank=True)
    area_thana = models.CharField(max_length=120, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    delivery_area = models.CharField(max_length=40, null=True, blank=True)
    cart_items = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=50, default="checkout_page")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "updated_at"], name="sitepages_ac_user_idx"),
            models.Index(fields=["session_key", "status", "updated_at"], name="sitepages_ac_session_idx"),
        ]
        verbose_name = "Abandoned Checkout"
        verbose_name_plural = "Abandoned Checkouts"

    def __str__(self):
        identity = self.phone_number or self.email or self.session_key or f"#{self.pk}"
        return f"{identity} ({self.get_status_display()})"


class Order(models.Model):
    ORDER_ID_LENGTH = 12
    ORDER_ID_ALPHABET = string.ascii_uppercase + string.digits

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    order_id = models.CharField(max_length=12, unique=True, db_index=True)
    order_date = models.DateTimeField(auto_now_add=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
    address = models.TextField()
    district = models.CharField(max_length=120)
    thana = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    order_notes = models.TextField(blank=True)
    payment_method = models.CharField(max_length=80, default="Cash on Delivery")
    delivery_zone = models.CharField(max_length=40, blank=True)
    delivery_label = models.CharField(max_length=120, blank=True)
    delivery_estimate = models.CharField(max_length=120, blank=True)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return self.order_id

    @classmethod
    def valid_next_statuses(cls, status):
        return {
            cls.Status.PENDING: (cls.Status.PACKED, cls.Status.CANCELLED),
            cls.Status.PACKED: (cls.Status.SHIPPED, cls.Status.CANCELLED),
            cls.Status.SHIPPED: (cls.Status.DELIVERED, cls.Status.CANCELLED),
            cls.Status.DELIVERED: (cls.Status.CONFIRMED, cls.Status.RETURNED),
            cls.Status.CONFIRMED: (),
            cls.Status.CANCELLED: (),
            cls.Status.RETURNED: (),
        }.get(status, ())

    @classmethod
    def generate_order_id_candidate(cls):
        while True:
            candidate = "".join(secrets.choice(cls.ORDER_ID_ALPHABET) for _ in range(cls.ORDER_ID_LENGTH))
            if any(character.isalpha() for character in candidate) and any(character.isdigit() for character in candidate):
                return candidate

    @classmethod
    def generate_unique_order_id(cls):
        candidate = cls.generate_order_id_candidate()
        while cls.objects.filter(order_id=candidate).exists():
            candidate = cls.generate_order_id_candidate()
        return candidate

    def save(self, *args, **kwargs):
        self._status_changed_on_save = False
        if self.pk:
            previous_status = Order.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            self._status_changed_on_save = previous_status != self.status
            self._previous_status_on_save = previous_status
            if (
                self._status_changed_on_save
                and not getattr(self, "_status_change_via_service", False)
                and self.status not in self.valid_next_statuses(previous_status)
            ):
                raise ValidationError("Invalid order status transition. Use the order status service.")

        if not self.order_id:
            self.order_id = self.generate_unique_order_id()
        with transaction.atomic():
            super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    class Source(models.TextChoices):
        CHECKOUT = "checkout", "Checkout"
        DASHBOARD = "dashboard", "Dashboard"
        PAYMENT = "payment", "Payment"
        SHIPMENT = "shipment", "Shipment"
        API = "api", "API"
        SYSTEM = "system", "System"
        IMPORTED = "imported", "Imported"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    previous_status = models.CharField(max_length=20, choices=Order.Status.choices, blank=True)
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_at = models.DateTimeField(default=timezone.now, db_index=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    note = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.SYSTEM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "id"]
        verbose_name = "Order Status History"
        verbose_name_plural = "Order Status History"
        indexes = [
            models.Index(fields=["order", "changed_at"]),
            models.Index(fields=["order", "status", "changed_at"]),
        ]

    def __str__(self):
        return f"{self.order.order_id}: {self.get_status_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "category.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=255)
    product_slug = models.SlugField(max_length=275, blank=True)
    product_sku = models.CharField(max_length=64, blank=True)
    category_name = models.CharField(max_length=150, blank=True)
    brand_name = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        return f"{self.order.order_id} - {self.product_name}"


class SaleManager(models.Manager):
    def generate_from_order(self, order):
        sale, created = self.get_or_create(
            order=order,
            defaults={
                "sale_id": Sale.build_sale_id(order),
                "user": order.user,
                "full_name": order.full_name,
                "phone": order.phone,
                "email": order.email,
                "payment_method": order.payment_method,
                "subtotal_amount": order.subtotal_amount,
                "shipping_amount": order.shipping_amount,
                "total_amount": order.total_amount,
                "item_count": order.item_count,
            },
        )

        existing_order_item_ids = set(
            sale.items.values_list("order_item_id", flat=True)
        )
        SaleItem.objects.bulk_create(
            [
                SaleItem(
                    sale=sale,
                    order_item=order_item,
                    product=order_item.product,
                    product_name=order_item.product_name,
                    product_sku=order_item.product_sku,
                    category_name=order_item.category_name,
                    brand_name=order_item.brand_name,
                    quantity=order_item.quantity,
                    unit_price=order_item.unit_price,
                    subtotal=order_item.subtotal,
                )
                for order_item in order.items.all()
                if order_item.pk not in existing_order_item_ids
            ]
        )
        return sale, created


class Sale(models.Model):
    SALE_ID_PREFIX = "S"

    sale_id = models.CharField(max_length=13, unique=True, db_index=True)
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="sale",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )
    sale_date = models.DateTimeField(auto_now_add=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
    payment_method = models.CharField(max_length=80, default="Cash on Delivery")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    item_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SaleManager()

    class Meta:
        ordering = ["-sale_date", "-id"]
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def __str__(self):
        return self.sale_id

    @classmethod
    def build_sale_id(cls, order):
        return f"{cls.SALE_ID_PREFIX}{order.order_id}"


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="sale_item",
    )
    product = models.ForeignKey(
        "category.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_items",
    )
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=64, blank=True)
    category_name = models.CharField(max_length=150, blank=True)
    brand_name = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Sale Item"
        verbose_name_plural = "Sale Items"

    def __str__(self):
        return f"{self.sale.sale_id} - {self.product_name}"


class OrderStockApplication(models.Model):
    """The quantity from a packed order line currently deducted from stock."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="stock_applications",
    )
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_application",
    )
    product = models.ForeignKey(
        "category.Product",
        on_delete=models.PROTECT,
        related_name="order_stock_applications",
    )
    applied_quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Stock Application"
        verbose_name_plural = "Order Stock Applications"

    def __str__(self):
        return f"{self.order.order_id}: {self.product} ({self.applied_quantity})"


class HeroSlide(models.Model):
    IMAGE_SIZE = (1400, 600)

    class ContentAlignment(models.TextChoices):
        LEFT = "left", "Left"
        RIGHT = "right", "Right"
        CENTER = "center", "Center"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    eyebrow = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255)
    title_highlight = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="hero_slides/")
    primary_button_label = models.CharField(max_length=80, blank=True)
    primary_button_url = models.CharField(max_length=255, blank=True)
    secondary_button_label = models.CharField(max_length=80, blank=True)
    secondary_button_url = models.CharField(max_length=255, blank=True)
    content_alignment = models.CharField(
        max_length=20,
        choices=ContentAlignment.choices,
        default=ContentAlignment.LEFT,
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Hero Slide"
        verbose_name_plural = "Hero Slides"

    def __str__(self):
        return self.name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "hero-slide"
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
        old_image_name = None
        if self.pk:
            old_image_name = HeroSlide.objects.filter(pk=self.pk).values_list("image", flat=True).first()

        self.slug = self.build_unique_slug(self.name or self.title, instance=self)

        if self.image and (
            not getattr(self.image, "_committed", True) or old_image_name != self.image.name
        ):
            self._normalize_image()

        super().save(*args, **kwargs)

    def _normalize_image(self):
        if not self.image:
            return

        self.image.open()
        image = None
        normalized = None
        output = BytesIO()

        try:
            image = Image.open(self.image)
            image = ImageOps.exif_transpose(image)

            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

            normalized = ImageOps.fit(image, self.IMAGE_SIZE, Image.Resampling.LANCZOS)
            if normalized.mode != "RGB":
                normalized = normalized.convert("RGB")

            normalized.save(output, format="JPEG", quality=90, optimize=True)
            output.seek(0)

            file_stem = slugify(self.name or self.title) or "hero-slide"
            self.image.save(f"{file_stem}.jpg", ContentFile(output.read()), save=False)
        finally:
            if image is not None:
                image.close()
            if normalized is not None:
                normalized.close()
            output.close()
            self.image.close()


class HomepagePromoBanner(models.Model):
    class Placement(models.TextChoices):
        LARGE = "large", "Large Banner"
        SMALL = "small", "Small Banner"

    name = models.CharField(max_length=150)
    placement = models.CharField(max_length=20, choices=Placement.choices, default=Placement.SMALL)
    eyebrow = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=180)
    image = models.ImageField(upload_to="promo_banners/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True)
    button_label = models.CharField(max_length=80, blank=True)
    button_url = models.CharField(max_length=255, blank=True)
    use_dark_overlay = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["placement", "sort_order", "id"]
        verbose_name = "Homepage Promo Banner"
        verbose_name_plural = "Homepage Promo Banners"

    def __str__(self):
        return self.name

    @property
    def display_image_url(self):
        if self.image:
            return self.image.url
        return self.image_url

    def clean(self):
        super().clean()
        if not self.image and not self.image_url:
            raise ValidationError("Upload an image or provide an image URL.")

        if self.is_active:
            active_limit = 1 if self.placement == self.Placement.LARGE else 2
            queryset = HomepagePromoBanner.objects.filter(
                placement=self.placement,
                is_active=True,
            )
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)
            if queryset.count() >= active_limit:
                label = "large banner" if self.placement == self.Placement.LARGE else "small banners"
                raise ValidationError(f"Only {active_limit} active {label} can be shown on the homepage.")


