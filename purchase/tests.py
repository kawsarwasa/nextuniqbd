from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from category.models import Brand, Category, Product, StockTransaction

from .models import Purchase, PurchaseItem, PurchaseStockApplication
from .services import sync_received_purchase_stock


User = get_user_model()


class PurchaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="purchase-admin@example.com",
            email="purchase-admin@example.com",
            password="Admin@100%",
        )
        self.category = Category.objects.create(name="Electronics")
        self.brand = Brand.objects.create(name="Acme")
        self.product_one = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Keyboard",
            regular_price="700.00",
            current_price="500.00",
            sku="KEY00001",
        )
        self.product_two = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Mouse",
            regular_price="300.00",
            current_price="200.00",
            sku="MOU00001",
        )

    def test_purchase_generates_12_digit_id(self):
        purchase = Purchase.objects.create()

        self.assertEqual(len(purchase.purchase_id), 12)
        self.assertTrue(purchase.purchase_id.isdigit())
        self.assertIsNone(purchase.category)
        self.assertIsNone(purchase.brand)

    def test_dashboard_purchase_add_renders_product_search_options(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard_purchase_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "purchase-product-options")
        self.assertContains(response, "Keyboard")
        self.assertContains(response, "Mouse")
        self.assertContains(response, "dashboard-combobox")
        self.assertContains(response, "dashboard-combobox__dropdown")
        self.assertContains(response, "js-searchable-select")
        self.assertContains(response, "Search product")
        self.assertContains(response, "purchase-product-select")
        self.assertContains(response, "productPrices")

    def test_dashboard_purchase_create_saves_multiple_items_and_total(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("dashboard_purchase_add"),
            data={
                "supplier_name": "Main Supplier",
                "supplier_phone": "01700000000",
                "supplier_address": "Dhaka",
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product_one.pk),
                "items-0-quantity": "2",
                "items-0-unit_price": "500",
                "items-1-product": str(self.product_two.pk),
                "items-1-quantity": "3",
                "items-1-unit_price": "200",
            },
        )

        self.assertEqual(response.status_code, 302)
        purchase = Purchase.objects.prefetch_related("items").latest("id")
        self.assertEqual(purchase.items.count(), 2)
        self.assertEqual(float(purchase.total_amount), 1600.0)
        self.assertIsNone(purchase.category)
        self.assertIsNone(purchase.brand)
        self.assertEqual(purchase.items.order_by("id").first().product, self.product_one)
        self.assertEqual(purchase.items.order_by("id").first().product_name, "Keyboard")
        self.product_one.refresh_from_db()
        self.product_two.refresh_from_db()
        self.assertEqual(self.product_one.stock_quantity, 2)
        self.assertEqual(self.product_two.stock_quantity, 3)
        self.assertEqual(StockTransaction.objects.filter(transaction_type=StockTransaction.TransactionType.PURCHASE).count(), 2)

    def test_dashboard_purchase_detail_displays_purchase_lines(self):
        self.client.force_login(self.user)
        purchase = Purchase.objects.create(supplier_name="Main Supplier", supplier_phone="01700000000")
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product_one,
            product_name=self.product_one.name,
            quantity=2,
            unit_price="500.00",
        )
        purchase.refresh_total()

        response = self.client.get(reverse("dashboard_purchase_detail", args=[purchase.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, purchase.purchase_id)
        self.assertContains(response, "Main Supplier")
        self.assertContains(response, "Keyboard")
        self.assertContains(response, "500.00")

    def test_dashboard_purchase_edit_allows_deleting_one_item_with_blank_extra_row(self):
        self.client.force_login(self.user)
        purchase = Purchase.objects.create(supplier_name="Main Supplier")
        first_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product_one,
            product_name=self.product_one.name,
            quantity=2,
            unit_price="500.00",
        )
        second_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product_two,
            product_name=self.product_two.name,
            quantity=3,
            unit_price="200.00",
        )
        purchase.refresh_total()

        response = self.client.post(
            reverse("dashboard_purchase_edit", args=[purchase.pk]),
            data={
                "supplier_name": "Main Supplier",
                "supplier_phone": "",
                "supplier_address": "",
                "items-TOTAL_FORMS": "3",
                "items-INITIAL_FORMS": "2",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": str(first_item.pk),
                "items-0-product": str(self.product_one.pk),
                "items-0-quantity": "2",
                "items-0-unit_price": "500.00",
                "items-1-id": str(second_item.pk),
                "items-1-product": str(self.product_two.pk),
                "items-1-quantity": "3",
                "items-1-unit_price": "200.00",
                "items-1-DELETE": "on",
                "items-2-id": "",
                "items-2-product": "",
                "items-2-quantity": "",
                "items-2-unit_price": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        purchase.refresh_from_db()
        remaining_items = list(purchase.items.order_by("id"))
        self.assertEqual(len(remaining_items), 1)
        self.assertEqual(remaining_items[0].product, self.product_one)
        self.assertEqual(float(purchase.total_amount), 1000.0)

    def test_dashboard_purchase_edit_does_not_render_an_extra_blank_item(self):
        self.client.force_login(self.user)
        purchase = Purchase.objects.create(supplier_name="Main Supplier")
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product_one,
            product_name=self.product_one.name,
            quantity=2,
            unit_price="500.00",
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product_two,
            product_name=self.product_two.name,
            quantity=3,
            unit_price="200.00",
        )

        response = self.client.get(reverse("dashboard_purchase_edit", args=[purchase.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["item_formset"].forms), 2)

    def test_dashboard_purchase_list_paginates_thirty_records_per_page(self):
        for index in range(31):
            Purchase.objects.create(supplier_name=f"Supplier {index}")
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard_purchase_list"))
        second_page = self.client.get(reverse("dashboard_purchase_list"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["purchases"]), 30)
        self.assertContains(response, "dashboard-pagination")
        self.assertEqual(len(second_page.context["purchases"]), 1)


class PurchaseStockIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="purchase-stock-admin",
            email="purchase-stock-admin@example.com",
            password="Admin@100%",
        )
        self.category = Category.objects.create(name="Purchase Stock")
        self.product_one = Product.objects.create(
            category=self.category,
            name="Stock Product One",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBPURCHASE1",
        )
        self.product_two = Product.objects.create(
            category=self.category,
            name="Stock Product Two",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBPURCHASE2",
        )

    def create_received_purchase(self, *lines):
        purchase = Purchase.objects.create(supplier_name="Stock Supplier")
        for product, quantity in lines:
            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                product_name=product.name,
                quantity=quantity,
                unit_price="50.00",
            )
        sync_received_purchase_stock(purchase.pk, user=self.user)
        return purchase

    def test_received_purchase_increases_stock_and_records_purchase_transaction(self):
        purchase = self.create_received_purchase((self.product_one, 10))

        self.product_one.refresh_from_db()
        transaction = StockTransaction.objects.get(product=self.product_one)
        self.assertEqual(self.product_one.stock_quantity, 10)
        self.assertEqual(transaction.transaction_type, StockTransaction.TransactionType.PURCHASE)
        self.assertEqual(transaction.quantity_change, 10)
        self.assertEqual(transaction.balance_after, 10)
        self.assertIn(purchase.purchase_id, transaction.reference)
        self.assertEqual(transaction.created_by, self.user)

    def test_resaving_received_purchase_does_not_add_stock_twice(self):
        purchase = self.create_received_purchase((self.product_one, 10))

        sync_received_purchase_stock(purchase.pk, user=self.user)
        self.product_one.refresh_from_db()

        self.assertEqual(self.product_one.stock_quantity, 10)
        self.assertEqual(StockTransaction.objects.filter(product=self.product_one).count(), 1)
        self.assertEqual(PurchaseStockApplication.objects.get(purchase=purchase).applied_quantity, 10)

    def test_editing_received_quantity_applies_only_the_difference(self):
        purchase = self.create_received_purchase((self.product_one, 10))
        item = purchase.items.get()
        item.quantity = 14
        item.save()

        sync_received_purchase_stock(purchase.pk, user=self.user)
        self.product_one.refresh_from_db()
        quantities = list(
            StockTransaction.objects.filter(product=self.product_one)
            .order_by("id")
            .values_list("quantity_change", flat=True)
        )

        self.assertEqual(self.product_one.stock_quantity, 14)
        self.assertEqual(quantities, [10, 4])

    def test_deleting_received_purchase_reverses_stock_once(self):
        purchase = self.create_received_purchase((self.product_one, 10), (self.product_two, 4))
        self.client.force_login(self.user)

        response = self.client.post(reverse("dashboard_purchase_delete", args=[purchase.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Purchase.objects.filter(pk=purchase.pk).exists())
        self.product_one.refresh_from_db()
        self.product_two.refresh_from_db()
        transactions = list(StockTransaction.objects.filter(product=self.product_one).order_by("id"))
        second_product_transactions = list(StockTransaction.objects.filter(product=self.product_two).order_by("id"))
        self.assertEqual(self.product_one.stock_quantity, 0)
        self.assertEqual(self.product_two.stock_quantity, 0)
        self.assertEqual([transaction.quantity_change for transaction in transactions], [10, -10])
        self.assertEqual([transaction.quantity_change for transaction in second_product_transactions], [4, -4])
        self.assertEqual(transactions[-1].transaction_type, StockTransaction.TransactionType.PURCHASE_RETURN)

    def test_tracking_disabled_product_is_ignored(self):
        self.product_one.track_stock = False
        self.product_one.availability = "In Stock"
        self.product_one.save(update_fields=["track_stock", "availability"])

        purchase = self.create_received_purchase((self.product_one, 10))
        self.product_one.refresh_from_db()

        self.assertEqual(self.product_one.stock_quantity, 0)
        self.assertFalse(StockTransaction.objects.filter(product=self.product_one).exists())
        self.assertFalse(PurchaseStockApplication.objects.filter(purchase=purchase).exists())

    def test_multiple_purchase_items_apply_stock_to_each_product(self):
        self.create_received_purchase((self.product_one, 2), (self.product_two, 3))
        self.product_one.refresh_from_db()
        self.product_two.refresh_from_db()

        self.assertEqual(self.product_one.stock_quantity, 2)
        self.assertEqual(self.product_two.stock_quantity, 3)
        self.assertEqual(StockTransaction.objects.filter(transaction_type=StockTransaction.TransactionType.PURCHASE).count(), 2)
