"""Queue browser-deduplicated Meta events without delaying customer requests."""

import hashlib
import json
import uuid

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from .meta import (
    customer_data_from_order,
    customer_data_from_request,
    is_browser_tracking_enabled,
    is_capi_tracking_enabled,
    request_attribution,
)
from .models import MetaEvent, MetaOrderAttribution


CHECKOUT_EVENT_SESSION_KEY = "meta_initiate_checkout"


def new_event_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def safe_event_id(value, prefix):
    value = str(value or "").strip()
    if 8 <= len(value) <= 128 and all(character.isalnum() or character in "_-" for character in value):
        return value
    return new_event_id(prefix)


def queue_event(*, event_id, event_name, custom_data, user_data, event_source_url, order=None):
    if not is_capi_tracking_enabled():
        return None
    try:
        event, _created = MetaEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "event_name": event_name,
                "event_time": timezone.now(),
                "event_source_url": event_source_url,
                "custom_data": custom_data,
                "user_data": user_data,
                "order": order,
            },
        )
    except IntegrityError:
        event = MetaEvent.objects.get(event_id=event_id)
    return event


def browser_event(event_name, event_id, custom_data):
    if not is_browser_tracking_enabled():
        return None
    return {"event_name": event_name, "event_id": event_id, "custom_data": custom_data}


def product_custom_data(product, quantity=1):
    quantity = int(quantity)
    return {
        "content_ids": [product.sku],
        "contents": [{"id": product.sku, "quantity": quantity, "item_price": float(product.current_price)}],
        "content_type": "product",
        "content_name": product.name,
        "value": float(product.current_price * quantity),
        "currency": "BDT",
    }


def queue_view_content(request, product):
    event_id = new_event_id("view_content")
    custom_data = product_custom_data(product)
    attribution = request_attribution(request)
    queue_event(
        event_id=event_id,
        event_name="ViewContent",
        custom_data=custom_data,
        user_data=customer_data_from_request(request),
        event_source_url=attribution["event_source_url"],
    )
    return browser_event("ViewContent", event_id, custom_data)


def queue_add_to_cart(request, product, quantity, event_id):
    event_id = safe_event_id(event_id, "add_to_cart")
    custom_data = product_custom_data(product, quantity)
    attribution = request_attribution(request)
    queue_event(
        event_id=event_id,
        event_name="AddToCart",
        custom_data=custom_data,
        user_data=customer_data_from_request(request),
        event_source_url=attribution["event_source_url"],
    )
    return browser_event("AddToCart", event_id, custom_data)


def checkout_custom_data(cart_state, shipping_amount):
    contents = [
        {
            "id": item["sku"],
            "quantity": int(item["quantity"]),
            "item_price": float(item["current_price"]),
        }
        for item in cart_state["items"]
    ]
    return {
        "content_ids": [item["sku"] for item in cart_state["items"]],
        "contents": contents,
        "content_type": "product",
        "currency": "BDT",
        "value": float(cart_state["subtotal"] + shipping_amount),
        "num_items": cart_state["item_count"],
    }


def checkout_signature(cart_state, shipping_amount):
    signature_data = {
        "items": [
            (item["sku"], int(item["quantity"]), str(item["current_price"]))
            for item in cart_state["items"]
        ],
        "shipping": str(shipping_amount),
    }
    return hashlib.sha256(json.dumps(signature_data, separators=(",", ":")).encode("utf-8")).hexdigest()


def queue_initiate_checkout(request, cart_state, shipping_amount):
    if cart_state["is_empty"] or not is_browser_tracking_enabled():
        return None
    signature = checkout_signature(cart_state, shipping_amount)
    saved = request.session.get(CHECKOUT_EVENT_SESSION_KEY, {})
    event_id = saved.get("event_id") if saved.get("signature") == signature else new_event_id("initiate_checkout")
    request.session[CHECKOUT_EVENT_SESSION_KEY] = {"signature": signature, "event_id": event_id}
    request.session.modified = True
    custom_data = checkout_custom_data(cart_state, shipping_amount)
    attribution = request_attribution(request)
    queue_event(
        event_id=event_id,
        event_name="InitiateCheckout",
        custom_data=custom_data,
        user_data=customer_data_from_request(request),
        event_source_url=attribution["event_source_url"],
    )
    return browser_event("InitiateCheckout", event_id, custom_data)


def capture_order_attribution(request, order):
    if not settings.META_TRACKING_ENABLED:
        return None
    attribution = request_attribution(request)
    return MetaOrderAttribution.objects.update_or_create(
        order=order,
        defaults={
            "fbp": attribution["fbp"],
            "fbc": attribution["fbc"],
            "client_ip": attribution["client_ip"] or None,
            "client_user_agent": attribution["client_user_agent"],
            "event_source_url": attribution["event_source_url"],
        },
    )[0]


def queue_purchase(order):
    if not is_capi_tracking_enabled():
        return None
    items = list(order.items.all())
    custom_data = {
        "content_ids": [item.product_sku for item in items],
        "contents": [
            {"id": item.product_sku, "quantity": item.quantity, "item_price": float(item.unit_price)}
            for item in items
        ],
        "content_type": "product",
        "currency": "BDT",
        "value": float(order.total_amount),
        "order_id": order.order_id,
    }
    attribution = getattr(order, "meta_attribution", None)
    return queue_event(
        event_id=f"purchase_{order.order_id}",
        event_name="Purchase",
        custom_data=custom_data,
        user_data=customer_data_from_order(order),
        event_source_url=attribution.event_source_url if attribution else "",
        order=order,
    )
