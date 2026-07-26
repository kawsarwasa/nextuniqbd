from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/profile/", views.DashboardProfileView.as_view(), name="dashboard_profile"),
    path("dashboard/users/", views.DashboardUserListView.as_view(), name="dashboard_user_list"),
    path("dashboard/users/<int:pk>/status/", views.DashboardUserStatusToggleView.as_view(), name="dashboard_user_status"),
    path(
        "dashboard/users/<int:pk>/permissions/",
        views.DashboardUserPermissionView.as_view(),
        name="dashboard_user_permissions",
    ),
    path("dashboard/roles/", views.DashboardRoleListView.as_view(), name="dashboard_role_list"),
    path("dashboard/roles/<int:pk>/status/", views.DashboardRoleStatusToggleView.as_view(), name="dashboard_role_status"),
    path(
        "dashboard/roles/<int:pk>/permissions/",
        views.DashboardRolePermissionView.as_view(),
        name="dashboard_role_permissions",
    ),
]
