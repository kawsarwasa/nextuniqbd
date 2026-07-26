from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import BlogCategory, BlogPost


User = get_user_model()


class BlogDashboardSmokeTests(TestCase):
    def setUp(self):
        self.dashboard_user = User.objects.create_superuser(
            username="blog-admin@example.com",
            email="blog-admin@example.com",
            password="Admin@100%",
        )

    def test_blog_post_slug_is_generated(self):
        category = BlogCategory.objects.create(name="News")
        post = BlogPost.objects.create(category=category, title="Spring Collection", author_name="Admin")
        self.assertEqual(post.slug, "spring-collection")

    def test_blog_post_list_view_renders(self):
        self.client.force_login(self.dashboard_user)
        response = self.client.get(reverse("dashboard_blog_post_list"))
        self.assertEqual(response.status_code, 200)
