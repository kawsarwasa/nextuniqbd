from datetime import timedelta
from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from purchase.models import Purchase, PurchaseItem, PurchaseStockApplication
from purchase.services import sync_received_purchase_stock
from sitepages.models import Order, OrderItem, OrderStatusHistory, Sale, SaleItem

from .forms import ProductForm
from .image_derivatives import product_image_legacy_derivative_name, product_image_optimized_name
from .models import Brand, Category, Product, ProductImage, ProductReview, StockTransaction


class ProductFormTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics")
        self.brand = Brand.objects.create(name="Acme")

    def test_new_product_form_prefills_visible_defaults(self):
        form = ProductForm()

        self.assertEqual(form.fields["status"].initial, Product.Status.PUBLISHED)
        self.assertEqual(form.fields["availability"].initial, ProductForm.AVAILABILITY_IN_STOCK)
        self.assertIsNone(form.fields["sku"].initial)
        self.assertFalse(form.fields["sku"].disabled)
        self.assertTrue(form.fields["sku"].required)
        self.assertNotIn("minlength", form.fields["sku"].widget.attrs)
        self.assertEqual(form.fields["sku"].widget.attrs["maxlength"], Product.SKU_LENGTH)
        self.assertIn("is_featured", form.fields)
        self.assertFalse(form.fields["is_featured"].initial)

    def test_form_accepts_skus_up_to_twelve_characters_and_preserves_case(self):
        for sku in (
            "A",
            "AB",
            "abc123",
            "Ab#29x",
            "SKU@2026",
            "123456789012",
            "Ab3#xY9!Q2@k",
        ):
            with self.subTest(sku=sku):
                form = ProductForm(
                    data={
                        "category": self.category.pk,
                        "name": "Wireless Mouse",
                        "regular_price": "1200",
                        "current_price": "999",
                        "sku": sku,
                        "brand": self.brand.pk,
                        "status": Product.Status.PUBLISHED,
                        "availability": ProductForm.AVAILABILITY_OUT_OF_STOCK,
                        "track_stock": "on",
                        "stock_quantity": "0",
                        "low_stock_threshold": "5",
                        "short_description": "Compact mouse",
                        "full_description_html": "<p>Compact mouse</p>",
                    }
                )

                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["availability"], ProductForm.AVAILABILITY_OUT_OF_STOCK)
                self.assertEqual(form.cleaned_data["sku"], sku)

    def test_form_rejects_a_blank_sku(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sku"], ["This field is required."])

    def test_form_rejects_sku_that_is_too_long(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "ABC123xyz!@#4",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sku"], ["SKU cannot be more than 12 characters."])

    def test_form_rejects_whitespace_in_sku(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "ABC DEF12345",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["sku"],
            ["SKU can contain letters, numbers, and symbols, but not whitespace."],
        )

    def test_form_trims_accidental_surrounding_sku_whitespace(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "  ABC12  ",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sku"], "ABC12")

    def test_form_rejects_duplicate_manual_sku_on_create(self):
        Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="Ab3#xY9!Q2@k",
            status=Product.Status.PUBLISHED,
            availability=ProductForm.AVAILABILITY_IN_STOCK,
        )
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "Ab3#xY9!Q2@k",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A product with this SKU already exists.", form.errors["sku"])

    def test_edit_form_allows_manual_sku_update(self):
        product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="NUBabc",
            status=Product.Status.PUBLISHED,
            availability=ProductForm.AVAILABILITY_IN_STOCK,
        )
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "ABC123xyz!@#",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            },
            instance=product,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sku"], "ABC123xyz!@#")

    def test_edit_form_allows_an_unchanged_legacy_sku(self):
        product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="NUBabc",
            status=Product.Status.PUBLISHED,
            availability=ProductForm.AVAILABILITY_IN_STOCK,
        )
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Existing Mouse",
                "regular_price": "1300",
                "current_price": "999",
                "sku": "NUBabc",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            },
            instance=product,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sku"], "NUBabc")
        saved_product = form.save()
        self.assertEqual(saved_product.sku, "NUBabc")

    def test_edit_form_requires_a_changed_sku_to_follow_the_current_maximum(self):
        product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="NUBabc",
        )
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Existing Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "ABC123xyz!@#4",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            },
            instance=product,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["sku"], ["SKU cannot be more than 12 characters."])

    def test_form_rejects_negative_stock_values(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "NUBABC123XYZ",
                "brand": self.brand.pk,
                "status": Product.Status.PUBLISHED,
                "availability": ProductForm.AVAILABILITY_IN_STOCK,
                "track_stock": "on",
                "stock_quantity": "-1",
                "low_stock_threshold": "-1",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("stock_quantity", form.errors)
        self.assertIn("low_stock_threshold", form.errors)


class ProductModelTests(TestCase):
    def test_product_save_generates_unique_sku_when_blank(self):
        category = Category.objects.create(name="Books")
        product = Product.objects.create(
            category=category,
            name="Notebook",
            regular_price="100",
            current_price="80",
            sku="",
            status=Product.Status.DRAFT,
            availability="",
        )

        self.assertLessEqual(len(product.sku), Product.SKU_LENGTH)
        self.assertTrue(all(character in Product.SKU_ALPHABET for character in product.sku))
        self.assertFalse(product.sku.startswith("NUB"))

        another_product = Product.objects.create(
            category=category,
            name="Notebook Pro",
            regular_price="200",
            current_price="150",
            sku="",
            status=Product.Status.DRAFT,
            availability="",
        )

        self.assertLessEqual(len(another_product.sku), Product.SKU_LENGTH)
        self.assertTrue(all(character in Product.SKU_ALPHABET for character in another_product.sku))
        self.assertNotEqual(product.sku, another_product.sku)

    def test_product_save_does_not_replace_a_nonblank_legacy_or_manual_sku(self):
        category = Category.objects.create(name="Accessories")
        product = Product.objects.create(
            category=category,
            name="Travel Bag",
            regular_price="100",
            current_price="80",
            sku="MANUAL123",
            status=Product.Status.DRAFT,
            availability="In Stock",
        )

        self.assertEqual(product.sku, "MANUAL123")

    def test_product_save_preserves_valid_manually_entered_sku_case(self):
        category = Category.objects.create(name="Accessories")
        product = Product.objects.create(
            category=category,
            name="Travel Bag",
            regular_price="100",
            current_price="80",
            sku="AbC123#xyZ!9",
            status=Product.Status.DRAFT,
            availability="In Stock",
        )

        self.assertEqual(product.sku, "AbC123#xyZ!9")

    def test_product_review_properties_reflect_related_reviews(self):
        category = Category.objects.create(name="Home")
        product = Product.objects.create(
            category=category,
            name="Lamp",
            regular_price="150",
            current_price="120",
            sku="",
            status=Product.Status.PUBLISHED,
            availability="In Stock",
        )

        ProductReview.objects.create(
            product=product,
            reviewer_name="Jessica Doe",
            reviewer_email="jessica@example.com",
            title="Excellent",
            body="Very good product.",
            rating=5,
            verified_purchase=True,
            review_date="2026-04-01",
        )
        ProductReview.objects.create(
            product=product,
            reviewer_name="Mike Ray",
            reviewer_email="mike@example.com",
            title="Solid",
            body="Worth the price.",
            rating=4,
            verified_purchase=False,
            review_date="2026-04-02",
        )

        self.assertEqual(product.review_count, 2)
        self.assertEqual(product.average_rating, 4.5)

    def test_product_review_initials_are_derived_from_name(self):
        category = Category.objects.create(name="Fitness")
        product = Product.objects.create(
            category=category,
            name="Yoga Mat",
            regular_price="90",
            current_price="70",
            sku="",
            status=Product.Status.PUBLISHED,
            availability="In Stock",
        )
        review = ProductReview.objects.create(
            product=product,
            reviewer_name="Sarah Lee",
            reviewer_email="sarah@example.com",
            title="Nice",
            body="Comfortable and durable.",
            rating=4,
            verified_purchase=True,
            review_date="2026-04-03",
        )

        self.assertEqual(review.reviewer_initials, "SL")


class ProductListPaginationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Pagination")
        self.user = get_user_model().objects.create_superuser(
            username="product-pagination-admin",
            email="product-pagination-admin@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        for index in range(21):
            Product.objects.create(
                category=self.category,
                name=f"Page Product {index}",
                regular_price="100",
                current_price="90",
                sku=f"NUBPAGE{index:05d}",
            )

    def test_product_list_shows_twenty_products_per_page_with_numbered_navigation(self):
        response = self.client.get(reverse("dashboard_product_list"))
        second_page = self.client.get(reverse("dashboard_product_list"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 20)
        self.assertContains(response, "product-pagination")
        self.assertContains(response, '?page=2')
        self.assertEqual(len(second_page.context["products"]), 1)

    def test_product_list_handles_an_invalid_page_without_losing_the_queryset(self):
        response = self.client.get(reverse("dashboard_product_list"), {"page": "not-a-page"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 20)

    def test_active_products_are_newest_first_before_inactive_products(self):
        Product.objects.all().delete()
        active_old = Product.objects.create(
            category=self.category,
            name="Active old",
            regular_price="100",
            current_price="90",
            sku="NUBACTIVEOLD",
            status=Product.Status.PUBLISHED,
        )
        active_new = Product.objects.create(
            category=self.category,
            name="Active new",
            regular_price="100",
            current_price="90",
            sku="NUBACTIVENEW",
            status=Product.Status.DRAFT,
        )
        inactive_old = Product.objects.create(
            category=self.category,
            name="Inactive old",
            regular_price="100",
            current_price="90",
            sku="NUBINACTIVEOLD",
            status=Product.Status.INACTIVE,
        )
        inactive_new = Product.objects.create(
            category=self.category,
            name="Inactive new",
            regular_price="100",
            current_price="90",
            sku="NUBINACTIVENEW",
            status=Product.Status.INACTIVE,
        )
        now = timezone.now()
        Product.objects.filter(pk=active_old.pk).update(created_at=now - timedelta(days=4))
        Product.objects.filter(pk=active_new.pk).update(created_at=now - timedelta(days=3))
        Product.objects.filter(pk=inactive_old.pk).update(created_at=now - timedelta(days=2))
        Product.objects.filter(pk=inactive_new.pk).update(created_at=now - timedelta(days=1))

        response = self.client.get(reverse("dashboard_product_list"))
        product_ids = [product.pk for product in response.context["products"]]

        self.assertLess(product_ids.index(active_new.pk), product_ids.index(active_old.pk))
        self.assertLess(product_ids.index(active_old.pk), product_ids.index(inactive_new.pk))
        self.assertLess(product_ids.index(inactive_new.pk), product_ids.index(inactive_old.pk))


class ProductListSummaryTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Product summary")
        self.user = get_user_model().objects.create_superuser(
            username="product-summary-admin",
            email="product-summary-admin@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.low_stock_product = self.create_product(
            "Low stock product",
            "NUBSUMMARY01",
            status=Product.Status.PUBLISHED,
            stock_quantity=5,
            low_stock_threshold=5,
        )
        self.out_of_stock_product = self.create_product(
            "Out of stock product",
            "NUBSUMMARY02",
            status=Product.Status.PUBLISHED,
            stock_quantity=0,
        )
        self.in_stock_product = self.create_product(
            "In stock product",
            "NUBSUMMARY03",
            stock_quantity=8,
            low_stock_threshold=5,
        )
        self.create_product(
            "Untracked product",
            "NUBSUMMARY04",
            track_stock=False,
            stock_quantity=0,
        )

    def create_product(self, name, sku, **kwargs):
        data = {
            "category": self.category,
            "name": name,
            "regular_price": "100",
            "current_price": "90",
            "sku": sku,
        }
        data.update(kwargs)
        return Product.objects.create(**data)

    def test_summary_uses_tracked_stock_counts_and_links_to_filtered_lists(self):
        response = self.client.get(reverse("dashboard_product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_total"], 4)
        self.assertEqual(response.context["product_published_total"], 2)
        self.assertEqual(response.context["product_low_stock_total"], 1)
        self.assertEqual(response.context["product_out_of_stock_total"], 1)
        self.assertContains(response, '?status=published')
        self.assertContains(response, '?stock_status=low')
        self.assertContains(response, '?stock_status=out')

    def test_summary_links_apply_the_matching_product_list_filters(self):
        published_response = self.client.get(reverse("dashboard_product_list"), {"status": "published"})
        low_stock_response = self.client.get(reverse("dashboard_product_list"), {"stock_status": "low"})
        out_of_stock_response = self.client.get(reverse("dashboard_product_list"), {"stock_status": "out"})

        self.assertQuerySetEqual(
            published_response.context["products"],
            [self.out_of_stock_product, self.low_stock_product],
            ordered=False,
        )
        self.assertQuerySetEqual(low_stock_response.context["products"], [self.low_stock_product])
        self.assertQuerySetEqual(out_of_stock_response.context["products"], [self.out_of_stock_product])


class ProductListFilterTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Filtered category")
        self.other_category = Category.objects.create(name="Other category")
        self.brand = Brand.objects.create(name="Filtered brand")
        self.other_brand = Brand.objects.create(name="Other brand")
        self.user = get_user_model().objects.create_superuser(
            username="product-filter-admin",
            email="product-filter-admin@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.matching_products = [
            self.create_product(
                f"Matching product {index}",
                f"NUBMATCH{index:04d}",
                category=self.category,
                brand=self.brand,
                status=Product.Status.PUBLISHED,
                stock_quantity=10,
                low_stock_threshold=5,
            )
            for index in range(21)
        ]
        self.low_stock_product = self.create_product(
            "Low stock product",
            "NUBLOWFILTER",
            category=self.category,
            brand=self.brand,
            stock_quantity=5,
            low_stock_threshold=5,
        )
        self.out_of_stock_product = self.create_product(
            "Out of stock product",
            "NUBOUTFILTER",
            category=self.category,
            brand=self.other_brand,
            stock_quantity=0,
        )
        self.untracked_product = self.create_product(
            "Untracked product",
            "NUBUNTRACKER",
            category=self.other_category,
            brand=self.brand,
            track_stock=False,
            stock_quantity=0,
        )

    def create_product(self, name, sku, **kwargs):
        return Product.objects.create(
            name=name,
            regular_price="100",
            current_price="90",
            sku=sku,
            **kwargs,
        )

    def test_combined_filters_and_pagination_keep_filter_values(self):
        filters = {
            "q": "Matching",
            "category": str(self.category.pk),
            "brand": str(self.brand.pk),
            "status": Product.Status.PUBLISHED,
            "stock_status": "in",
        }
        response = self.client.get(reverse("dashboard_product_list"), filters)
        second_page = self.client.get(reverse("dashboard_product_list"), {**filters, "page": 2})

        self.assertEqual(len(response.context["products"]), 20)
        self.assertEqual(len(second_page.context["products"]), 1)
        self.assertEqual(response.context["filters"], filters)
        self.assertContains(
            response,
            f"?q=Matching&amp;category={self.category.pk}&amp;brand={self.brand.pk}&amp;status=published&amp;stock_status=in&amp;page=2",
        )
        self.assertContains(response, 'value="Matching"')
        self.assertContains(response, f'value="{self.category.pk}" selected')
        self.assertContains(response, f'value="{self.brand.pk}" selected')

    def test_search_and_each_stock_filter_return_matching_products(self):
        sku_response = self.client.get(reverse("dashboard_product_list"), {"q": "NUBMATCH0000"})
        low_stock_response = self.client.get(reverse("dashboard_product_list"), {"stock_status": "low"})
        out_of_stock_response = self.client.get(reverse("dashboard_product_list"), {"stock_status": "out"})
        untracked_response = self.client.get(reverse("dashboard_product_list"), {"stock_status": "not_tracked"})

        self.assertQuerySetEqual(sku_response.context["products"], [self.matching_products[0]])
        self.assertQuerySetEqual(low_stock_response.context["products"], [self.low_stock_product])
        self.assertQuerySetEqual(out_of_stock_response.context["products"], [self.out_of_stock_product])
        self.assertQuerySetEqual(untracked_response.context["products"], [self.untracked_product])


class ProductListTableTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Table category")
        self.brand = Brand.objects.create(name="Table brand")
        self.user = get_user_model().objects.create_superuser(
            username="product-table-admin",
            email="product-table-admin@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.discounted_product = self.create_product(
            "A very long product name that should be truncated cleanly in the dashboard product table without changing its source value",
            "NUBTABLE0001",
            brand=self.brand,
            regular_price="100",
            current_price="80",
            stock_quantity=10,
            low_stock_threshold=5,
        )
        self.low_stock_product = self.create_product(
            "Low stock table product",
            "NUBTABLE0002",
            stock_quantity=5,
            low_stock_threshold=5,
        )
        self.out_of_stock_product = self.create_product(
            "Out of stock table product",
            "NUBTABLE0003",
            stock_quantity=0,
        )
        self.untracked_product = self.create_product(
            "Untracked table product",
            "NUBTABLE0004",
            track_stock=False,
            stock_quantity=0,
        )

    def create_product(self, name, sku, **kwargs):
        data = {
            "category": self.category,
            "name": name,
            "regular_price": "100",
            "current_price": "90",
            "sku": sku,
        }
        data.update(kwargs)
        return Product.objects.create(**data)

    def test_table_handles_missing_images_brands_discount_and_stock_states(self):
        response = self.client.get(reverse("dashboard_product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard-category-thumb--placeholder", count=4)
        self.assertContains(response, "No brand", count=3)
        self.assertContains(response, "20% off")
        self.assertContains(response, "In Stock: 10")
        self.assertContains(response, "Low Stock: 5")
        self.assertContains(response, "Out of Stock")
        self.assertContains(response, "Not Tracked")
        self.assertContains(response, 'style="min-width: 0; max-width: 18rem;"')

    def test_sort_headers_order_products_and_preserve_active_filters(self):
        response = self.client.get(
            reverse("dashboard_product_list"),
            {"q": "table product", "sort": "name"},
        )

        self.assertEqual(
            [product.name for product in response.context["products"]],
            [
                "Low stock table product",
                "Out of stock table product",
                "Untracked table product",
            ],
        )
        self.assertContains(response, "?q=table+product&amp;sort=-name")
        self.assertContains(response, "?q=table+product&amp;sort=price")


class ProductManagementActionTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Product actions")
        self.admin = get_user_model().objects.create_superuser(
            username="product-actions-admin",
            email="product-actions-admin@example.com",
            password="test-password",
        )
        self.product = self.create_product("Action product", "NUBACTION001")

    def create_product(self, name, sku, **kwargs):
        data = {
            "category": self.category,
            "name": name,
            "regular_price": "100",
            "current_price": "90",
            "sku": sku,
        }
        data.update(kwargs)
        return Product.objects.create(**data)

    @staticmethod
    def create_order_item(product):
        order = Order.objects.create(
            full_name="History Customer",
            phone="01700000000",
            address="History address",
            district="Dhaka",
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            product_slug=product.slug,
            product_sku=product.sku,
            quantity=1,
            unit_price=product.current_price,
            subtotal=product.current_price,
        )
        return order, order_item

    def assert_product_is_inactivated_by_delete(self, product):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboard_product_delete", args=[product.pk]),
            follow=True,
        )

        self.assertContains(
            response,
            "so it was made inactive instead of being permanently deleted.",
        )
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.INACTIVE)
        return product

    def test_bulk_status_action_requires_change_permission(self):
        viewer = get_user_model().objects.create_user(username="product-action-viewer", password="test-password")
        viewer.user_permissions.add(
            Permission.objects.get(codename="view_product", content_type__app_label="category")
        )
        self.client.force_login(viewer)

        response = self.client.post(
            reverse("dashboard_product_bulk_action"),
            {"action": "publish", "selected_products": [self.product.pk]},
        )

        self.assertRedirects(response, reverse("dashboard_product_list"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.DRAFT)

    def test_bulk_status_changes_and_safe_deletion(self):
        deletable_product = self.create_product("Deletable product", "NUBACTION002")
        protected_product = self.create_product("Protected product", "NUBACTION003", stock_quantity=3)
        StockTransaction.objects.create(
            product=protected_product,
            transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
            quantity_change=3,
            balance_after=3,
        )
        self.client.force_login(self.admin)

        self.client.post(
            reverse("dashboard_product_bulk_action"),
            {"action": "publish", "selected_products": [self.product.pk]},
        )
        self.client.post(
            reverse("dashboard_product_bulk_action"),
            {"action": "delete", "selected_products": [deletable_product.pk, protected_product.pk]},
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PUBLISHED)
        self.assertFalse(Product.objects.filter(pk=deletable_product.pk).exists())
        self.assertFalse(Product.objects.filter(pk=protected_product.pk).exists())

    def test_delete_with_opening_stock_permanently_deletes_product_and_its_image(self):
        product = self.create_product("Stock history product", "NUBACTIONSTOCK")
        StockTransaction.objects.create(
            product=product,
            transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
            quantity_change=1,
            balance_after=1,
        )
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            image = ProductImage.objects.create(
                product=product,
                image=SimpleUploadedFile("history-image.png", b"not-an-image", content_type="image/png"),
            )
            image_name = image.image.name
            storage = image.image.storage
            product_id = product.pk

            self.client.force_login(self.admin)
            response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]), follow=True)

            self.assertContains(response, '"Stock history product" deleted successfully.')
            self.assertFalse(Product.objects.filter(pk=product.pk).exists())
            self.assertFalse(StockTransaction.objects.filter(product_id=product_id).exists())
            self.assertFalse(ProductImage.objects.filter(pk=image.pk).exists())
            self.assertFalse(storage.exists(image_name))

    def test_manual_stock_adjustment_does_not_block_product_deletion(self):
        product = self.create_product("Manual adjustment product", "NUBACTIONMANUAL")
        StockTransaction.objects.create(
            product=product,
            transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT,
            quantity_change=2,
            balance_after=2,
            reference="Dashboard product edit",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]), follow=True)

        self.assertContains(response, '"Manual adjustment product" deleted successfully.')
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_stale_reversed_purchase_stock_rows_do_not_block_product_deletion(self):
        product = self.create_product("Stale purchase stock product", "NUBACTIONSTALE")
        stale_reference = "Purchase 999999999999 / item 1"
        StockTransaction.objects.create(
            product=product,
            transaction_type=StockTransaction.TransactionType.PURCHASE,
            quantity_change=1,
            balance_after=1,
            reference=stale_reference,
        )
        StockTransaction.objects.create(
            product=product,
            transaction_type=StockTransaction.TransactionType.PURCHASE_RETURN,
            quantity_change=-1,
            balance_after=0,
            reference=stale_reference,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]), follow=True)

        self.assertContains(response, '"Stale purchase stock product" deleted successfully.')
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_delete_with_purchase_history_inactivates_product_and_keeps_purchase_item(self):
        product = self.create_product("Purchase history product", "NUBACTIONPURCHASE")
        purchase = Purchase.objects.create()
        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            product_name=product.name,
            quantity=1,
            unit_price="90",
            subtotal="90",
        )

        self.assert_product_is_inactivated_by_delete(product)

        purchase_item.refresh_from_db()
        self.assertEqual(purchase_item.product_id, product.pk)

    def test_product_is_permanently_deleted_after_its_received_purchase_is_deleted(self):
        product = self.create_product("Deleted purchase product", "NUBACTIONPURCHASEDELETE")
        purchase = Purchase.objects.create()
        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            product_name=product.name,
            quantity=3,
            unit_price="90",
            subtotal="270",
        )
        sync_received_purchase_stock(purchase.pk, user=self.admin)
        self.client.force_login(self.admin)

        purchase_response = self.client.post(reverse("dashboard_purchase_delete", args=[purchase.pk]))

        self.assertEqual(purchase_response.status_code, 302)
        self.assertFalse(Purchase.objects.filter(pk=purchase.pk).exists())
        self.assertFalse(PurchaseItem.objects.filter(pk=purchase_item.pk).exists())
        self.assertFalse(PurchaseStockApplication.objects.filter(purchase_id=purchase.pk).exists())
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(StockTransaction.objects.filter(product=product).exists())

        product_response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]))

        self.assertEqual(product_response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_delete_with_order_history_inactivates_product_and_keeps_order_item(self):
        product = self.create_product("Order history product", "NUBACTIONORDER")
        _, order_item = self.create_order_item(product)

        self.assert_product_is_inactivated_by_delete(product)

        order_item.refresh_from_db()
        self.assertEqual(order_item.product_id, product.pk)

    def test_delete_with_sale_history_inactivates_product_and_keeps_sale_item(self):
        product = self.create_product("Sale history product", "NUBACTIONSALE")
        StockTransaction.objects.create(
            product=product,
            transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
            quantity_change=1,
            balance_after=1,
        )
        order, order_item = self.create_order_item(product)
        sale = Sale.objects.create(
            sale_id=Sale.build_sale_id(order),
            order=order,
            full_name=order.full_name,
            phone=order.phone,
            email=order.email,
            subtotal_amount=product.current_price,
            total_amount=product.current_price,
            item_count=1,
        )
        sale_item = SaleItem.objects.create(
            sale=sale,
            order_item=order_item,
            product=product,
            product_name=product.name,
            product_sku=product.sku,
            quantity=1,
            unit_price=product.current_price,
            subtotal=product.current_price,
        )

        self.assert_product_is_inactivated_by_delete(product)

        sale_item.refresh_from_db()
        self.assertEqual(sale_item.product_id, product.pk)

    def test_delete_without_transaction_history_permanently_deletes_product(self):
        product = self.create_product("Disposable product", "NUBACTIONDELETE")
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]), follow=True)

        self.assertContains(response, '"Disposable product" deleted successfully.')
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_inactive_product_without_history_is_permanently_deleted(self):
        product = self.create_product(
            "Inactive disposable product",
            "NUBACTIONINACTIVE",
            status=Product.Status.INACTIVE,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]), follow=True)

        self.assertContains(response, '"Inactive disposable product" deleted successfully.')
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_unrelated_order_audit_history_does_not_block_product_deletion(self):
        product = self.create_product("Audit-only product", "NUBACTIONAUDIT")
        audit_order = Order.objects.create(
            full_name="Audit Customer",
            phone="01700000001",
            address="Audit address",
            district="Dhaka",
        )
        OrderStatusHistory.objects.create(
            order=audit_order,
            status=Order.Status.PENDING,
            note="Unrelated audit entry.",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_delete", args=[product.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_duplicate_creates_a_draft_without_stock_or_related_history(self):
        source = self.create_product(
            "Duplicate source",
            "NUBACTION004",
            status=Product.Status.PUBLISHED,
            stock_quantity=7,
            low_stock_threshold=3,
            short_description="Reusable summary",
            full_description="Reusable detail",
        )
        StockTransaction.objects.create(
            product=source,
            transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
            quantity_change=7,
            balance_after=7,
        )
        ProductReview.objects.create(
            product=source,
            reviewer_name="Review user",
            title="Review title",
            body="Review body",
            rating=5,
            review_date="2026-01-01",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("dashboard_product_duplicate", args=[source.pk]))
        duplicate = Product.objects.exclude(pk__in=[self.product.pk, source.pk]).get()
        source.refresh_from_db()

        self.assertRedirects(response, reverse("dashboard_product_edit", args=[duplicate.pk]))
        self.assertEqual(duplicate.status, Product.Status.DRAFT)
        self.assertEqual(duplicate.stock_quantity, 0)
        self.assertEqual(duplicate.category, source.category)
        self.assertEqual(duplicate.current_price, source.current_price)
        self.assertNotEqual(duplicate.sku, source.sku)
        self.assertNotEqual(duplicate.slug, source.slug)
        self.assertFalse(duplicate.stock_transactions.exists())
        self.assertFalse(duplicate.reviews.exists())
        self.assertFalse(duplicate.images.exists())


class ProductStockWorkflowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Stock Category")
        self.user = get_user_model().objects.create_superuser(
            username="stock-admin", email="stock-admin@example.com", password="test-password"
        )
        self.client.force_login(self.user)

    def product_data(self, **overrides):
        data = {
            "category": self.category.pk,
            "name": "Stocked Product",
            "regular_price": "1200",
            "current_price": "999",
            "sku": "NUBSTOCK0000",
            "status": Product.Status.PUBLISHED,
            "availability": ProductForm.AVAILABILITY_IN_STOCK,
            "track_stock": "on",
            "stock_quantity": "0",
            "low_stock_threshold": "5",
            "short_description": "Stock test product",
            "full_description_html": "<p>Stock test product</p>",
        }
        data.update(overrides)
        return data

    def test_stock_status_uses_quantity_and_preserves_availability_when_not_tracked(self):
        tracked_product = Product.objects.create(
            category=self.category,
            name="Low Stock Product",
            regular_price="100",
            current_price="90",
            sku="NUBLOWSTOCK",
            stock_quantity=3,
            low_stock_threshold=5,
        )
        untracked_product = Product.objects.create(
            category=self.category,
            name="Untracked Product",
            regular_price="100",
            current_price="90",
            sku="NUBUNTRACK",
            track_stock=False,
            availability="Out of Stock",
        )

        self.assertEqual(tracked_product.stock_status, "low_stock")
        self.assertEqual(tracked_product.stock_status_label, "In Stock")
        self.assertEqual(tracked_product.availability, "In Stock")
        self.assertEqual(untracked_product.stock_status, "not_tracked")
        self.assertEqual(untracked_product.availability, "Out of Stock")

    def test_creating_product_with_opening_stock_records_transaction(self):
        response = self.client.post(
            reverse("dashboard_product_add"), self.product_data(stock_quantity="8")
        )

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name="Stocked Product")
        transaction = StockTransaction.objects.get(product=product)
        self.assertEqual(transaction.transaction_type, StockTransaction.TransactionType.OPENING_STOCK)
        self.assertEqual(transaction.quantity_change, 8)
        self.assertEqual(transaction.balance_after, 8)
        self.assertEqual(transaction.created_by, self.user)

    def test_editing_stock_records_only_one_manual_adjustment_when_quantity_changes(self):
        product = Product.objects.create(
            category=self.category,
            name="Stocked Product",
            regular_price="1200",
            current_price="999",
            sku="NUBSTOCK0000",
            stock_quantity=3,
        )
        edit_url = reverse("dashboard_product_edit", args=[product.pk])

        response = self.client.post(edit_url, self.product_data(stock_quantity="7"))
        self.assertEqual(response.status_code, 302)
        transaction = StockTransaction.objects.get(product=product)
        self.assertEqual(transaction.transaction_type, StockTransaction.TransactionType.MANUAL_ADJUSTMENT)
        self.assertEqual(transaction.quantity_change, 4)
        self.assertEqual(transaction.balance_after, 7)

        response = self.client.post(edit_url, self.product_data(stock_quantity="7"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockTransaction.objects.filter(product=product).count(), 1)

    def test_edit_page_can_reactivate_an_inactive_product(self):
        product = Product.objects.create(
            category=self.category,
            name="Inactive product",
            regular_price="1200",
            current_price="999",
            sku="NUBREACTIVATE",
            status=Product.Status.INACTIVE,
        )

        response = self.client.post(
            reverse("dashboard_product_edit", args=[product.pk]),
            self.product_data(name=product.name, sku=product.sku, status=Product.Status.PUBLISHED),
        )

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.PUBLISHED)


class ProductImageDerivativeTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = self.settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.category = Category.objects.create(name="Derivative Category")
        self.product = Product.objects.create(
            category=self.category,
            name="Derivative Product",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBDERIV001",
        )

    @staticmethod
    def uploaded_image(width=800, height=600):
        output = BytesIO()
        Image.new("RGB", (width, height), "#ff5c00").save(output, format="PNG")
        return SimpleUploadedFile("product.png", output.getvalue(), content_type="image/png")

    def test_creates_one_optimized_webp_without_replacing_original(self):
        product_image = ProductImage.objects.create(product=self.product, image=self.uploaded_image(1200, 900))
        storage = product_image.image.storage
        optimized_name = product_image_optimized_name(product_image.image.name)
        card_name = product_image_legacy_derivative_name(product_image.image.name, "card")
        detail_name = product_image_legacy_derivative_name(product_image.image.name, "detail")

        self.assertTrue(storage.exists(product_image.image.name))
        self.assertTrue(storage.exists(optimized_name))
        self.assertFalse(storage.exists(card_name))
        self.assertFalse(storage.exists(detail_name))
        self.assertIn(".optimized.webp", product_image.optimized_url)
        self.assertEqual(product_image.card_url, product_image.optimized_url)
        self.assertEqual(product_image.detail_url, product_image.optimized_url)

        with storage.open(optimized_name, "rb") as optimized_file:
            with Image.open(optimized_file) as optimized_image:
                self.assertLessEqual(optimized_image.width, 800)
                self.assertLessEqual(optimized_image.height, 800)

    def test_optimized_url_falls_back_to_original_when_derivative_is_missing(self):
        product_image = ProductImage.objects.create(product=self.product, image=self.uploaded_image(120, 80))
        storage = product_image.image.storage
        storage.delete(product_image_optimized_name(product_image.image.name))

        self.assertEqual(product_image.optimized_url, product_image.image.url)
        self.assertEqual(product_image.card_url, product_image.image.url)
        self.assertEqual(product_image.detail_url, product_image.image.url)

    def test_deleting_image_removes_original_and_optimized_derivative(self):
        product_image = ProductImage.objects.create(product=self.product, image=self.uploaded_image())
        storage = product_image.image.storage
        image_name = product_image.image.name
        optimized_name = product_image_optimized_name(image_name)

        product_image.delete()

        self.assertFalse(storage.exists(image_name))
        self.assertFalse(storage.exists(optimized_name))

    def test_legacy_cleanup_only_removes_known_legacy_derivatives(self):
        product_image = ProductImage.objects.create(product=self.product, image=self.uploaded_image())
        storage = product_image.image.storage
        image_name = product_image.image.name
        optimized_name = product_image_optimized_name(image_name)
        card_name = product_image_legacy_derivative_name(image_name, "card")
        detail_name = product_image_legacy_derivative_name(image_name, "detail")
        storage.save(card_name, ContentFile(b"legacy card"))
        storage.save(detail_name, ContentFile(b"legacy detail"))

        dry_run_output = StringIO()
        call_command("cleanup_legacy_product_image_derivatives", stdout=dry_run_output)

        self.assertIn("planned removal of 2 legacy derivatives", dry_run_output.getvalue())
        self.assertTrue(storage.exists(image_name))
        self.assertTrue(storage.exists(optimized_name))
        self.assertTrue(storage.exists(card_name))
        self.assertTrue(storage.exists(detail_name))

        call_command("cleanup_legacy_product_image_derivatives", "--write", stdout=StringIO())

        self.assertTrue(storage.exists(image_name))
        self.assertTrue(storage.exists(optimized_name))
        self.assertFalse(storage.exists(card_name))
        self.assertFalse(storage.exists(detail_name))

    def test_rebuild_command_creates_missing_optimized_derivative(self):
        product_image = ProductImage.objects.create(product=self.product, image=self.uploaded_image())
        storage = product_image.image.storage
        optimized_name = product_image_optimized_name(product_image.image.name)
        storage.delete(optimized_name)

        output = StringIO()
        call_command("rebuild_product_image_derivatives", stdout=output)

        self.assertIn("generated 1 optimized derivatives", output.getvalue())
        self.assertTrue(storage.exists(optimized_name))
