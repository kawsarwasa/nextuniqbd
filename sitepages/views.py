import re
import json
import logging
from datetime import timedelta
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import TruncMonth
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.html import conditional_escape, format_html, strip_tags
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from category.models import Brand, Category, Product, ProductImage, ProductReview
from .dashboard_pagination import DEFAULT_DASHBOARD_PAGE_SIZE, build_dashboard_pagination_context
from .abandoned_checkout import (
    create_or_update_abandoned_checkout,
    mark_pending_abandoned_checkout_converted,
)
from .forms import (
    CheckoutOrderForm,
    ContactMessageForm,
    DashboardPasswordForm,
    DashboardProfileForm,
    UsernameAuthenticationForm,
    HeroSlideForm,
    OrderStatusForm,
    RegistrationForm,
    RoleForm,
)
from .permissions import (
    DashboardAccessMixin,
    DashboardPermissionMixin,
    get_managed_permission_ids,
    get_permission_ids_for_cells,
    get_role_profile,
    get_role_permission_rows,
    get_user_permission_rows,
    user_can_access_dashboard,
)
from .models import (
    HeroSlide,
    ContactMessage,
    Order,
    OrderItem,
    Sale,
    SaleItem,
    UserProfile,
)
from .cart import (
    add_to_cart_session,
    clear_cart_session,
    DELIVERY_ZONES,
    get_cart_state,
    get_delivery_zone_details,
    normalize_quantity,
    remove_from_cart_session,
    serialize_cart_state,
    set_delivery_zone,
    update_cart_session,
)
from .order_stock import validate_checkout_stock
from .order_status import change_order_status
from .order_tracking import build_order_tracking_context
from .cache import (
    HERO_SLIDES_CACHE_KEY,
    HOMEPAGE_BRANDS_CACHE_KEY,
    HOMEPAGE_CATEGORIES_CACHE_KEY,
    HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY,
    get_public_cache_value,
)

FRONTEND_TEMPLATE_RE = re.compile(r"^[a-zA-Z0-9_]+\.html$")
logger = logging.getLogger(__name__)
User = get_user_model()
ORDER_STATUS_BADGE_CLASSES = {
    Order.Status.PENDING: "text-bg-warning",
    Order.Status.CONFIRMED: "text-bg-success",
    Order.Status.PACKED: "text-bg-info",
    Order.Status.SHIPPED: "text-bg-primary",
    Order.Status.DELIVERED: "text-bg-success",
    Order.Status.CANCELLED: "text-bg-danger",
    Order.Status.RETURNED: "text-bg-warning",
}


def build_review_context(product):
    reviews = list(product.reviews.all())
    review_count = len(reviews)
    average_rating = round(sum(review.rating for review in reviews) / review_count, 1) if review_count else 0

    for review in reviews:
        review.full_stars = range(review.rating)
        review.empty_stars_range = range(max(5 - review.rating, 0))

    breakdown = []
    for rating in range(5, 0, -1):
        rating_total = sum(1 for review in reviews if review.rating == rating)
        percentage = round((rating_total / review_count) * 100) if review_count else 0
        breakdown.append(
            {
                "rating": rating,
                "count": rating_total,
                "percentage": percentage,
            }
        )

    return {
        "reviews": reviews,
        "review_summary": {
            "count": review_count,
            "average": average_rating,
            "breakdown": breakdown,
        },
    }


def build_review_form_context(form_data=None, errors=None, submitted=False):
    form_data = form_data or {}
    errors = errors or {}
    return {
        "review_form_data": {
            "reviewer_name": form_data.get("reviewer_name", ""),
            "reviewer_email": form_data.get("reviewer_email", ""),
            "title": form_data.get("title", ""),
            "body": form_data.get("body", ""),
            "rating": form_data.get("rating", ""),
        },
        "review_form_errors": errors,
        "review_submitted": submitted,
        "review_form_open": submitted or bool(errors),
    }


def get_published_products_queryset(*, include_detail_relations=False):
    queryset = Product.objects.select_related("brand", "category").filter(status=Product.Status.PUBLISHED)

    if include_detail_relations:
        return queryset.prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.only("id", "product_id", "image", "sort_order").order_by("sort_order", "id"),
            ),
            "reviews",
        )

    return queryset.annotate(
        _review_count=Count("reviews"),
        _average_rating=Avg("reviews__rating"),
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.only("id", "product_id", "image", "sort_order").order_by("sort_order", "id")[:1],
            to_attr="card_images",
        )
    )


def with_confirmed_sales_total(queryset):
    """Add an accurate, join-safe total of quantities in final confirmed sales."""
    confirmed_sale_items = (
        SaleItem.objects.filter(
            product_id=OuterRef("pk"),
            sale__order__status=Order.Status.CONFIRMED,
        )
        .order_by()
        .values("product_id")
        .annotate(total_sold=Sum("quantity"))
        .values("total_sold")[:1]
    )
    return queryset.annotate(
        total_sold=Subquery(confirmed_sale_items, output_field=IntegerField())
    )


def get_active_hero_slides():
    def build_slides():
        slides = list(HeroSlide.objects.filter(is_active=True).order_by("sort_order", "id"))
        for slide in slides:
            slide.content_inline_style = ""
            if slide.content_alignment == HeroSlide.ContentAlignment.RIGHT:
                slide.content_css_class = "hero-content hero-right"
            elif slide.content_alignment == HeroSlide.ContentAlignment.CENTER:
                slide.content_css_class = "hero-content"
                slide.content_inline_style = "margin-left:auto;margin-right:auto;text-align:center;"
            else:
                slide.content_css_class = "hero-content"
            slide.title_html = build_hero_slide_title_html(slide.title, slide.title_highlight)
        return slides

    return get_public_cache_value(HERO_SLIDES_CACHE_KEY, build_slides)


def get_homepage_categories():
    def build_categories():
        categories = list(
            Category.objects.filter(is_active=True, show_on_homepage=True)
            .annotate(published_product_count=Count("products", filter=Q(products__status=Product.Status.PUBLISHED)))
            .order_by("sort_order", "name", "id")[:5]
        )
        for category in categories:
            category.home_url = f"/products/?category={category.slug}"
        return categories

    return get_public_cache_value(HOMEPAGE_CATEGORIES_CACHE_KEY, build_categories)


