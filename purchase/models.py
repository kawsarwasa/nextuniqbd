import secrets
import string
from decimal import Decimal

from django.db import models
from django.db.models import Sum


class Purchase(models.Model):
    PURCHASE_ID_LENGTH = 12
    PURCHASE_ID_ALPHABET = string.digits

    purchase_id = models.CharField(max_length=12, unique=True, db_index=True)
    purchase_date = models.DateTimeField(auto_now_add=True)
    category = models.ForeignKey(
        "category.Category",
        on_delete=models.PROTECT,
        related_name="purchases",
        null=True,
        blank=True,
    )
    brand = models.ForeignKey(
        "category.Brand",
        on_delete=models.PROTECT,
        related_name="purchases",
        null=True,
        blank=True,
    )
    supplier_name = models.CharField(max_length=150, blank=True)
    supplier_phone = models.CharField(max_length=50, blank=True)
    supplier_address = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchase_date", "-id"]
        verbose_name = "Purchase"
        verbose_name_plural = "Purchases"

    def __str__(self):
        return self.purchase_id

    @classmethod
    def generate_purchase_id_candidate(cls):
        return "".join(secrets.choice(cls.PURCHASE_ID_ALPHABET) for _ in range(cls.PURCHASE_ID_LENGTH))

    @classmethod
    def generate_unique_purchase_id(cls):
        candidate = cls.generate_purchase_id_candidate()
        while cls.objects.filter(purchase_id=candidate).exists():
            candidate = cls.generate_purchase_id_candidate()
        return candidate

    def refresh_total(self, *, save=True):
        self.total_amount = self.items.aggregate(total=Sum("subtotal"))["total"] or 0
        if save:
            self.save(update_fields=["total_amount", "updated_at"])
        return self.total_amount

    def save(self, *args, **kwargs):
        if not self.purchase_id:
            self.purchase_id = self.generate_unique_purchase_id()
        super().save(*args, **kwargs)


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "category.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_items",
    )
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Purchase Item"
        verbose_name_plural = "Purchase Items"

    def __str__(self):
        return f"{self.purchase.purchase_id} - {self.product_name}"

    def save(self, *args, **kwargs):
        if self.product_id:
            self.product_name = self.product.name
        quantity = Decimal(self.quantity or 0)
        unit_price = Decimal(str(self.unit_price or 0))
        self.subtotal = quantity * unit_price
        super().save(*args, **kwargs)


class PurchaseStockApplication(models.Model):
    """The quantity from a received purchase line currently applied to stock."""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="stock_applications",
    )
    purchase_item = models.OneToOneField(
        PurchaseItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_application",
    )
    product = models.ForeignKey(
        "category.Product",
        on_delete=models.PROTECT,
        related_name="purchase_stock_applications",
    )
    applied_quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase Stock Application"
        verbose_name_plural = "Purchase Stock Applications"

    def __str__(self):
        return f"{self.purchase.purchase_id}: {self.product} ({self.applied_quantity})"
