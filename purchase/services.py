from django.core.exceptions import ValidationError
from django.db import transaction

from category.models import Product, StockTransaction

from .models import Purchase, PurchaseStockApplication


def _save_product_stock(product, quantity_change, *, transaction_type, reference, note, user):
    """Apply one non-zero, validated movement to a locked tracked product."""
    if not quantity_change:
        return

    if quantity_change < 0 and product.stock_quantity < abs(quantity_change):
        raise ValidationError(
            f"Cannot reverse {abs(quantity_change)} unit(s) of {product.name}; "
            f"only {product.stock_quantity} unit(s) are available."
        )

    product.stock_quantity += quantity_change
    product.save(update_fields=["stock_quantity", "availability", "updated_at"])
    StockTransaction.objects.create(
        product=product,
        transaction_type=transaction_type,
        quantity_change=quantity_change,
        balance_after=product.stock_quantity,
        reference=reference,
        note=note,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def _reverse_application(application, *, user, reason):
    """Reverse an already-applied line once, without permitting negative stock."""
    if not application.applied_quantity:
        return

    product = Product.objects.select_for_update().get(pk=application.product_id)
    _save_product_stock(
        product,
        -application.applied_quantity,
        transaction_type=StockTransaction.TransactionType.PURCHASE_RETURN,
        reference=f"Purchase {application.purchase.purchase_id} / item {application.purchase_item_id or 'removed'}",
        note=reason,
        user=user,
    )
    application.applied_quantity = 0
    application.save(update_fields=["applied_quantity", "updated_at"])


@transaction.atomic
def sync_received_purchase_stock(purchase_id, *, user=None):
    """Synchronize received purchase lines with stock exactly once per line quantity.

    The purchase row, its applications, and each affected product are locked.  The
    persisted applied quantity is the idempotency marker: re-saving unchanged
    purchase lines produces no stock movement, while edited quantities apply only
    their difference.
    """
    purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
    items = list(purchase.items.select_related("product").select_for_update())
    applications = list(
        PurchaseStockApplication.objects.select_for_update()
        .select_related("product", "purchase")
        .filter(purchase=purchase)
    )
    applications_by_item = {
        application.purchase_item_id: application
        for application in applications
        if application.purchase_item_id is not None
    }
    current_item_ids = {item.pk for item in items}

    # A formset-deleted line retains its application with a null item. Reverse it
    # once before considering the currently received lines.
    for application in applications:
        if application.purchase_item_id not in current_item_ids:
            _reverse_application(application, user=user, reason="Purchase item removed")

    for item in items:
        product = item.product
        application = applications_by_item.get(item.pk)

        if product is None:
            if application is not None:
                _reverse_application(application, user=user, reason="Purchase product removed")
            continue

        if application is not None and application.product_id != product.pk:
            _reverse_application(application, user=user, reason="Purchase product changed")
            application.product = product
            application.applied_quantity = 0
            application.save(update_fields=["product", "applied_quantity", "updated_at"])

        # Products that do not track stock are deliberately left without an
        # application or transaction.
        if not product.track_stock:
            continue

        if application is None:
            application = PurchaseStockApplication.objects.create(
                purchase=purchase,
                purchase_item=item,
                product=product,
            )

        quantity_change = item.quantity - application.applied_quantity
        if not quantity_change:
            continue

        locked_product = Product.objects.select_for_update().get(pk=product.pk)
        _save_product_stock(
            locked_product,
            quantity_change,
            transaction_type=(
                StockTransaction.TransactionType.PURCHASE
                if quantity_change > 0
                else StockTransaction.TransactionType.PURCHASE_RETURN
            ),
            reference=f"Purchase {purchase.purchase_id} / item {item.pk}",
            note="Received purchase" if quantity_change > 0 else "Received purchase quantity reduced",
            user=user,
        )
        application.applied_quantity = item.quantity
        application.save(update_fields=["applied_quantity", "updated_at"])


@transaction.atomic
def reverse_received_purchase_stock(purchase_id, *, user=None):
    """Reverse all stock still applied by a received purchase exactly once."""
    purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
    applications = list(
        PurchaseStockApplication.objects.select_for_update()
        .select_related("purchase", "product")
        .filter(purchase=purchase, applied_quantity__gt=0)
    )
    for application in applications:
        _reverse_application(application, user=user, reason="Received purchase reversed")