def get_homepage_brands():
    def build_brands():
        brands = list(
            Brand.objects.filter(is_active=True, show_on_homepage=True)
            .annotate(published_product_count=Count("products", filter=Q(products__status=Product.Status.PUBLISHED)))
            .order_by("name", "id")
        )
        for brand in brands:
            brand.home_url = f"/products/?brand={brand.slug}"
        return brands

    return get_public_cache_value(HOMEPAGE_BRANDS_CACHE_KEY, build_brands)


def get_homepage_latest_products():
    def build_products():
        products = list(
            get_published_products_queryset()
            .filter(category__is_active=True)
            .order_by("-created_at", "-id")[:20]
        )
        return decorate_products(products)

    return get_public_cache_value(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY, build_products)


def build_hero_slide_title_html(title, highlight):
    escaped_title = conditional_escape(title or "")
    escaped_highlight = conditional_escape(highlight or "")

    if not escaped_highlight:
        return escaped_title

    raw_title = title or ""
    raw_highlight = highlight or ""
    index = raw_title.lower().find(raw_highlight.lower())

    if index >= 0:
        before = conditional_escape(raw_title[:index])
        matched = conditional_escape(raw_title[index : index + len(raw_highlight)])
        after = conditional_escape(raw_title[index + len(raw_highlight) :])
        return format_html("{}<span>{}</span>{}", before, matched, after)

    return format_html("{}<br><span>{}</span>", escaped_title, escaped_highlight)


def decorate_product(product, now=None):
    if product is None:
        return None

    now = now or timezone.now()
    prefetched_images = getattr(product, "_prefetched_objects_cache", {}).get("images")
    card_images = getattr(product, "card_images", None)
    image_count = (
        len(prefetched_images)
        if prefetched_images is not None
        else (len(card_images) if card_images is not None else None)
    )
    primary_image = product.primary_image

    product.category_label = product.category.name
    product.brand_label = product.brand.name if product.brand else ""
    product.primary_image_url = primary_image.image.url if primary_image and primary_image.image else ""
    product.primary_image_card_url = primary_image.card_url if primary_image else ""
    product.primary_image_detail_url = primary_image.detail_url if primary_image else ""
    product.display_rating = product.average_rating
    rounded_rating = max(0, min(5, round(product.display_rating)))
    product.full_stars = range(rounded_rating)
    product.empty_stars = range(max(5 - rounded_rating, 0))
    product.is_on_sale = product.current_price < product.regular_price
    if product.track_stock:
        product.is_in_stock = product.stock_quantity > 0
        product.stock_display = (
            "Out of Stock"
            if not product.is_in_stock
            else f"Only {product.stock_quantity} left"
            if product.is_low_stock
            else "In Stock"
        )
    else:
        product.is_in_stock = "out" not in (product.availability or "").strip().lower()
        product.stock_display = product.availability or "Not specified"
    product.is_new_arrival = now - product.created_at <= timedelta(days=30)
    product.short_description_plain = " ".join(strip_tags(product.short_description or "").split())
    product.full_description_html = product.full_description or (
        f"<p>{product.short_description_plain or 'No product description available yet.'}</p>"
    )
    product.image_count = image_count

    if product.is_on_sale and product.regular_price:
        product.sale_percentage = round(((product.regular_price - product.current_price) / product.regular_price) * 100)
        product.sale_amount = product.regular_price - product.current_price
    else:
        product.sale_percentage = 0
        product.sale_amount = 0

    product.specification_rows = [
        {"label": "SKU", "value": product.sku},
        {"label": "Category", "value": product.category_label},
        {"label": "Brand", "value": product.brand_label or "Unbranded"},
        {"label": "Availability", "value": product.availability or "Not specified"},
        {"label": "Status", "value": product.get_status_display()},
        {"label": "Gallery Images", "value": str(product.image_count or 0)},
    ]
    return product


def decorate_products(products, now=None):
    now = now or timezone.now()
    for index, product in enumerate(products, start=1):
        decorate_product(product, now=now)
        product.sort_order = index
        product.created_timestamp = int(product.created_at.timestamp())
    return products


def build_products_listing_context(request=None):
    search_query = ((request.GET.get("q") if request else "") or "").strip()
    selected_category_slug = ((request.GET.get("category") if request else "") or "").strip()
    selected_brand_slug = ((request.GET.get("brand") if request else "") or "").strip()
    selected_product_tab = ((request.GET.get("tab") if request else "") or "").strip().lower()

    queryset = get_published_products_queryset().order_by("-id")

    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query)
            | Q(short_description__icontains=search_query)
            | Q(full_description__icontains=search_query)
            | Q(category__name__icontains=search_query)
            | Q(brand__name__icontains=search_query)
            | Q(sku__icontains=search_query)
        )

    if selected_category_slug:
        queryset = queryset.filter(category__slug=selected_category_slug)

    if selected_brand_slug:
        queryset = queryset.filter(brand__slug=selected_brand_slug)

    tab_labels = {
        "deals": "Today's Deals",
        "bestsellers": "Best Sellers",
        "new": "New Arrivals",
        "featured": "Featured Products",
    }
    now = timezone.now()
    if selected_product_tab == "deals":
        queryset = queryset.filter(current_price__lt=F("regular_price")).annotate(
            discount_percent=ExpressionWrapper(
                (F("regular_price") - F("current_price")) * 100 / F("regular_price"),
                output_field=DecimalField(max_digits=7, decimal_places=2),
            )
        ).order_by("-discount_percent", "-created_at", "-id")
    elif selected_product_tab == "bestsellers":
        queryset = with_confirmed_sales_total(queryset).filter(total_sold__gt=0).order_by(
            "-total_sold", "-_average_rating", "-created_at", "-id"
        )
    elif selected_product_tab == "new":
        queryset = queryset.filter(created_at__gte=now - timedelta(days=30)).order_by("-created_at", "-id")
    elif selected_product_tab == "featured":
        queryset = queryset.filter(is_featured=True).order_by("-created_at", "-id")
    else:
        selected_product_tab = ""

    products = list(queryset)
    decorate_products(products)

    category_counts = {}
    brand_counts = {}
    availability_counts = {
        "in_stock": 0,
        "on_sale": 0,
        "new_arrival": 0,
    }
    highest_price = 0
    for product in products:
        category_counts[product.category_label] = category_counts.get(product.category_label, 0) + 1
        if product.brand_label:
            brand_counts[product.brand_label] = brand_counts.get(product.brand_label, 0) + 1
        if product.is_in_stock:
            availability_counts["in_stock"] += 1
        if product.is_on_sale:
            availability_counts["on_sale"] += 1
        if product.is_new_arrival:
            availability_counts["new_arrival"] += 1

        highest_price = max(highest_price, float(product.current_price))

    price_max = max(500, int(ceil(highest_price / 50.0) * 50)) if products else 500

    return {
        "products": products,
        "product_count": len(products),
        "category_filters": [
            {
                "name": name,
                "count": count,
                "checked": bool(selected_category_slug and category_slug == selected_category_slug),
            }
            for name, count, category_slug in sorted(
                [
                    (name, count, next((product.category.slug for product in products if product.category_label == name), ""))
                    for name, count in category_counts.items()
                ],
                key=lambda item: item[0].lower(),
            )
        ],
        "brand_filters": [
            {
                "name": name,
                "count": count,
                "checked": bool(selected_brand_slug and brand_slug == selected_brand_slug),
            }
            for name, count, brand_slug in sorted(
                [
                    (name, count, next((product.brand.slug for product in products if product.brand_label == name and product.brand), ""))
                    for name, count in brand_counts.items()
                ],
                key=lambda item: item[0].lower(),
            )
        ],
        "availability_filters": [
            {"value": "in_stock", "label": "In Stock", "count": availability_counts["in_stock"], "checked": True},
            {"value": "on_sale", "label": "On Sale", "count": availability_counts["on_sale"], "checked": False},
            {
                "value": "new_arrival",
                "label": "New Arrivals",
                "count": availability_counts["new_arrival"],
                "checked": False,
            },
        ],
        "price_max": price_max,
        "selected_search_query": search_query,
        "selected_search_category": selected_category_slug,
        "selected_search_brand": selected_brand_slug,
        "selected_product_tab": selected_product_tab,
        "selected_product_tab_label": tab_labels.get(selected_product_tab, ""),
    }


