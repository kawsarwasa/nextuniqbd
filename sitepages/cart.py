from decimal import Decimal

from django.urls import reverse

from django.db.models import Prefetch

from category.models import Product, ProductImage


CART_SESSION_KEY = "storefront_cart"
DELIVERY_ZONE_SESSION_KEY = "storefront_delivery_zone"
MAX_CART_QTY = 10
DELIVERY_ZONES = {
    "inside_dhaka": {"label": "Inside Dhaka", "amount": Decimal("60.00"), "estimate": "1-2 business days"},
    "outside_dhaka": {"label": "Outside Dhaka", "amount": Decimal("130.00"), "estimate": "3-5 business days"},
}
DEFAULT_DELIVERY_ZONE = "inside_dhaka"


def _get_session_cart(session):
    cart = session.get(CART_SESSION_KEY, {})
    if not isinstance(cart, dict):
        return {}
    return {str(key): int(value) for key, value in cart.items() if str(value).isdigit() or isinstance(value, int)}


def _save_session_cart(session, cart):
    session[CART_SESSION_KEY] = cart
    session.modified = True


def normalize_quantity(quantity, minimum=1, maximum=MAX_CART_QTY):
    try:
        normalized = int(quantity)
    except (TypeError, ValueError):
        normalized = minimum
    return max(minimum, min(maximum, normalized))


def add_to_cart_session(request, product_id, quantity=1):
    cart = _get_session_cart(request.session)
    key = str(product_id)
    existing_quantity = int(cart.get(key, 0))
    cart[key] = normalize_quantity(existing_quantity + int(quantity or 0))
    _save_session_cart(request.session, cart)
    _invalidate_cart_state(request)
    return cart


def update_cart_session(request, product_id, quantity):
    cart = _get_session_cart(request.session)
    key = str(product_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = normalize_quantity(quantity)
    _save_session_cart(request.session, cart)
    _invalidate_cart_state(request)
    return cart


def remove_from_cart_session(request, product_id):
    cart = _get_session_cart(request.session)
    cart.pop(str(product_id), None)
    _save_session_cart(request.session, cart)
    _invalidate_cart_state(request)
    return cart


def clear_cart_session(request):
    _save_session_cart(request.session, {})
    _invalidate_cart_state(request)


def get_delivery_zone(session):
    zone = session.get(DELIVERY_ZONE_SESSION_KEY, DEFAULT_DELIVERY_ZONE)
    if zone not in DELIVERY_ZONES:
        zone = DEFAULT_DELIVERY_ZONE
    return zone


def set_delivery_zone(session, zone):
    normalized_zone = zone if zone in DELIVERY_ZONES else DEFAULT_DELIVERY_ZONE
    session[DELIVERY_ZONE_SESSION_KEY] = normalized_zone
    session.modified = True
    return normalized_zone


def get_delivery_zone_details(session):
    zone = get_delivery_zone(session)
    return {
        "key": zone,
        **DELIVERY_ZONES[zone],
    }


def get_cart_state(request):
    cached_state = getattr(request, "_revo_cart_state", None)
    if cached_state is not None:
        return cached_state

    cart = _get_session_cart(request.session)
    if not cart:
        request._revo_cart_state = {
            "items": [],
            "preview_items": [],
            "product_ids": [],
            "item_count": 0,
            "line_count": 0,
            "subtotal": Decimal("0.00"),
            "is_empty": True,
        }
        return request._revo_cart_state

    product_ids = [int(product_id) for product_id in cart.keys() if str(product_id).isdigit()]
    products = (
        Product.objects.select_related("category", "brand")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.only("id", "product_id", "image", "sort_order").order_by("sort_order", "id")[:1],
                to_attr="card_images",
            )
        )
        .filter(pk__in=product_ids, status=Product.Status.PUBLISHED)
    )
    products_by_id = {product.pk: product for product in products}

    items = []
    subtotal = Decimal("0.00")
    stale_keys = []

    for product_id_str, quantity in cart.items():
        product = products_by_id.get(int(product_id_str))
        if product is None:
            stale_keys.append(product_id_str)
            continue

        image = product.primary_image
        unit_price = product.current_price
        line_subtotal = unit_price * quantity
        subtotal += line_subtotal

        items.append(
            {
                "product_id": product.pk,
                "quantity": quantity,
                "name": product.name,
                "slug": product.slug,
                "sku": product.sku,
                "category_name": product.category.name,
                "brand_name": product.brand.name if product.brand else "",
                "image_url": image.card_url if image and image.image else "",
                "detail_url": reverse("frontend_product_detail", args=[product.slug]),
                "current_price": unit_price,
                "regular_price": product.regular_price,
                "is_on_sale": unit_price < product.regular_price,
                "subtotal": line_subtotal,
            }
        )

    if stale_keys:
        for key in stale_keys:
            cart.pop(key, None)
        _save_session_cart(request.session, cart)

    item_count = sum(item["quantity"] for item in items)

    request._revo_cart_state = {
        "items": items,
        "preview_items": items[:3],
        "product_ids": [item["product_id"] for item in items],
        "item_count": item_count,
        "line_count": len(items),
        "subtotal": subtotal,
        "is_empty": not items,
    }
    return request._revo_cart_state


def _invalidate_cart_state(request):
    request.__dict__.pop("_revo_cart_state", None)


def serialize_cart_state(cart_state):
    def serialize_item(item):
        return {
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "name": item["name"],
            "slug": item["slug"],
            "sku": item["sku"],
            "category_name": item["category_name"],
            "brand_name": item["brand_name"],
            "image_url": item["image_url"],
            "detail_url": item["detail_url"],
            "current_price": f"{item['current_price']:.2f}",
            "regular_price": f"{item['regular_price']:.2f}",
            "is_on_sale": item["is_on_sale"],
            "subtotal": f"{item['subtotal']:.2f}",
        }

    return {
        "items": [serialize_item(item) for item in cart_state["items"]],
        "preview_items": [serialize_item(item) for item in cart_state["preview_items"]],
        "product_ids": cart_state["product_ids"],
        "item_count": cart_state["item_count"],
        "line_count": cart_state["line_count"],
        "subtotal": f"{cart_state['subtotal']:.2f}",
        "is_empty": cart_state["is_empty"],
    }
