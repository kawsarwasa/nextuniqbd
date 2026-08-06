from datetime import date

from django.core.cache import cache
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from category.models import Brand, Category, Product, ProductImage, ProductReview
from sitepages.cache import HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY


class HomepagePerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Homepage Brand", is_active=True, show_on_homepage=True)
        cls.categories = [
            Category.objects.create(
                name=f"Homepage Category {index}",
                sort_order=index,
                is_active=True,
                show_on_homepage=True,
            )
            for index in range(1, 5)
        ]
        cls.products = []
        for category in cls.categories:
            for index in range(6):
                cls.products.append(
                    Product.objects.create(
                        category=category,
                        brand=cls.brand,
                        name=f"Product {category.sort_order}-{index}",
                        regular_price="100.00",
                        current_price="80.00" if index % 2 == 0 else "100.00",
                        sku="invalid",
                        status=Product.Status.PUBLISHED,
                        availability="In Stock",
                        stock_quantity=100,
                    )
                )

    def setUp(self):
        cache.clear()

    def test_populated_homepage_has_bounded_cold_and_warm_query_counts(self):
        # The homepage cards use a bounded set of aggregate/prefetch queries.
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("frontend_home"))
        self.assertLessEqual(len(queries), 24)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["homepage_latest_products"]), 20)

        with self.assertNumQueries(0):
            warm_response = self.client.get(reverse("frontend_home"))
        self.assertEqual(warm_response.status_code, 200)

    def test_product_image_and_review_changes_invalidate_latest_product_cache(self):
        self.client.get(reverse("frontend_home"))
        self.assertIsNotNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))

        ProductReview.objects.create(
            product=self.products[0],
            reviewer_name="Cache Reviewer",
            title="Updated rating",
            body="Invalidate the homepage cards.",
            rating=5,
            review_date=date.today(),
        )
        self.assertIsNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))

        self.client.get(reverse("frontend_home"))
        self.assertIsNotNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))
        ProductImage.objects.create(product=self.products[0], image="products/cache-invalidation.jpg")
        self.assertIsNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))
