from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction

from category.models import Product, StockTransaction

from .models import Order, OrderStockApplication


def _locked_products(product_ids):
    return {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=sorted(product_ids))
    }


def _validate_stock_changes(products, quantity_changes):
    for product_id, quantity_change in quantity_changes.items():
        if quantity_change >= 0:
            continue
        product = products[product_id]
        required = abs(quantity_change)
        if product.stock_quantity < required:
            raise ValidationError(
                f"Insufficient stock for {product.name}. Only {product.stock_quantity} available."
            )


def _save_stock_changes(products, quantity_changes, *, order, user, reversal_type, reversal_note=None):
    for product_id in sorted(quantity_changes):
        quantity_change = quantity_changes[product_id]
        if not quantity_change:
            continue

        product = products[product_id]
        product.stock_quantity += quantity_change
        product.save(update_fields=["stock_quantity", "availability", "updated_at"])
        StockTransaction.objects.create(
            product=product,
            transaction_type=(
                StockTransaction.TransactionType.SALE
                if quantity_change < 0
                else reversal_type
            ),
            quantity_change=quantity_change,
            balance_after=product.stock_quantity,
            reference=f"Order {order.order_id}",
            note=("Packed order" if quantity_change < 0 else (reversal_note or "Packed order stock restored.")),
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )


@transaction.atomic
def sync_packed_order_stock(order_id, *, user=None):
    """Apply a packed order's current quantities to stock exactly once.

    Per-line applications are the idempotency marker. All involved products are
    locked and validated before any quantity is changed, so an insufficient line
    rolls back the complete order operation.
    """
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PACKED:
        return

    items = list(order.items.select_related("product").select_for_update())
    applications = list(
        OrderStockApplication.objects.select_for_update()
        .select_related("product")
        .filter(order=order)
    )
    applications_by_item = {
        application.order_item_id: application
        for application in applications
        if application.order_item_id is not None
    }
    current_item_ids = {item.pk for item in items}
    changes = defaultdict(int)
    application_updates = []
    application_creations = []

    # Deleted lines are restored once; their application remains as the audit
    # marker with a zero applied quantity.
    for application in applications:
        if application.order_item_id not in current_item_ids and application.applied_quantity:
            changes[application.product_id] += application.applied_quantity
            application_updates.append((application, application.product_id, 0))

    for item in items:
        product = item.product
        application = applications_by_item.get(item.pk)

        if product is None:
            if application is not None and application.applied_quantity:
                changes[application.product_id] += application.applied_quantity
                application_updates.append((application, application.product_id, 0))
            continue

        if application is None:
            if product.track_stock:
                changes[product.pk] -= item.quantity
                application_creations.append((item, product.pk, item.quantity))
            continue

        if application.product_id != product.pk:
            if application.applied_quantity:
                changes[application.product_id] += application.applied_quantity
            if product.track_stock:
                changes[product.pk] -= item.quantity
                new_applied_quantity = item.quantity
            else:
                new_applied_quantity = 0
            application_updates.append((application, product.pk, new_applied_quantity))
            continue

        if not product.track_stock:
            if application.applied_quantity:
                changes[product.pk] += application.applied_quantity
                application_updates.append((application, product.pk, 0))
            continue

        new_applied_quantity = item.quantity
        changes[product.pk] += application.applied_quantity - new_applied_quantity
        if new_applied_quantity != application.applied_quantity:
            application_updates.append((application, product.pk, new_applied_quantity))

    products = _locked_products(changes.keys())
    _validate_stock_changes(products, changes)
    _save_stock_changes(
        products,
        changes,
        order=order,
        user=user,
        reversal_type=StockTransaction.TransactionType.SALE_RETURN,
        reversal_note="Packed order stock adjustment restored.",
    )

    for application, product_id, applied_quantity in application_updates:
        application.product_id = product_id
        application.applied_quantity = applied_quantity
        application.save(update_fields=["product", "applied_quantity", "updated_at"])
    for item, product_id, applied_quantity in application_creations:
        OrderStockApplication.objects.create(
            order=order,
            order_item=item,
            product_id=product_id,
            applied_quantity=applied_quantity,
        )


@transaction.atomic
def reverse_confirmed_order_stock(
    order_id,
    *,
    user=None,
    reversal_type=StockTransaction.TransactionType.ORDER_CANCELLATION,
    reversal_note="Packed order stock restored.",
):
    """Return all stock still deducted by a cancelled or returned order exactly once."""
    order = Order.objects.select_for_update().get(pk=order_id)
    applications = list(
        OrderStockApplication.objects.select_for_update()
        .filter(order=order, applied_quantity__gt=0)
    )
    changes = defaultdict(int)
    for application in applications:
        changes[application.product_id] += application.applied_quantity

    products = _locked_products(changes.keys())
    _save_stock_changes(
        products,
        changes,
        order=order,
        user=user,
        reversal_type=reversal_type,
        reversal_note=reversal_note,
    )
    for application in applications:
        application.applied_quantity = 0
        application.save(update_fields=["applied_quantity", "updated_at"])


@transaction.atomic
def validate_checkout_stock(cart_state):
    """Lock and validate the cart just before its pending order is created."""
    requested_quantities = defaultdict(int)
    for item in cart_state["items"]:
        requested_quantities[item["product_id"]] += item["quantity"]

    products = _locked_products(requested_quantities.keys())
    if len(products) != len(requested_quantities):
        raise ValidationError("One or more products are no longer available.")

    for product_id, quantity in requested_quantities.items():
        product = products[product_id]
        if product.status != Product.Status.PUBLISHED:
            raise ValidationError(f"{product.name} is no longer available.")
        if product.track_stock and product.stock_quantity < quantity:
            raise ValidationError(
                f"Insufficient stock for {product.name}. Only {product.stock_quantity} available."
            )
