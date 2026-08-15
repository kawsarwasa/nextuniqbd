from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from category.models import Brand, Category, Product
from sitepages.cache import HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY


class HomepageLatestProductsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_category = Category.objects.create(name="Active category", is_active=True)
        cls.inactive_category = Category.objects.create(name="Inactive category", is_active=False)
        cls.brand = Brand.objects.create(name="Homepage brand", is_active=True)

    def setUp(self):
        cache.clear()

    def create_product(self, name, *, category=None, status=Product.Status.PUBLISHED, stock=10):
        return Product.objects.create(
            category=category or self.active_category,
            brand=self.brand,
            name=name,
            regular_price="100.00",
            current_price="80.00",
            sku="invalid",
            status=status,
            stock_quantity=stock,
            availability="In Stock" if stock else "Out of Stock",
        )

    def homepage_latest_products(self):
        response = self.client.get(reverse("frontend_home"))
        self.assertEqual(response.status_code, 200)
        return response.context["homepage_latest_products"], response

    def test_latest_products_are_public_newest_first_and_limited_to_twenty(self):
        products = [self.create_product(f"Product {index}") for index in range(22)]
        start = timezone.now() - timedelta(days=1)
        for index, product in enumerate(products):
            Product.objects.filter(pk=product.pk).update(created_at=start + timedelta(minutes=index))

        draft = self.create_product("Draft product", status=Product.Status.DRAFT)
        inactive_product = self.create_product("Inactive product", status=Product.Status.INACTIVE)
        inactive_category_product = self.create_product("Hidden category product", category=self.inactive_category)
        Product.objects.filter(pk=draft.pk).update(created_at=timezone.now() + timedelta(days=1))
        Product.objects.filter(pk=inactive_product.pk).update(created_at=timezone.now() + timedelta(days=1))
        Product.objects.filter(pk=inactive_category_product.pk).update(created_at=timezone.now() + timedelta(days=1))

        latest_products, response = self.homepage_latest_products()

        self.assertEqual(len(latest_products), 20)
        self.assertEqual(
            [product.pk for product in latest_products],
            [product.pk for product in reversed(products[-20:])],
        )
        self.assertNotIn(draft.pk, [product.pk for product in latest_products])
        self.assertNotIn(inactive_product.pk, [product.pk for product in latest_products])
        self.assertNotIn(inactive_category_product.pk, [product.pk for product in latest_products])
        self.assertContains(response, "Latest Products")
        self.assertContains(response, reverse("frontend_products"))

    def test_product_changes_invalidate_the_latest_products_cache(self):
        product = self.create_product("Cached latest product")
        self.client.get(reverse("frontend_home"))
        self.assertIsNotNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))

        product.name = "Updated latest product"
        product.save(update_fields=["name"])
        self.assertIsNone(cache.get(HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY))

    def test_inactive_products_are_excluded_from_the_public_product_listing(self):
        inactive_product = self.create_product("Inactive public product", status=Product.Status.INACTIVE)

        response = self.client.get(reverse("frontend_products"), {"q": inactive_product.name})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(inactive_product.pk, [product.pk for product in response.context["products"]])
