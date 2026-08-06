from django.test import TestCase
from .models import BlogCategory, BlogPost

class BlogModelTests(TestCase):
    def test_blog_post_slug_is_generated(self):
        category = BlogCategory.objects.create(name="News")
        post = BlogPost.objects.create(category=category, title="Spring Collection", author_name="Admin")
        self.assertEqual(post.slug, "spring-collection")
