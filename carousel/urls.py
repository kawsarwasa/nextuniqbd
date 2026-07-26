from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/carousel/", views.HeroSlideListView.as_view(), name="dashboard_hero_slide_list"),
    path("dashboard/carousel/add/", views.HeroSlideCreateView.as_view(), name="dashboard_hero_slide_add"),
    path("dashboard/carousel/<int:pk>/edit/", views.HeroSlideUpdateView.as_view(), name="dashboard_hero_slide_edit"),
    path("dashboard/carousel/<int:pk>/delete/", views.HeroSlideDeleteView.as_view(), name="dashboard_hero_slide_delete"),
]
