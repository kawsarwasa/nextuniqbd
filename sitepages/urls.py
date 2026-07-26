from django.urls import path, re_path, register_converter
from django.views.generic import RedirectView

from . import views


class FrontendPageConverter:
    regex = r"[a-zA-Z0-9_-]+"

    def to_python(self, value):
        return value.replace("-", "_") + ".html"

    def to_url(self, value):
        if value.endswith(".html"):
            value = value[:-5]
        return value.replace("_", "-")


register_converter(FrontendPageConverter, "frontendpage")

urlpatterns = [
    path("", views.frontend_home, name="frontend_home"),
    path("index.html", RedirectView.as_view(pattern_name="frontend_home", permanent=False), name="frontend_home_legacy"),
    path("login/", views.auth_login_view, name="auth_login"),
    path("register/", views.auth_register_view, name="auth_register"),
    path("logout/", views.auth_logout_view, name="auth_logout"),
    path("about/", views.frontend_page, {"template_name": "about.html"}, name="frontend_about"),
    path(
        "privacy-policy/",
        views.frontend_page,
        {"template_name": "privacy_policy.html"},
        name="frontend_privacy_policy",
    ),
    path("blog/", views.frontend_blog, name="frontend_blog"),
    path("blog/<slug:slug>/", views.frontend_blog_detail, name="frontend_blog_detail"),
    path("blog-details/", views.frontend_blog_detail, name="frontend_blog_details"),
    path("cart/", views.frontend_cart, name="frontend_cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    path("cart/clear/", views.cart_clear, name="cart_clear"),
    path("cart/delivery-zone/", views.cart_set_delivery_zone, name="cart_set_delivery_zone"),
    path("checkout/", views.frontend_checkout, name="frontend_checkout"),
    path(
        "checkout/save-abandoned-checkout/",
        views.save_abandoned_checkout,
        name="save_abandoned_checkout",
    ),
    path("checkout/success/<str:order_id>/", views.frontend_order_success, name="frontend_order_success"),
    path("contact/", views.frontend_page, {"template_name": "contact.html"}, name="frontend_contact"),
    path("products/<slug:slug>/", views.frontend_product_detail, name="frontend_product_detail"),
    path("products/", views.frontend_page, {"template_name": "products.html"}, name="frontend_products"),
    path("product-details/", views.frontend_product_detail, name="frontend_product_details"),
    path("dashboard/", views.dashboard_home, name="dashboard_home"),
    path("dashboard/promo-banners/", views.HomepagePromoBannerListView.as_view(), name="dashboard_promo_banner_list"),
    path("dashboard/promo-banners/add/", views.HomepagePromoBannerCreateView.as_view(), name="dashboard_promo_banner_add"),
    path(
        "dashboard/promo-banners/<int:pk>/edit/",
        views.HomepagePromoBannerUpdateView.as_view(),
        name="dashboard_promo_banner_edit",
    ),
    path(
        "dashboard/promo-banners/<int:pk>/delete/",
        views.HomepagePromoBannerDeleteView.as_view(),
        name="dashboard_promo_banner_delete",
    ),
    re_path(r"^(?P<template_name>[a-zA-Z0-9_]+\.html)$", views.frontend_legacy_page, name="frontend_page_legacy"),
    path("<frontendpage:template_name>/", views.frontend_page, name="frontend_page"),
]
