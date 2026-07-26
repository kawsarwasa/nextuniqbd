from django.urls import path

from . import views


app_name = "finance"


urlpatterns = [
    path("", views.finance_dashboard, name="dashboard"),
    path("transactions/", views.TransactionListView.as_view(), name="transaction_list"),
    path("opening-balance/", views.OpeningBalanceCreateView.as_view(), name="opening_balance"),
    path("cash-in/", views.CashInListView.as_view(), name="cash_in_list"),
    path("cash-in/add/", views.CashInCreateView.as_view(), name="cash_in_create"),
    path("cash-in/<int:pk>/edit/", views.CashInUpdateView.as_view(), name="cash_in_update"),
    path("cash-in/<int:pk>/delete/", views.CashInDeleteView.as_view(), name="cash_in_delete"),
    path("cash-out/", views.CashOutListView.as_view(), name="cash_out_list"),
    path("cash-out/add/", views.CashOutCreateView.as_view(), name="cash_out_create"),
    path("cash-out/<int:pk>/edit/", views.CashOutUpdateView.as_view(), name="cash_out_update"),
    path("cash-out/<int:pk>/delete/", views.CashOutDeleteView.as_view(), name="cash_out_delete"),
    path("dues/", views.DueListView.as_view(), name="due_list"),
    path("dues/add/", views.DueAccountCreateView.as_view(), name="due_create"),
    path("dues/<int:due_pk>/payments/add/", views.DuePaymentCreateView.as_view(), name="due_payment_create"),
    path(
        "dues/<int:due_pk>/payments/<int:pk>/edit/",
        views.DuePaymentUpdateView.as_view(),
        name="due_payment_update",
    ),
    path(
        "dues/<int:due_pk>/payments/<int:pk>/delete/",
        views.DuePaymentDeleteView.as_view(),
        name="due_payment_delete",
    ),
    path("dues/<int:pk>/", views.DueDetailView.as_view(), name="due_detail"),
    path("dues/<int:pk>/edit/", views.DueAccountUpdateView.as_view(), name="due_update"),
    path("dues/<int:pk>/delete/", views.DueAccountDeleteView.as_view(), name="due_delete"),
    path("categories/", views.TransactionCategoryListView.as_view(), name="category_list"),
    path("categories/add/", views.TransactionCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.TransactionCategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.TransactionCategoryDeleteView.as_view(), name="category_delete"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
]