def build_product_detail_context(product):
    decorate_product(product)

    related_products = list(
        get_published_products_queryset().filter(category=product.category).exclude(pk=product.pk).order_by("-id")[:5]
    )
    if len(related_products) < 5:
        related_ids = [item.pk for item in related_products]
        related_products.extend(
            list(
                get_published_products_queryset()
                .exclude(pk__in=[product.pk, *related_ids])
                .order_by("-id")[: 5 - len(related_products)]
            )
        )

    recently_viewed_products = list(
        get_published_products_queryset().exclude(pk=product.pk).order_by("-updated_at", "-id")[:4]
    )

    decorate_products(related_products)
    decorate_products(recently_viewed_products)

    return {
        "product": product,
        "related_products": related_products,
        "recently_viewed_products": recently_viewed_products,
        **build_review_context(product),
    }


def build_cart_page_context(request):
    cart_state = get_cart_state(request)
    delivery_zone = get_delivery_zone_details(request.session)
    recommended_products = list(
        get_published_products_queryset()
        .exclude(pk__in=cart_state["product_ids"])
        .order_by("-id")[:4]
    )
    decorate_products(recommended_products)

    return {
        "cart_state": cart_state,
        "delivery_zone": delivery_zone,
        "recommended_products": recommended_products,
        "cart_modal_product": recommended_products[0] if recommended_products else None,
    }


def build_checkout_initial_data(request):
    profile = get_dashboard_profile(request.user) if getattr(request.user, "is_authenticated", False) else None
    return {
        "full_name": get_user_display_name(request.user) if getattr(request.user, "is_authenticated", False) else "",
        "phone": profile.phone if profile is not None else "",
        "email": request.user.email if getattr(request.user, "is_authenticated", False) else "",
        "address": profile.address if profile is not None else "",
        "district": "",
        "thana": "",
        "postal": "",
        "order_notes": "",
    }


def build_checkout_page_context(request, checkout_form=None):
    cart_state = get_cart_state(request)
    delivery_zone = get_delivery_zone_details(request.session)
    checkout_form = checkout_form or CheckoutOrderForm(initial=build_checkout_initial_data(request))
    return {
        "cart_state": cart_state,
        "checkout_delivery_zone": delivery_zone,
        "checkout_initial_shipping": delivery_zone["amount"] if not cart_state["is_empty"] else 0,
        "checkout_form": checkout_form,
    }


@transaction.atomic
def create_order_from_checkout(request, checkout_form, cart_state):
    delivery_zone = get_delivery_zone_details(request.session)
    cleaned_data = checkout_form.cleaned_data
    validate_checkout_stock(cart_state)

    order = Order(
        user=request.user if getattr(request.user, "is_authenticated", False) else None,
        full_name=cleaned_data["full_name"],
        phone=cleaned_data["phone"],
        email=cleaned_data["email"],
        address=cleaned_data["address"],
        district=cleaned_data["district"],
        thana=cleaned_data["thana"],
        postal_code=cleaned_data["postal"],
        order_notes=cleaned_data["order_notes"],
        payment_method="Cash on Delivery",
        delivery_zone=delivery_zone["key"],
        delivery_label=delivery_zone["label"],
        delivery_estimate=delivery_zone["estimate"],
        shipping_amount=delivery_zone["amount"],
        subtotal_amount=cart_state["subtotal"],
        total_amount=cart_state["subtotal"] + delivery_zone["amount"],
        item_count=cart_state["item_count"],
    )
    order._initial_status_history_source = "checkout"
    order.save()

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product_id=item["product_id"],
                product_name=item["name"],
                product_slug=item["slug"],
                product_sku=item["sku"],
                category_name=item["category_name"],
                brand_name=item["brand_name"],
                quantity=item["quantity"],
                unit_price=item["current_price"],
                subtotal=item["subtotal"],
            )
            for item in cart_state["items"]
        ]
    )
    mark_pending_abandoned_checkout_converted(request)
    return order


def get_user_display_name(user):
    full_name = user.get_full_name().strip()
    return full_name or user.email or user.username


