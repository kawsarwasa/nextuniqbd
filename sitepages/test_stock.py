import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from category.models import Category, Product, StockTransaction

from .models import AbandonedCheckout, Order, OrderItem, OrderStockApplication
from .order_stock import sync_packed_order_stock


User = get_user_model()


class OrderStockIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="order-stock-admin",
            email="order-stock-admin@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Order Stock")
        self.product = Product.objects.create(
            category=self.category,
            name="Order Stock Product",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBORDERSTK",
            stock_quantity=10,
            status=Product.Status.PUBLISHED,
        )

    def create_order(self, quantity, *, product=None):
        product = product or self.product
        order = Order.objects.create(
            full_name="Stock Buyer",
            phone="01700000000",
            address="Dhaka",
            district="Dhaka",
            subtotal_amount="90.00",
            total_amount="150.00",
            item_count=quantity,
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            product_slug=product.slug,
            product_sku=product.sku,
            quantity=quantity,
            unit_price="90.00",
            subtotal=str(90 * quantity),
        )
        return order

    def confirm(self, order):
        self.client.force_login(self.user)
        return self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            {"status": Order.Status.PACKED},
        )

    def test_confirmed_order_deducts_stock_once(self):
        order = self.create_order(3)

        self.assertEqual(self.confirm(order).status_code, 302)
        sync_packed_order_stock(order.pk, user=self.user)
        self.product.refresh_from_db()

        self.assertEqual(self.product.stock_quantity, 7)
        transactions = list(StockTransaction.objects.filter(product=self.product).order_by("id"))
        self.assertEqual([item.quantity_change for item in transactions], [-3])
        self.assertEqual(transactions[0].transaction_type, StockTransaction.TransactionType.SALE)
        self.assertEqual(OrderStockApplication.objects.get(order=order).applied_quantity, 3)

    def test_insufficient_stock_rolls_back_the_entire_confirmation(self):
        self.product.stock_quantity = 2
        self.product.save(update_fields=["stock_quantity", "availability", "updated_at"])
        order = self.create_order(3)

        response = self.confirm(order)
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock_quantity, 2)
        self.assertFalse(StockTransaction.objects.filter(product=self.product).exists())

    def test_cancelling_confirmed_order_restores_stock_once(self):
        order = self.create_order(3)
        self.confirm(order)

        response = self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            {"status": Order.Status.CANCELLED, "note": "Customer cancelled."},
        )
        self.assertEqual(response.status_code, 302)
        self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            {"status": Order.Status.CANCELLED, "note": "Customer cancelled."},
        )
        self.product.refresh_from_db()

        self.assertEqual(self.product.stock_quantity, 10)
        transactions = list(StockTransaction.objects.filter(product=self.product).order_by("id"))
        self.assertEqual([item.quantity_change for item in transactions], [-3, 3])
        self.assertEqual(transactions[-1].transaction_type, StockTransaction.TransactionType.ORDER_CANCELLATION)

    def test_confirmed_order_item_quantity_changes_apply_only_the_difference(self):
        order = self.create_order(3)
        self.confirm(order)
        item = order.items.get()
        item.quantity = 5
        item.save()

        sync_packed_order_stock(order.pk, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

        item.quantity = 2
        item.save()
        sync_packed_order_stock(order.pk, user=self.user)
        self.product.refresh_from_db()
        quantities = list(
            StockTransaction.objects.filter(product=self.product).order_by("id").values_list("quantity_change", flat=True)
        )
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(quantities, [-3, -2, 3])

    def test_cart_rejects_out_of_stock_and_excess_quantities_but_allows_untracked_products(self):
        self.product.stock_quantity = 2
        self.product.save(update_fields=["stock_quantity", "availability", "updated_at"])

        response = self.client.post(
            reverse("cart_add"), json.dumps({"product_id": self.product.pk, "quantity": 3}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse("cart_add"), json.dumps({"product_id": self.product.pk, "quantity": 2}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("cart_update"), json.dumps({"product_id": self.product.pk, "quantity": 3}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        self.product.track_stock = False
        self.product.save(update_fields=["track_stock", "availability", "updated_at"])
        response = self.client.post(
            reverse("cart_update"), json.dumps({"product_id": self.product.pk, "quantity": 8}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

    def test_checkout_rechecks_stock_before_creating_pending_order(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 2}
        session.save()
        self.product.stock_quantity = 1
        self.product.save(update_fields=["stock_quantity", "availability", "updated_at"])

        response = self.client.post(
            reverse("frontend_checkout"),
            {
                "full_name": "Buyer",
                "phone": "01700000000",
                "email": "",
                "address": "Dhaka",
                "district": "Dhaka",
                "thana": "",
                "postal": "",
                "order_notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insufficient stock for Order Stock Product. Only 1 available.")
        self.assertFalse(Order.objects.exists())

    def test_competing_confirmations_cannot_oversell_final_units(self):
        self.product.stock_quantity = 5
        self.product.save(update_fields=["stock_quantity", "availability", "updated_at"])
        first_order = self.create_order(3)
        second_order = self.create_order(3)

        with transaction.atomic():
            first_order.status = Order.Status.PACKED
            first_order.save(update_fields=["status", "updated_at"])
            sync_packed_order_stock(first_order.pk, user=self.user)
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                second_order.status = Order.Status.PACKED
                second_order.save(update_fields=["status", "updated_at"])
                sync_packed_order_stock(second_order.pk, user=self.user)

        self.product.refresh_from_db()
        second_order.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 2)
        self.assertEqual(second_order.status, Order.Status.PENDING)

    def test_abandoned_checkout_never_changes_stock(self):
        checkout = AbandonedCheckout.objects.create(
            session_key="stock-test",
            cart_items=[{"product_id": self.product.pk, "quantity": 4}],
        )
        checkout.status = AbandonedCheckout.Status.CANCELLED
        checkout.save(update_fields=["status", "updated_at"])
        checkout.delete()
        self.product.refresh_from_db()

        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(StockTransaction.objects.filter(product=self.product).exists())

    def test_tracking_disabled_product_is_not_deducted_on_confirmation(self):
        self.product.track_stock = False
        self.product.save(update_fields=["track_stock", "availability", "updated_at"])
        order = self.create_order(4)

        self.confirm(order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(StockTransaction.objects.filter(product=self.product).exists())
