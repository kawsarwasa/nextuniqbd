from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/orders/", views.DashboardOrderListView.as_view(), name="dashboard_order_list"),
    path(
        "dashboard/orders/<str:order_id>/tracking/",
        views.DashboardOrderTrackingView.as_view(),
        name="dashboard_order_tracking",
    ),
    path(
        "dashboard/abandoned-checkouts/",
        views.DashboardAbandonedCheckoutListView.as_view(),
        name="dashboard_abandoned_checkout_list",
    ),
    path(
        "dashboard/abandoned-checkouts/<int:pk>/",
        views.DashboardAbandonedCheckoutDetailView.as_view(),
        name="dashboard_abandoned_checkout_detail",
    ),
    path(
        "dashboard/abandoned-checkouts/<int:pk>/status/<str:status>/",
        views.DashboardAbandonedCheckoutStatusView.as_view(),
        name="dashboard_abandoned_checkout_status",
    ),
    path("dashboard/sales/", views.DashboardSaleListView.as_view(), name="dashboard_sale_list"),
    path("dashboard/sales/<str:sale_id>/", views.DashboardSaleDetailView.as_view(), name="dashboard_sale_detail"),
    path("dashboard/orders/<str:order_id>/", views.DashboardOrderDetailView.as_view(), name="dashboard_order_detail"),
]