def get_dashboard_profile(user):
    if not getattr(user, "is_authenticated", False):
        return None
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def get_safe_redirect_url(request, fallback_url):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host(), *settings.ALLOWED_HOSTS},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def build_dashboard_user_context(target_user, selected_role):
    from .permissions import ensure_default_roles

    ensure_default_roles()
    roles = list(Group.objects.select_related("role_profile").order_by("name"))
    managed_permission_ids = get_managed_permission_ids()
    direct_permission_ids = set(
        target_user.user_permissions.filter(id__in=managed_permission_ids).values_list("id", flat=True)
    )

    for role in roles:
        role.profile = get_role_profile(role)

    return {
        "managed_user": target_user,
        "managed_user_display_name": get_user_display_name(target_user),
        "available_roles": roles,
        "selected_role": selected_role,
        "selected_role_profile": get_role_profile(selected_role),
        "user_permission_rows": get_user_permission_rows(target_user, selected_role),
        "direct_permission_count": len(direct_permission_ids),
    }


def build_dashboard_role_list_context(form, edit_role=None, *, request=None, page_number=None):
    from .permissions import ensure_default_roles

    ensure_default_roles()
    roles_queryset = Group.objects.select_related("role_profile").order_by("name")
    paginator = Paginator(roles_queryset, DEFAULT_DASHBOARD_PAGE_SIZE)
    page_obj = paginator.get_page(page_number)
    roles = list(page_obj.object_list)
    for role in roles:
        role.profile = get_role_profile(role)

    active_role_total = RoleProfile.objects.filter(is_active=True).count()
    context = {
        "form": form,
        "roles": roles,
        "editing_role": edit_role,
        "role_total": paginator.count,
        "role_active_total": active_role_total,
        "role_inactive_total": paginator.count - active_role_total,
        "page_obj": page_obj,
    }
    if request is not None:
        context.update(build_dashboard_pagination_context(request, page_obj))
    return context


def build_dashboard_role_permission_context(role):
    role.profile = get_role_profile(role)
    return {
        "managed_role": role,
        "managed_role_profile": role.profile,
        "role_permission_rows": get_role_permission_rows(role),
        "permission_snapshot_at": timezone.localtime().strftime("%a, %b %d, %Y %H:%M"),
    }


def get_month_start(date_value):
    return date_value.replace(day=1)


def add_months(date_value, offset):
    month_index = date_value.month - 1 + offset
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    return date_value.replace(year=year, month=month, day=1)


def normalize_truncated_month(value):
    if hasattr(value, "date"):
        value = value.date()
    return get_month_start(value)


def build_monthly_total_map(queryset, date_field, amount_field, first_month):
    rows = (
        queryset.filter(**{f"{date_field}__date__gte": first_month})
        .annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(total=Sum(amount_field))
        .order_by("month")
    )
    return {
        normalize_truncated_month(row["month"]): float(row["total"] or 0)
        for row in rows
        if row["month"] is not None
    }


def build_dashboard_home_context(user):
    order_queryset = Order.objects.all()
    sale_queryset = Sale.objects.all()
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        order_queryset = order_queryset.filter(user=user)
        sale_queryset = sale_queryset.filter(user=user)

    current_month = get_month_start(timezone.localdate())
    first_month = add_months(current_month, -6)
    month_starts = [add_months(first_month, index) for index in range(7)]
    order_totals = build_monthly_total_map(order_queryset, "order_date", "total_amount", first_month)
    sale_totals = build_monthly_total_map(sale_queryset, "sale_date", "total_amount", first_month)
    from purchase.models import PurchaseItem

    latest_purchase_cost = PurchaseItem.objects.filter(product=OuterRef("pk")).order_by(
        "-purchase__purchase_date", "-id"
    ).values("unit_price")[:1]
    tracked_products = Product.objects.filter(track_stock=True)
    stock_summary = tracked_products.aggregate(
        total_stock_quantity=Sum("stock_quantity"),
        out_of_stock_product_total=Count("pk", filter=Q(stock_quantity=0)),
    )
    low_stock_queryset = Product.objects.filter(
        track_stock=True,
        stock_quantity__gt=0,
        stock_quantity__lte=F("low_stock_threshold"),
    )
    low_stock_product_total = low_stock_queryset.count()
    low_stock_products = list(
        low_stock_queryset
        .select_related("category")
        .order_by("stock_quantity", "name", "id")[:8]
    )
    can_view_inventory_value = user.is_superuser or user.has_perm("purchase.view_purchase")
    total_stock_value = None
    if can_view_inventory_value:
        total_stock_value = (
            tracked_products.annotate(latest_cost=Subquery(latest_purchase_cost)).aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F("stock_quantity") * F("latest_cost"),
                        output_field=DecimalField(max_digits=24, decimal_places=2),
                    )
                )
            )["total"]
            or 0
        )

    return {
        "new_order_total": order_queryset.filter(status=Order.Status.PENDING).count(),
        "user_registration_total": User.objects.count(),
        "unique_visitor_total": Session.objects.filter(expire_date__gte=timezone.now()).count(),
        "total_stock_quantity": stock_summary["total_stock_quantity"] or 0,
        "total_stock_value": total_stock_value,
        "low_stock_product_total": low_stock_product_total,
        "out_of_stock_product_total": stock_summary["out_of_stock_product_total"],
        "low_stock_products": low_stock_products,
        "can_view_inventory_value": can_view_inventory_value,
        "dashboard_sales_chart": {
            "categories": [month.isoformat() for month in month_starts],
            "series": [
                {
                    "name": "Order Value",
                    "data": [order_totals.get(month, 0) for month in month_starts],
                },
                {
                    "name": "Sales Value",
                    "data": [sale_totals.get(month, 0) for month in month_starts],
                },
            ],
        },
    }


def get_visible_orders_queryset(user):
    queryset = (
        Order.objects.select_related("user")
        .prefetch_related("items")
        .order_by("-order_date", "-id")
    )
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return queryset
    return queryset.filter(user=user)


def attach_dashboard_order_metadata(order):
    order.status_badge_class = ORDER_STATUS_BADGE_CLASSES.get(order.status, "text-bg-secondary")
    return order


def build_dashboard_order_list_context(user, page_number=None, paginate_by=DEFAULT_DASHBOARD_PAGE_SIZE, request=None):
    visible_orders = get_visible_orders_queryset(user)
    paginator = Paginator(visible_orders, paginate_by)
    page_obj = paginator.get_page(page_number)
    orders = [attach_dashboard_order_metadata(order) for order in page_obj.object_list]
    visible_sales = Sale.objects.all()
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        visible_sales = visible_sales.filter(user=user)
    context = {
        "orders": orders,
        "page_obj": page_obj,
        "order_total": paginator.count,
        "pending_order_total": visible_orders.filter(status=Order.Status.PENDING).count(),
        "cancelled_order_total": visible_orders.filter(status=Order.Status.CANCELLED).count(),
        "sale_total": visible_sales.count(),
    }
    if request is not None:
        context.update(build_dashboard_pagination_context(request, page_obj))
    return context


