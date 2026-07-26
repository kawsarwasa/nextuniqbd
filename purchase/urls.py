from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/purchases/", views.PurchaseListView.as_view(), name="dashboard_purchase_list"),
    path("dashboard/purchases/add/", views.PurchaseCreateView.as_view(), name="dashboard_purchase_add"),
    path("dashboard/purchases/<int:pk>/", views.PurchaseDetailView.as_view(), name="dashboard_purchase_detail"),
    path("dashboard/purchases/<int:pk>/edit/", views.PurchaseUpdateView.as_view(), name="dashboard_purchase_edit"),
    path("dashboard/purchases/<int:pk>/delete/", views.PurchaseDeleteView.as_view(), name="dashboard_purchase_delete"),
]
