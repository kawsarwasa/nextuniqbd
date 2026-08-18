"""Centralized, transactional order-status changes."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Order, OrderStatusHistory, Sale


@dataclass(frozen=True)
class OrderStatusChangeResult:
    order: Order
    previous_status: str
    changed: bool


def _changed_by_user(user):
    return user if getattr(user, "is_authenticated", False) else None


def get_valid_next_statuses(status):
    return Order.valid_next_statuses(status)


def change_order_status(*, order, new_status, changed_by=None, note="", source=OrderStatusHistory.Source.SYSTEM):
    """Change an order status once and record the audit entry in one transaction.

    Callers can wrap this helper in a larger ``transaction.atomic()`` block when
    their workflow also changes stock, payment, or shipment records.
    """
    valid_statuses = {value for value, _label in Order.Status.choices}
    if new_status not in valid_statuses:
        raise ValidationError("Invalid order status.")

    valid_sources = {value for value, _label in OrderStatusHistory.Source.choices}
    if source not in valid_sources:
        raise ValidationError("Invalid order status history source.")

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        previous_status = locked_order.status
        if previous_status == new_status:
            return OrderStatusChangeResult(
                order=locked_order,
                previous_status=previous_status,
                changed=False,
            )

        if new_status not in get_valid_next_statuses(previous_status):
            raise ValidationError(
                f"{locked_order.get_status_display()} orders cannot move directly to "
                f"{dict(Order.Status.choices)[new_status]}."
            )
        if new_status in {Order.Status.CANCELLED, Order.Status.RETURNED} and not note.strip():
            raise ValidationError("A note is required when cancelling or returning an order.")

        locked_order.status = new_status
        locked_order._skip_order_status_history_signal = True
        locked_order._status_change_via_service = True
        locked_order.save(update_fields=["status", "updated_at"])
        OrderStatusHistory.objects.create(
            order=locked_order,
            previous_status=previous_status,
            status=new_status,
            changed_at=timezone.now(),
            changed_by=_changed_by_user(changed_by),
            note=note.strip(),
            source=source,
        )
        from .order_stock import reverse_confirmed_order_stock, sync_packed_order_stock

        if previous_status == Order.Status.PENDING and new_status == Order.Status.PACKED:
            sync_packed_order_stock(locked_order.pk, user=changed_by)
        elif (
            new_status == Order.Status.CANCELLED
            and previous_status in {Order.Status.PACKED, Order.Status.SHIPPED}
        ):
            reverse_confirmed_order_stock(
                locked_order.pk,
                user=changed_by,
                reversal_note="Order cancelled and stock restored.",
            )
        elif previous_status == Order.Status.DELIVERED and new_status == Order.Status.RETURNED:
            reverse_confirmed_order_stock(
                locked_order.pk,
                user=changed_by,
                reversal_type="sale_return",
                reversal_note="Delivered order returned and stock received.",
            )
        elif previous_status == Order.Status.DELIVERED and new_status == Order.Status.CONFIRMED:
            Sale.objects.generate_from_order(locked_order)
            from tracking.services import queue_purchase

            queue_purchase(locked_order)
        return OrderStatusChangeResult(
            order=locked_order,
            previous_status=previous_status,
            changed=True,
        )