def build_dashboard_order_detail_context(order, status_form=None, include_tracking=False):
    attach_dashboard_order_metadata(order)
    return {
        "order": order,
        "order_items": list(order.items.all()),
        "sale": Sale.objects.filter(order=order).first(),
        "status_form": status_form or OrderStatusForm(order=order),
        "tracking": build_order_tracking_context(order) if include_tracking else None,
    }


def build_dashboard_profile_context(user, profile_form=None, password_form=None):
    profile = get_dashboard_profile(user)
    return {
        "profile_form": profile_form or DashboardProfileForm(user=user, instance=profile),
        "password_form": password_form or DashboardPasswordForm(user=user),
        "dashboard_profile": profile,
        "dashboard_profile_display_name": get_user_display_name(user),
    }


@ensure_csrf_cookie
def _render_known_template(request, prefix: str, template_path: str):
    if ".." in template_path:
        raise Http404("Invalid template path.")

    template_name = f"{prefix}/{template_path}"
    try:
        get_template(template_name)
    except TemplateDoesNotExist as exc:
        raise Http404("Template not found.") from exc
    context = {}
    if prefix == "frontend":
        stem = template_path.removesuffix(".html")
        active_map = {
            "index": "home",
            "products": "products",
            "product_details": "products",
            "cart": "cart",
            "checkout": "checkout",
            "contact": "contact",
        }
        context["active_page"] = active_map.get(stem, "")
        context["template_stem"] = stem
        if template_path == "products.html":
            context.update(build_products_listing_context(request))
    return render(request, template_name, context)


def frontend_home(request):
    context = {
        "active_page": "home",
        "template_stem": "index",
        "hero_slides": get_active_hero_slides(),
        "homepage_latest_products": get_homepage_latest_products(),
        "homepage_categories": get_homepage_categories(),
        "homepage_brands": get_homepage_brands(),
    }
    return render(request, "frontend/index.html", context)


def frontend_page(request, template_name: str):
    if not FRONTEND_TEMPLATE_RE.fullmatch(template_name):
        raise Http404("Invalid frontend page.")
    return _render_known_template(request, "frontend", template_name)


def frontend_contact(request):
    form = ContactMessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Thank you. Your message has been sent successfully. Our team will contact you soon.",
        )
        return redirect("frontend_contact")

    return render(
        request,
        "frontend/contact.html",
        {"active_page": "contact", "template_stem": "contact", "form": form},
    )


class DashboardContactMessageListView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_contactmessage"
    template_name = "dashboard/contact_messages/list.html"
    paginate_by = DEFAULT_DASHBOARD_PAGE_SIZE

    def get(self, request):
        search = request.GET.get("q", "").strip()
        status = request.GET.get("status", "").strip()
        queryset = ContactMessage.objects.all()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(area__icontains=search)
            )
        if status in ContactMessage.Status.values:
            queryset = queryset.filter(status=status)
        else:
            status = ""

        paginator = Paginator(queryset, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "contact_messages": page_obj.object_list,
                "page_obj": page_obj,
                "contact_message_total": paginator.count,
                "filters": {"q": search, "status": status},
                "status_choices": ContactMessage.Status.choices,
                **build_dashboard_pagination_context(request, page_obj),
            },
        )


class DashboardContactMessageDetailView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_contactmessage"
    template_name = "dashboard/contact_messages/detail.html"

    def get(self, request, pk):
        contact_message = get_object_or_404(ContactMessage, pk=pk)
        if (
            contact_message.status == ContactMessage.Status.NEW
            and request.user.has_perm("sitepages.change_contactmessage")
        ):
            contact_message.status = ContactMessage.Status.READ
            contact_message.save(update_fields=["status", "updated_at"])
        return render(request, self.template_name, {"contact_message": contact_message})


class DashboardContactMessageStatusView(DashboardPermissionMixin, View):
    permission_required = "sitepages.change_contactmessage"

    def post(self, request, pk, status):
        if status not in {ContactMessage.Status.READ, ContactMessage.Status.RESOLVED}:
            messages.error(request, "Invalid contact message status.")
            return redirect("dashboard_contact_message_detail", pk=pk)

        contact_message = get_object_or_404(ContactMessage, pk=pk)
        contact_message.status = status
        contact_message.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Contact message marked as {contact_message.get_status_display().lower()}.",
            extra_tags="toast-edit",
        )
        return redirect("dashboard_contact_message_detail", pk=pk)


@ensure_csrf_cookie
def frontend_product_detail(request, slug=None):
    requested_slug = slug or request.GET.get("slug")
    queryset = get_published_products_queryset(include_detail_relations=True).order_by("id")

    if requested_slug:
        product = queryset.filter(slug=requested_slug).first()
        if product is None:
            raise Http404("Product not found.")
    else:
        product = queryset.first()
        if product is None:
            raise Http404("No published products available.")

    if request.method == "POST":
        form_data = {
            "reviewer_name": (request.POST.get("reviewer_name") or "").strip(),
            "reviewer_email": (request.POST.get("reviewer_email") or "").strip(),
            "title": (request.POST.get("title") or "").strip(),
            "body": (request.POST.get("body") or "").strip(),
            "rating": (request.POST.get("rating") or "").strip(),
        }
        errors = {}

        if not form_data["reviewer_name"]:
            errors["reviewer_name"] = "Your name is required."
        if not form_data["reviewer_email"]:
            errors["reviewer_email"] = "Your email is required."
        else:
            try:
                validate_email(form_data["reviewer_email"])
            except ValidationError:
                errors["reviewer_email"] = "Enter a valid email address."
        if not form_data["title"]:
            errors["title"] = "Review title is required."
        if not form_data["body"]:
            errors["body"] = "Review text is required."

        try:
            rating = int(form_data["rating"])
            if rating < 1 or rating > 5:
                raise ValueError
        except (TypeError, ValueError):
            errors["rating"] = "Please select a rating from 1 to 5 stars."
            rating = None

        if not errors:
            ProductReview.objects.create(
                product=product,
                reviewer_name=form_data["reviewer_name"],
                reviewer_email=form_data["reviewer_email"],
                title=form_data["title"],
                body=form_data["body"],
                rating=rating,
                verified_purchase=False,
                review_date=timezone.localdate(),
            )
            return redirect(f"{redirect('frontend_product_detail', slug=product.slug).url}?review_submitted=1#pdtab-reviews")

        context = {
            "active_page": "products",
            "template_stem": "product_details",
        }
        context.update(build_product_detail_context(product))
        context.update(build_review_form_context(form_data=form_data, errors=errors))
        return render(request, "frontend/product_details.html", context)

    context = {
        "active_page": "products",
        "template_stem": "product_details",
    }
    context.update(build_product_detail_context(product))
    context.update(build_review_form_context(submitted=request.GET.get("review_submitted") == "1"))
    return render(request, "frontend/product_details.html", context)


