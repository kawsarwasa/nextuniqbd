from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/categories/", views.CategoryListView.as_view(), name="dashboard_category_list"),
    path("dashboard/categories/add/", views.CategoryCreateView.as_view(), name="dashboard_category_add"),
    path(
        "dashboard/categories/<int:pk>/edit/",
        views.CategoryUpdateView.as_view(),
        name="dashboard_category_edit",
    ),
    path(
        "dashboard/categories/<int:pk>/delete/",
        views.CategoryDeleteView.as_view(),
        name="dashboard_category_delete",
    ),
    path("dashboard/brands/", views.BrandListView.as_view(), name="dashboard_brand_list"),
    path("dashboard/brands/add/", views.BrandCreateView.as_view(), name="dashboard_brand_add"),
    path(
        "dashboard/brands/<int:pk>/edit/",
        views.BrandUpdateView.as_view(),
        name="dashboard_brand_edit",
    ),
    path(
        "dashboard/brands/<int:pk>/delete/",
        views.BrandDeleteView.as_view(),
        name="dashboard_brand_delete",
    ),
    path("dashboard/products/", views.ProductListView.as_view(), name="dashboard_product_list"),
    path("dashboard/products/bulk-action/", views.ProductBulkActionView.as_view(), name="dashboard_product_bulk_action"),
    path("dashboard/inventory/", views.InventoryReportView.as_view(), name="dashboard_inventory_report"),
    path("dashboard/inventory/history/", views.StockHistoryView.as_view(), name="dashboard_stock_history"),
    path("dashboard/products/add/", views.ProductCreateView.as_view(), name="dashboard_product_add"),
    path(
        "dashboard/products/<int:pk>/duplicate/",
        views.ProductDuplicateView.as_view(),
        name="dashboard_product_duplicate",
    ),
    path(
        "dashboard/products/<int:pk>/",
        views.ProductDetailView.as_view(),
        name="dashboard_product_detail",
    ),
    path(
        "dashboard/products/<int:pk>/edit/",
        views.ProductUpdateView.as_view(),
        name="dashboard_product_edit",
    ),
    path(
        "dashboard/products/<int:pk>/delete/",
        views.ProductDeleteView.as_view(),
        name="dashboard_product_delete",
    ),
]
