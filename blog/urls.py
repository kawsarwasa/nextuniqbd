from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/blog/categories/", views.BlogCategoryListView.as_view(), name="dashboard_blog_category_list"),
    path("dashboard/blog/categories/add/", views.BlogCategoryCreateView.as_view(), name="dashboard_blog_category_add"),
    path(
        "dashboard/blog/categories/<int:pk>/edit/",
        views.BlogCategoryUpdateView.as_view(),
        name="dashboard_blog_category_edit",
    ),
    path(
        "dashboard/blog/categories/<int:pk>/delete/",
        views.BlogCategoryDeleteView.as_view(),
        name="dashboard_blog_category_delete",
    ),
    path("dashboard/blog/tags/", views.BlogTagListView.as_view(), name="dashboard_blog_tag_list"),
    path("dashboard/blog/tags/add/", views.BlogTagCreateView.as_view(), name="dashboard_blog_tag_add"),
    path(
        "dashboard/blog/tags/<int:pk>/edit/",
        views.BlogTagUpdateView.as_view(),
        name="dashboard_blog_tag_edit",
    ),
    path(
        "dashboard/blog/tags/<int:pk>/delete/",
        views.BlogTagDeleteView.as_view(),
        name="dashboard_blog_tag_delete",
    ),
    path("dashboard/blog/posts/", views.BlogPostListView.as_view(), name="dashboard_blog_post_list"),
    path("dashboard/blog/posts/add/", views.BlogPostCreateView.as_view(), name="dashboard_blog_post_add"),
    path("dashboard/blog/posts/<int:pk>/", views.BlogPostDetailView.as_view(), name="dashboard_blog_post_detail"),
    path(
        "dashboard/blog/posts/<int:pk>/edit/",
        views.BlogPostUpdateView.as_view(),
        name="dashboard_blog_post_edit",
    ),
    path(
        "dashboard/blog/posts/<int:pk>/delete/",
        views.BlogPostDeleteView.as_view(),
        name="dashboard_blog_post_delete",
    ),
    path("dashboard/blog/comments/", views.BlogCommentListView.as_view(), name="dashboard_blog_comment_list"),
    path("dashboard/blog/comments/add/", views.BlogCommentCreateView.as_view(), name="dashboard_blog_comment_add"),
    path(
        "dashboard/blog/comments/<int:pk>/edit/",
        views.BlogCommentUpdateView.as_view(),
        name="dashboard_blog_comment_edit",
    ),
    path(
        "dashboard/blog/comments/<int:pk>/delete/",
        views.BlogCommentDeleteView.as_view(),
        name="dashboard_blog_comment_delete",
    ),
]