@ensure_csrf_cookie
def frontend_cart(request):
    context = {
        "active_page": "cart",
        "template_stem": "cart",
    }
    context.update(build_cart_page_context(request))
    return render(request, "frontend/cart.html", context)


@ensure_csrf_cookie
def frontend_checkout(request):
    cart_state = get_cart_state(request)
    if request.method == "POST":
        checkout_form = CheckoutOrderForm(request.POST)
        create_or_update_abandoned_checkout(request, request.POST)
        if cart_state["is_empty"]:
            messages.error(request, "Your cart is empty. Add products before placing an order.")
        elif checkout_form.is_valid():
            try:
                order = create_order_from_checkout(request, checkout_form, cart_state)
            except ValidationError as error:
                checkout_form.add_error(None, error)
            else:
                clear_cart_session(request)
                return redirect("frontend_order_success", order_id=order.order_id)
    else:
        checkout_form = CheckoutOrderForm(initial=build_checkout_initial_data(request))
        if getattr(request.user, "is_authenticated", False) and not cart_state["is_empty"]:
            try:
                create_or_update_abandoned_checkout(request)
            except Exception:
                logger.exception(
                    "Unable to auto-save abandoned checkout for user %s.",
                    request.user.pk,
                )

    context = {
        "active_page": "checkout",
        "template_stem": "checkout",
    }
    context.update(build_checkout_page_context(request, checkout_form=checkout_form))
    return render(request, "frontend/checkout.html", context)


@require_POST
def save_abandoned_checkout(request):
    payload = _parse_json_body(request)
    abandoned_checkout = create_or_update_abandoned_checkout(request, payload)

    if abandoned_checkout is None:
        return JsonResponse(
            {
                "success": False,
                "message": "Abandoned checkout was not saved",
            }
        )

    return JsonResponse(
        {
            "success": True,
            "message": "Abandoned checkout saved",
        }
    )


def frontend_order_success(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_id=order_id)
    can_view_dashboard_orders = (
        getattr(request.user, "is_authenticated", False)
        and user_can_access_dashboard(request.user)
        and (
            request.user.is_staff
            or request.user.is_superuser
            or (order.user_id is not None and order.user_id == request.user.pk)
        )
    )
    return render(
        request,
        "frontend/order_success.html",
        {
            "active_page": "checkout",
            "template_stem": "order_success",
            "order": order,
            "can_view_dashboard_orders": can_view_dashboard_orders,
        },
    )


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _build_cart_json(request, *, message="", status=200):
    return JsonResponse({"message": message, "cart": serialize_cart_state(get_cart_state(request))}, status=status)


@require_POST
def cart_add(request):
    payload = _parse_json_body(request)
    product_id = payload.get("product_id")
    if not product_id:
        return JsonResponse({"message": "Missing product id."}, status=400)

    product = Product.objects.filter(pk=product_id, status=Product.Status.PUBLISHED).first()
    if product is None:
        return JsonResponse({"message": "Product not found."}, status=404)

    quantity = normalize_quantity(payload.get("quantity", 1))
    existing_quantity = int(request.session.get("storefront_cart", {}).get(str(product.pk), 0) or 0)
    if product.track_stock and (
        product.stock_quantity == 0 or existing_quantity + quantity > product.stock_quantity
    ):
        available = product.stock_quantity
        return JsonResponse(
            {"message": f"Only {available} unit(s) of {product.name} are available."},
            status=400,
        )
    add_to_cart_session(request, product.pk, quantity)
    return _build_cart_json(request, message=f"{product.name} added to cart.")


