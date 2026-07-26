"""Shared order-tracking presentation data built from recorded status history."""

from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone

from .models import Order, OrderStatusHistory


ORDER_TRACKING_STEPS = (
    ("placed", "Order Placed", Order.Status.PENDING, "bi-bag-check"),
    ("packed", "Packed", Order.Status.PACKED, "bi-box-seam"),
    ("shipped", "Shipped", Order.Status.SHIPPED, "bi-truck"),
    ("delivered", "Delivered", Order.Status.DELIVERED, "bi-house-check"),
    ("confirmed", "Order Confirmed", Order.Status.CONFIRMED, "bi-patch-check"),
)


def user_can_access_order_tracking(user):
    """Tracking is an internal staff dashboard feature."""
    return bool(
        getattr(user, "is_authenticated", False)
        and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        and (getattr(user, "is_superuser", False) or user.has_perm("sitepages.view_order"))
    )


def get_order_tracking_queryset():
    history_queryset = OrderStatusHistory.objects.select_related("changed_by").order_by("changed_at", "id")
    return Order.objects.select_related("user").prefetch_related(
        Prefetch("status_history", queryset=history_queryset)
    )


def _timestamp_data(history_entry):
    if history_entry is None:
        return {"recorded_at": None, "recorded_at_display": "Not recorded"}
    return {
        "recorded_at": history_entry.changed_at.isoformat(),
        "recorded_at_display": timezone.localtime(history_entry.changed_at).strftime("%b %d, %Y %I:%M %p"),
    }


def _history_user_label(history_entry):
    if history_entry.changed_by_id is None:
        return ""
    return history_entry.changed_by.get_full_name() or history_entry.changed_by.get_username()


def build_order_tracking_context(order):
    """Create a truthful tracking timeline; unrecorded milestones remain unrecorded."""
    history_entries = list(order.status_history.all())
    history_by_status = {}
    for entry in history_entries:
        history_by_status[entry.status] = entry

    current_step_indexes = {
        Order.Status.PENDING: 0,
        Order.Status.PACKED: 1,
        Order.Status.SHIPPED: 2,
        Order.Status.DELIVERED: 3,
        Order.Status.CONFIRMED: 4,
    }
    current_step_index = current_step_indexes.get(order.status)
    is_cancelled = order.status == Order.Status.CANCELLED
    is_returned = order.status == Order.Status.RETURNED
    steps = []
    for index, (key, label, status, icon) in enumerate(ORDER_TRACKING_STEPS):
        entry = history_by_status.get(status) if status else None
        if is_cancelled:
            state = "completed" if entry else "pending"
        elif is_returned:
            state = "completed" if entry else "pending"
        elif current_step_index is not None and index < current_step_index and entry:
            state = "completed"
        elif current_step_index == index:
            state = "current"
        else:
            state = "pending"
        steps.append(
            {
                "key": key,
                "label": label,
                "icon": icon,
                "state": state,
                "note": entry.note if entry else "",
                **_timestamp_data(entry),
            }
        )

    cancellation_entry = history_by_status.get(Order.Status.CANCELLED)
    returned_entry = history_by_status.get(Order.Status.RETURNED)
    events = [
        {
            "status": (
                "Processing (legacy)"
                if entry.status == "processing"
                else entry.get_status_display()
            ),
            "badge_class": {
                Order.Status.PENDING: "text-bg-warning",
                Order.Status.CONFIRMED: "text-bg-success",
                Order.Status.PACKED: "text-bg-info",
                Order.Status.SHIPPED: "text-bg-primary",
                Order.Status.DELIVERED: "text-bg-success",
                Order.Status.CANCELLED: "text-bg-danger",
                Order.Status.RETURNED: "text-bg-warning",
            }.get(entry.status, "text-bg-secondary"),
            "changed_by": _history_user_label(entry),
            "note": entry.note,
            "source": entry.get_source_display(),
            "is_imported": entry.source == OrderStatusHistory.Source.IMPORTED,
            **_timestamp_data(entry),
        }
        for entry in history_entries
    ]
    return {
        "order_number": order.order_id,
        "customer_name": order.full_name,
        "current_status": order.get_status_display(),
        "current_status_badge_class": {
            Order.Status.PENDING: "text-bg-warning",
            Order.Status.CONFIRMED: "text-bg-success",
            Order.Status.PACKED: "text-bg-info",
            Order.Status.SHIPPED: "text-bg-primary",
            Order.Status.DELIVERED: "text-bg-success",
            Order.Status.CANCELLED: "text-bg-danger",
            Order.Status.RETURNED: "text-bg-warning",
        }.get(order.status, "text-bg-secondary"),
        "is_cancelled": is_cancelled,
        "is_returned": is_returned,
        "cancellation_note": cancellation_entry.note if cancellation_entry else "",
        "returned_note": returned_entry.note if returned_entry else "",
        "steps": steps,
        "events": events,
        "detail_url": reverse("dashboard_order_detail", args=[order.order_id]),
        **{
            f"cancellation_{key}": value
            for key, value in _timestamp_data(cancellation_entry).items()
        },
        **{
            f"returned_{key}": value
            for key, value in _timestamp_data(returned_entry).items()
        },
    }
