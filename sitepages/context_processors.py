from django.conf import settings
from django.core.cache import cache

from category.models import Brand, Category

from .cart import get_cart_state
from .cache import (
    ACTIVE_CATEGORIES_CACHE_KEY,
    FOOTER_BRANDS_CACHE_KEY,
    FOOTER_CATEGORIES_CACHE_KEY,
    PUBLIC_CACHE_TIMEOUT,
)


def currency_context(request):
    return {"currency_symbol": settings.CURRENCY_SYMBOL}


def cart_context(request):
    if request.path.startswith("/dashboard/"):
        return {}

    cart_state = get_cart_state(request)
    return {
        "cart_items": cart_state["items"],
        "cart_preview_items": cart_state["preview_items"],
        "cart_item_count": cart_state["item_count"],
        "cart_line_count": cart_state["line_count"],
        "cart_subtotal": cart_state["subtotal"],
        "cart_is_empty": cart_state["is_empty"],
    }


def product_search_context(request):
    if request.path.startswith("/dashboard/"):
        return {}

    current_url_name = getattr(getattr(request, "resolver_match", None), "url_name", "")
    is_products_page = current_url_name == "frontend_products"
    active_categories = cache.get(ACTIVE_CATEGORIES_CACHE_KEY)
    if active_categories is None:
        active_categories = list(Category.objects.filter(is_active=True).order_by("sort_order", "name", "id"))
        cache.set(ACTIVE_CATEGORIES_CACHE_KEY, active_categories, PUBLIC_CACHE_TIMEOUT)
    return {
        "header_search_categories": active_categories,
        "navbar_categories": active_categories[:10],
        "header_search_query": ((request.GET.get("q") or "").strip() if is_products_page else ""),
        "header_search_category": ((request.GET.get("category") or "").strip() if is_products_page else ""),
    }


def footer_brand_context(request):
    if request.path.startswith("/dashboard/"):
        return {}

    footer_brands = cache.get(FOOTER_BRANDS_CACHE_KEY)
    if footer_brands is None:
        footer_brands = list(
            Brand.objects.filter(is_active=True, show_on_homepage=True)
            .only("name", "slug")
            .order_by("name", "id")
        )
        cache.set(FOOTER_BRANDS_CACHE_KEY, footer_brands, PUBLIC_CACHE_TIMEOUT)

    footer_categories = cache.get(FOOTER_CATEGORIES_CACHE_KEY)
    if footer_categories is None:
        footer_categories = list(
            Category.objects.filter(is_active=True, show_on_homepage=True)
            .only("name", "slug")
            .order_by("sort_order", "name", "id")[:5]
        )
        cache.set(FOOTER_CATEGORIES_CACHE_KEY, footer_categories, PUBLIC_CACHE_TIMEOUT)

    return {
        "footer_brands": footer_brands,
        "footer_categories": footer_categories,
    }
    

def dashboard_profile_context(request):

    from sitepages.models import UserProfile

    profile = None

    if request.path.startswith("/dashboard/") and request.user.is_authenticated:
        profile = UserProfile.objects.filter(user=request.user).first()

    return {
        'dashboard_profile': profile
    }
