from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/company/", views.CompanyProfileListView.as_view(), name="dashboard_company_profile_list"),
    path("dashboard/company/add/", views.CompanyProfileCreateView.as_view(), name="dashboard_company_profile_add"),
    path(
        "dashboard/company/<int:pk>/edit/",
        views.CompanyProfileUpdateView.as_view(),
        name="dashboard_company_profile_edit",
    ),
    path(
        "dashboard/company/<int:pk>/delete/",
        views.CompanyProfileDeleteView.as_view(),
        name="dashboard_company_profile_delete",
    ),
]
