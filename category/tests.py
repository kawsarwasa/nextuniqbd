from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from .forms import ProductForm
from .models import Brand, Category, Product, ProductReview, StockTransaction


class ProductFormTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics")
        self.brand = Brand.objects.create(name="Acme")

    def test_new_product_form_prefills_visible_defaults(self):
        form = ProductForm()

        self.assertEqual(form.fields["status"].initial, Product.Status.PUBLISHED)
        self.assertEqual(form.fields["availability"].initial, ProductForm.AVAILABILITY_IN_STOCK)
        self.assertEqual(form.fields["sku"].initial, Product.SKU_PREFIX)
        self.assertFalse(form.fields["sku"].disabled)
        self.assertTrue(form.fields["sku"].required)

    def test_form_accepts_manual_sku_and_normalizes_availability(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "nubabc123xyz",
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
        self.assertEqual(form.cleaned_data["sku"], "NUBABC123XYZ")

    def test_form_requires_nine_manual_sku_characters_after_prefix(self):
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": Product.SKU_PREFIX,
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
        self.assertIn("sku", form.errors)

    def test_form_rejects_duplicate_manual_sku_on_create(self):
        Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="NUBABC123XYZ",
            status=Product.Status.PUBLISHED,
            availability=ProductForm.AVAILABILITY_IN_STOCK,
        )
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
                "stock_quantity": "0",
                "low_stock_threshold": "5",
                "short_description": "Compact mouse",
                "full_description_html": "<p>Compact mouse</p>",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("sku", form.errors)

    def test_edit_form_allows_manual_sku_update(self):
        product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Existing Mouse",
            regular_price="1200",
            current_price="999",
            sku="NUBABC123XYZ",
            status=Product.Status.PUBLISHED,
            availability=ProductForm.AVAILABILITY_IN_STOCK,
        )
        form = ProductForm(
            data={
                "category": self.category.pk,
                "name": "Wireless Mouse",
                "regular_price": "1200",
                "current_price": "999",
                "sku": "NUBDEF456UVW",
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
        self.assertEqual(form.cleaned_data["sku"], "NUBDEF456UVW")

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

        self.assertRegex(product.sku, r"^NUB[A-Z0-9]{9}$")

        another_product = Product.objects.create(
            category=category,
            name="Notebook Pro",
            regular_price="200",
            current_price="150",
            sku="",
            status=Product.Status.DRAFT,
            availability="",
        )

        self.assertRegex(another_product.sku, r"^NUB[A-Z0-9]{9}$")
        self.assertNotEqual(product.sku, another_product.sku)

    def test_product_save_replaces_invalid_manual_sku(self):
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

        self.assertRegex(product.sku, r"^NUB[A-Z0-9]{9}$")

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
        for index in range(11):
            Product.objects.create(
                category=self.category,
                name=f"Page Product {index}",
                regular_price="100",
                current_price="90",
                sku=f"NUBPAGE{index:05d}",
            )

    def test_product_list_shows_ten_products_per_page_with_numbered_navigation(self):
        response = self.client.get(reverse("dashboard_product_list"))
        second_page = self.client.get(reverse("dashboard_product_list"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 10)
        self.assertContains(response, "product-pagination")
        self.assertContains(response, '?page=2')
        self.assertEqual(len(second_page.context["products"]), 1)


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
            for index in range(11)
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

        self.assertEqual(len(response.context["products"]), 10)
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
        self.assertTrue(Product.objects.filter(pk=protected_product.pk).exists())

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
