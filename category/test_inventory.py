from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from purchase.models import Purchase, PurchaseItem

from .models import Category, Product, StockTransaction


User = get_user_model()


class InventoryDashboardTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Inventory")
        self.product = Product.objects.create(
            category=self.category,
            name="Inventory Product",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBINVENTRY",
            stock_quantity=4,
        )
        purchase = Purchase.objects.create()
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            product_name=self.product.name,
            quantity=4,
            unit_price="50.00",
        )
        StockTransaction.objects.create(
            product=self.product,
            transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
            quantity_change=5,
            balance_after=5,
        )
        StockTransaction.objects.create(
            product=self.product,
            transaction_type=StockTransaction.TransactionType.SALE,
            quantity_change=-1,
            balance_after=4,
        )
        self.admin = User.objects.create_superuser(
            username="inventory-admin", email="inventory-admin@example.com", password="test-password"
        )

    def test_inventory_report_shows_stock_metrics_and_latest_purchase_cost_to_authorized_user(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard_inventory_report"), {"q": "Inventory"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory Product")
        self.assertContains(response, "Latest Purchase Cost")
        self.assertContains(response, "50.00")
        self.assertContains(response, "200.00")
        product = response.context["products"][0]
        self.assertEqual(product.total_purchased, 0)
        self.assertEqual(product.total_sold, 1)

    def test_inventory_report_hides_cost_from_product_viewer_without_purchase_permission(self):
        viewer = User.objects.create_user(username="inventory-viewer", password="test-password")
        viewer.user_permissions.add(Permission.objects.get(codename="view_product", content_type__app_label="category"))
        self.client.force_login(viewer)

        response = self.client.get(reverse("dashboard_inventory_report"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Latest Purchase Cost")
        self.assertNotContains(response, "200.00")

    def test_customer_without_product_permission_cannot_access_inventory_pages(self):
        customer = User.objects.create_user(username="inventory-customer", password="test-password")
        self.client.force_login(customer)

        response = self.client.get(reverse("dashboard_inventory_report"))

        self.assertIn(response.status_code, (302, 403))

    def test_stock_history_filters_and_product_detail_totals_use_transactions(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboard_stock_history"),
            {"product": self.product.pk, "transaction_type": StockTransaction.TransactionType.SALE},
        )
        detail_response = self.client.get(reverse("dashboard_product_detail", args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sale")
        self.assertEqual(len(response.context["transactions"]), 1)
        self.assertEqual(detail_response.context["stock_totals"]["sold"], 1)
        self.assertContains(detail_response, "Total Purchased")

    def test_dashboard_shows_stock_summary_and_low_stock_table(self):
        self.product.low_stock_threshold = 5
        self.product.save(update_fields=["low_stock_threshold", "availability", "updated_at"])
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Stock Quantity")
        self.assertContains(response, "Low Stock Products")
        self.assertContains(response, "Inventory Product")