@require_POST
def cart_update(request):
    payload = _parse_json_body(request)
    product_id = payload.get("product_id")
    if not product_id:
        return JsonResponse({"message": "Missing product id."}, status=400)

    quantity = payload.get("quantity", 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return JsonResponse({"message": "Invalid quantity."}, status=400)

    if quantity > 0:
        product = Product.objects.filter(pk=product_id, status=Product.Status.PUBLISHED).first()
        if product is None:
            return JsonResponse({"message": "Product not found."}, status=404)
        if product.track_stock and (product.stock_quantity == 0 or quantity > product.stock_quantity):
            return JsonResponse(
                {"message": f"Only {product.stock_quantity} unit(s) of {product.name} are available."},
                status=400,
            )
    update_cart_session(request, product_id, quantity)
    return _build_cart_json(request, message="Cart updated.")


@require_POST
def cart_remove(request):
    payload = _parse_json_body(request)
    product_id = payload.get("product_id")
    if not product_id:
        return JsonResponse({"message": "Missing product id."}, status=400)

    remove_from_cart_session(request, product_id)
    return _build_cart_json(request, message="Item removed from cart.")


@require_POST
def cart_clear(request):
    clear_cart_session(request)
    return _build_cart_json(request, message="Cart cleared.")


@require_POST
def cart_set_delivery_zone(request):
    payload = _parse_json_body(request)
    zone = payload.get("zone")
    if zone not in DELIVERY_ZONES:
        return JsonResponse({"message": "Invalid delivery zone."}, status=400)

    normalized_zone = set_delivery_zone(request.session, zone)
    delivery_zone = get_delivery_zone_details(request.session)
    return JsonResponse(
        {
            "message": "Delivery area updated.",
            "delivery_zone": {
                "key": normalized_zone,
                "label": delivery_zone["label"],
                "amount": f"{delivery_zone['amount']:.2f}",
                "estimate": delivery_zone["estimate"],
            },
        }
    )


def frontend_legacy_page(request, template_name: str):
    if not FRONTEND_TEMPLATE_RE.fullmatch(template_name):
        raise Http404("Invalid frontend page.")
    return redirect("frontend_page", template_name=template_name, permanent=False)


def auth_login_view(request):
    if request.user.is_authenticated:
        fallback_url = reverse_lazy("dashboard_home") if user_can_access_dashboard(request.user) else reverse_lazy("frontend_home")
        return redirect(get_safe_redirect_url(request, str(fallback_url)))

    form = UsernameAuthenticationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is None:
            form.add_error(None, "Invalid username or password.")
        elif not user.is_active:
            form.add_error(None, "This account is inactive.")
        else:
            login(request, user)
            if not form.cleaned_data["remember_me"]:
                request.session.set_expiry(0)

            fallback_url = reverse_lazy("dashboard_home") if user_can_access_dashboard(user) else reverse_lazy("frontend_home")
            messages.success(request, "Login successful.", extra_tags="toast-create")
            return redirect(get_safe_redirect_url(request, str(fallback_url)))

    return render(
        request,
        "auth/login.html",
        {
            "form": form,
            "next": request.POST.get("next") or request.GET.get("next", ""),
        },
    )


def auth_register_view(request):
    if request.user.is_authenticated:
        fallback_url = reverse_lazy("dashboard_home") if user_can_access_dashboard(request.user) else reverse_lazy("frontend_home")
        return redirect(get_safe_redirect_url(request, str(fallback_url)))

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully.", extra_tags="toast-create")
        return redirect(get_safe_redirect_url(request, str(reverse_lazy("dashboard_home"))))

    return render(
        request,
        "auth/register.html",
        {
            "form": form,
            "next": request.POST.get("next") or request.GET.get("next", ""),
        },
    )


@require_POST
def auth_logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.", extra_tags="toast-edit")
    return redirect(get_safe_redirect_url(request, str(reverse_lazy("frontend_home"))))


@login_required
@ensure_csrf_cookie
def dashboard_home(request):
    if not user_can_access_dashboard(request.user):
        messages.error(request, "You do not have permission to access the dashboard.")
        return redirect("frontend_home")
    return render(request, "dashboard/index.html", build_dashboard_home_context(request.user))


class DashboardProfileView(DashboardAccessMixin, View):
    template_name = "dashboard/profile.html"

    def get(self, request):
        return render(request, self.template_name, build_dashboard_profile_context(request.user))

    def post(self, request):
        profile = get_dashboard_profile(request.user)
        action = request.POST.get("form_type")

        if action == "password":
            password_form = DashboardPasswordForm(user=request.user, data=request.POST)
            profile_form = DashboardProfileForm(user=request.user, instance=profile)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.", extra_tags="toast-edit")
                return redirect("dashboard_profile")
            return render(
                request,
                self.template_name,
                build_dashboard_profile_context(request.user, profile_form=profile_form, password_form=password_form),
            )

        profile_form = DashboardProfileForm(request.POST, request.FILES, user=request.user, instance=profile)
        password_form = DashboardPasswordForm(user=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated successfully.", extra_tags="toast-edit")
            return redirect("dashboard_profile")
        return render(
            request,
            self.template_name,
            build_dashboard_profile_context(request.user, profile_form=profile_form, password_form=password_form),
        )


class HeroSlideDashboardMixin(DashboardPermissionMixin):
    model = HeroSlide
    form_class = HeroSlideForm
    success_url = reverse_lazy("dashboard_hero_slide_list")
    permission_required = "sitepages.view_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hero_slide_total"] = HeroSlide.objects.count()
        context["hero_slide_active_total"] = HeroSlide.objects.filter(is_active=True).count()
        return context


class HeroSlideListView(HeroSlideDashboardMixin, ListView):
    context_object_name = "hero_slides"
    paginate_by = 10
    template_name = "dashboard/carousel/list.html"

    def get_queryset(self):
        return HeroSlide.objects.order_by("sort_order", "id")


class HeroSlideCreateView(HeroSlideDashboardMixin, CreateView):
    template_name = "dashboard/carousel/form.html"
    permission_required = "sitepages.add_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Hero Slide"
        context["submit_label"] = "Save Slide"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Hero slide created successfully.", extra_tags="toast-create")
        return response


class HeroSlideUpdateView(HeroSlideDashboardMixin, UpdateView):
    template_name = "dashboard/carousel/form.html"
    permission_required = "sitepages.change_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Hero Slide"
        context["submit_label"] = "Update Slide"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Hero slide updated successfully.", extra_tags="toast-edit")
        return response


class HeroSlideDeleteView(DashboardPermissionMixin, View):
    permission_required = "sitepages.delete_heroslide"

    def post(self, request, pk):
        hero_slide = get_object_or_404(HeroSlide, pk=pk)
        slide_name = hero_slide.name
        hero_slide.delete()
        messages.error(
            request,
            f'"{slide_name}" deleted successfully.',
            extra_tags="toast-delete",
        )
        return redirect("dashboard_hero_slide_list")


class DashboardUserListView(DashboardPermissionMixin, ListView):
    model = User
    context_object_name = "users"
    paginate_by = 12
    permission_required = "auth.view_user"
    template_name = "dashboard/users/list.html"

    def get_queryset(self):
        return User.objects.prefetch_related("groups").order_by("-date_joined", "-id")

    def get_context_data(self, **kwargs):
        from .permissions import ensure_default_roles

        ensure_default_roles()
        context = super().get_context_data(**kwargs)
        for user in context["users"]:
            user.display_name = get_user_display_name(user)
            user.primary_role = user.groups.order_by("name").first()
            user.primary_role_profile = get_role_profile(user.primary_role) if user.primary_role else None

        context["user_total"] = User.objects.count()
        context["user_active_total"] = User.objects.filter(is_active=True).count()
        context["role_total"] = Group.objects.count()
        return context


class DashboardUserStatusToggleView(DashboardPermissionMixin, View):
    permission_required = "auth.change_user"

    def post(self, request, pk):
        target_user = get_object_or_404(User, pk=pk)
        if target_user.is_superuser and request.user.pk != target_user.pk:
            messages.error(request, "Superuser status must be managed from the account itself.")
            return redirect("dashboard_user_list")

        target_user.is_active = request.POST.get("is_active") == "on"
        target_user.save(update_fields=["is_active"])
        messages.info(request, "User status updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_user_list")


class DashboardUserPermissionView(DashboardPermissionMixin, View):
    permission_required = ("auth.view_user", "auth.change_user", "auth.change_group")
    template_name = "dashboard/users/permissions.html"

    def get_selected_role(self, user, role_id=None):
        if role_id and str(role_id).isdigit():
            return Group.objects.filter(pk=int(role_id)).first()
        return user.groups.order_by("name").first() or Group.objects.order_by("name").first()

    def get(self, request, pk):
        target_user = get_object_or_404(User.objects.prefetch_related("groups", "user_permissions"), pk=pk)
        selected_role = self.get_selected_role(target_user, request.GET.get("role"))
        context = build_dashboard_user_context(target_user, selected_role)
        return render(request, self.template_name, context)

    def post(self, request, pk):
        target_user = get_object_or_404(User.objects.prefetch_related("groups", "user_permissions"), pk=pk)
        selected_role = self.get_selected_role(target_user, request.POST.get("role"))

        if selected_role is None:
            messages.error(request, "Select a valid role before saving.")
            return render(request, self.template_name, build_dashboard_user_context(target_user, selected_role))

        selected_role_profile = get_role_profile(selected_role)
        if not selected_role_profile.is_active:
            messages.error(request, "The selected role is inactive. Activate it before assigning this user.")
            return render(request, self.template_name, build_dashboard_user_context(target_user, selected_role))

        managed_permission_ids = get_managed_permission_ids()
        selected_permission_ids = get_permission_ids_for_cells(request.POST.getlist("permission_cells"))
        selected_permission_ids &= managed_permission_ids
        preserved_permission_ids = set(
            target_user.user_permissions.exclude(id__in=managed_permission_ids).values_list("id", flat=True)
        )
        target_user.user_permissions.set(sorted(preserved_permission_ids | selected_permission_ids))

        target_user.groups.set([selected_role])
        target_user.is_active = request.POST.get("is_active") == "on"
        target_user.is_staff = target_user.is_superuser or request.POST.get("is_staff") == "on"
        target_user.save(update_fields=["is_active", "is_staff"])

        messages.success(request, "User role and direct permissions updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_user_list")


class DashboardRoleListView(DashboardPermissionMixin, View):
    permission_required = "auth.view_group"
    template_name = "dashboard/users/roles.html"

    def get_edit_role(self, role_id):
        if role_id and str(role_id).isdigit():
            return Group.objects.select_related("role_profile").filter(pk=int(role_id)).first()
        return None

    def get(self, request):
        edit_role = self.get_edit_role(request.GET.get("edit"))
        form = RoleForm(role=edit_role)
        return render(request, self.template_name, build_dashboard_role_list_context(form, edit_role))

    def post(self, request):
        edit_role = self.get_edit_role(request.POST.get("role_id"))
        required_permission = "auth.change_group" if edit_role is not None else "auth.add_group"
        if not request.user.has_perm(required_permission):
            messages.error(request, "You do not have permission to save roles.")
            form = RoleForm(request.POST, role=edit_role)
            return render(request, self.template_name, build_dashboard_role_list_context(form, edit_role))

        form = RoleForm(request.POST, role=edit_role)
        if form.is_valid():
            role = form.save()
            action_message = "Role updated successfully." if edit_role is not None else "Role created successfully."
            message_tag = "toast-edit" if edit_role is not None else "toast-create"
            messages.success(request, action_message, extra_tags=message_tag)
            return redirect("dashboard_role_list")

        return render(request, self.template_name, build_dashboard_role_list_context(form, edit_role))


class DashboardRoleStatusToggleView(DashboardPermissionMixin, View):
    permission_required = "auth.change_group"

    def post(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile"), pk=pk)
        profile = get_role_profile(role)
        profile.is_active = request.POST.get("is_active") == "on"
        profile.save(update_fields=["is_active", "updated_at"])
        messages.info(request, "Role status updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_role_list")


class DashboardRolePermissionView(DashboardPermissionMixin, View):
    permission_required = ("auth.view_group", "auth.change_group")
    template_name = "dashboard/users/role_permissions.html"

    def get(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile").prefetch_related("permissions"), pk=pk)
        return render(request, self.template_name, build_dashboard_role_permission_context(role))

    def post(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile").prefetch_related("permissions"), pk=pk)
        managed_permission_ids = get_managed_permission_ids()
        selected_permission_ids = get_permission_ids_for_cells(request.POST.getlist("permission_cells"))
        selected_permission_ids &= managed_permission_ids
        preserved_permission_ids = set(role.permissions.exclude(id__in=managed_permission_ids).values_list("id", flat=True))
        role.permissions.set(sorted(preserved_permission_ids | selected_permission_ids))

        messages.success(request, "Role permissions updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_role_list")


class DashboardOrderListView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_order"
    template_name = "dashboard/orders/list.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            build_dashboard_order_list_context(request.user, page_number=request.GET.get("page")),
        )


class DashboardOrderDetailView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_order"
    template_name = "dashboard/orders/detail.html"

    def get(self, request, order_id):
        order = get_object_or_404(get_visible_orders_queryset(request.user), order_id=order_id)
        return render(request, self.template_name, build_dashboard_order_detail_context(order))

    def post(self, request, order_id):
        order = get_object_or_404(get_visible_orders_queryset(request.user), order_id=order_id)
        if not (request.user.is_superuser or request.user.has_perm("sitepages.change_order")):
            messages.error(request, "You do not have permission to update this order.")
            return redirect("dashboard_order_detail", order_id=order.order_id)

        status_form = OrderStatusForm(request.POST, order=order)
        if status_form.is_valid():
            new_status = status_form.cleaned_data["status"]
            try:
                status_change = change_order_status(
                    order=order,
                    new_status=new_status,
                    changed_by=request.user,
                    note=status_form.cleaned_data["note"],
                    source="dashboard",
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("dashboard_order_detail", order_id=order.order_id)

            if status_change.changed:
                if new_status == order.Status.CONFIRMED:
                    messages.success(request, "Order confirmed and sale generated successfully.", extra_tags="toast-edit")
                else:
                    messages.success(request, "Order status updated successfully.", extra_tags="toast-edit")
            else:
                messages.info(request, "Order status was already set to that value.", extra_tags="toast-edit")
            return redirect("dashboard_order_detail", order_id=order.order_id)

        return render(request, self.template_name, build_dashboard_order_detail_context(order, status_form=status_form))


