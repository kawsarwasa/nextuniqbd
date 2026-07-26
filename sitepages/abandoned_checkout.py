from collections.abc import Mapping
import re

from django.db import transaction

from .cart import get_cart_state, get_delivery_zone_details
from .models import AbandonedCheckout


BD_PHONE_PATTERN = re.compile(r"^01[3-9]\d{8}$")


def normalize_bd_phone(value):
    """Normalize a Bangladesh mobile number to the local 01XXXXXXXXX format."""
    phone_number = re.sub(r"[\s\-()]", "", str(value or "").strip())
    if phone_number.startswith("+880"):
        phone_number = f"0{phone_number[4:]}"
    elif phone_number.startswith("880"):
        phone_number = f"0{phone_number[3:]}"
    return phone_number


FORM_FIELD_ALIASES = {
    "full_name": ("full_name",),
    "phone_number": ("phone_number", "phone"),
    "email": ("email",),
    "address": ("address",),
    "district": ("district",),
    "area_thana": ("area_thana", "thana"),
    "postal_code": ("postal_code", "postal"),
}


def build_cart_snapshot(cart_state):
    """Return a JSON-safe snapshot of the cart at checkout time."""
    return [
        {
            "product_id": item["product_id"],
            "name": item["name"],
            "slug": item["slug"],
            "sku": item["sku"],
            "category_name": item["category_name"],
            "brand_name": item["brand_name"],
            "image_url": item["image_url"],
            "detail_url": item["detail_url"],
            "quantity": item["quantity"],
            "unit_price": str(item["current_price"]),
            "line_total": str(item["subtotal"]),
        }
        for item in cart_state["items"]
    ]


def _get_form_value(form_data, aliases):
    if not isinstance(form_data, Mapping):
        return None, False

    for field_name in aliases:
        if field_name in form_data:
            value = form_data.get(field_name)
            return str(value).strip() if value is not None else "", True
    return None, False


def _get_user_defaults(user):
    profile = getattr(user, "dashboard_profile", None)
    full_name = user.get_full_name().strip()
    if not full_name:
        full_name = (user.email or user.get_username() or "").strip()
    phone_number = (profile.phone or "").strip() if profile else ""
    address = (profile.address or "").strip() if profile else ""

    return {
        "full_name": full_name or None,
        "phone_number": phone_number or None,
        "email": (user.email or "").strip().lower() or None,
        "address": address or None,
        "district": None,
        "area_thana": None,
        "postal_code": None,
    }


def _build_customer_data(request, form_data):
    is_authenticated = getattr(request.user, "is_authenticated", False)
    customer_data = _get_user_defaults(request.user) if is_authenticated else {
        field_name: None for field_name in FORM_FIELD_ALIASES
    }

    for field_name, aliases in FORM_FIELD_ALIASES.items():
        value, supplied = _get_form_value(form_data, aliases)
        if supplied:
            customer_data[field_name] = value or None

    if customer_data["email"]:
        customer_data["email"] = customer_data["email"].lower()
    return customer_data


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


@transaction.atomic
def create_or_update_abandoned_checkout(request, form_data=None):
    """
    Create or refresh the latest pending checkout for the current customer.

    Returns the AbandonedCheckout instance, or None when the cart is empty or
    an anonymous customer has not supplied a phone number.
    """
    cart_state = get_cart_state(request)
    if cart_state["is_empty"]:
        return None

    is_authenticated = getattr(request.user, "is_authenticated", False)
    customer_data = _build_customer_data(request, form_data)
    if not is_authenticated:
        phone_number = normalize_bd_phone(customer_data["phone_number"])
        if not BD_PHONE_PATTERN.fullmatch(phone_number):
            return None
        customer_data["phone_number"] = phone_number

    identity_filter = {}
    if is_authenticated:
        identity_filter["user"] = request.user
        session_key = request.session.session_key
    else:
        session_key = _ensure_session_key(request)
        identity_filter["session_key"] = session_key

    delivery_zone = get_delivery_zone_details(request.session)
    subtotal = cart_state["subtotal"]
    shipping_charge = delivery_zone["amount"]
    checkout_data = {
        **customer_data,
        "user": request.user if is_authenticated else None,
        "session_key": session_key,
        "delivery_area": delivery_zone["key"],
        "cart_items": build_cart_snapshot(cart_state),
        "subtotal": subtotal,
        "shipping_charge": shipping_charge,
        "total_amount": subtotal + shipping_charge,
        "source": "checkout_page",
    }

    abandoned_checkout = (
        AbandonedCheckout.objects.select_for_update()
        .filter(status=AbandonedCheckout.Status.PENDING, **identity_filter)
        .order_by("-updated_at", "-id")
        .first()
    )
    if abandoned_checkout is None:
        return AbandonedCheckout.objects.create(**checkout_data)

    for field_name, value in checkout_data.items():
        setattr(abandoned_checkout, field_name, value)
    abandoned_checkout.save(update_fields=[*checkout_data.keys(), "updated_at"])
    return abandoned_checkout


def mark_pending_abandoned_checkout_converted(request):
    """Convert the latest pending checkout for the current user or session."""
    identity_filter = {}
    if getattr(request.user, "is_authenticated", False):
        identity_filter["user"] = request.user
    elif request.session.session_key:
        identity_filter["session_key"] = request.session.session_key
    else:
        return None

    abandoned_checkout = (
        AbandonedCheckout.objects.select_for_update()
        .filter(status=AbandonedCheckout.Status.PENDING, **identity_filter)
        .order_by("-updated_at", "-id")
        .first()
    )
    if abandoned_checkout is None:
        return None

    abandoned_checkout.status = AbandonedCheckout.Status.CONVERTED
    abandoned_checkout.save(update_fields=["status", "updated_at"])
    return abandoned_checkout
