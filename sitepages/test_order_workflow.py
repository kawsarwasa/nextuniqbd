from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from category.models import Category, Product, StockTransaction

from .models import Order, OrderItem, OrderStatusHistory, Sale
from .forms import OrderStatusForm
from .order_status import change_order_status
from .order_tracking import build_order_tracking_context, get_order_tracking_queryset


User = get_user_model()


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="workflow-manager",
            email="workflow-manager@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Order Workflow")
        self.product = Product.objects.create(
            category=category,
            name="Workflow Product",
            regular_price="100.00",
            current_price="90.00",
            sku="NUBWORKFLOW",
            stock_quantity=10,
            status=Product.Status.PUBLISHED,
        )

    def create_order(self):
        order = Order.objects.create(
            full_name="Workflow Customer",
            phone="01700000000",
            address="Dhaka",
            district="Dhaka",
            subtotal_amount="90.00",
            total_amount="150.00",
            item_count=2,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            product_sku=self.product.sku,
            quantity=2,
            unit_price="90.00",
            subtotal="180.00",
        )
        return order

    def transition(self, order, status, note=""):
        return change_order_status(
            order=order,
            new_status=status,
            changed_by=self.user,
            note=note,
            source=OrderStatusHistory.Source.DASHBOARD,
        )

    def test_complete_workflow_creates_one_history_entry_per_real_transition(self):
        order = self.create_order()
        for status in (Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.DELIVERED):
            self.transition(order, status)
            self.assertFalse(Sale.objects.filter(order=order).exists())
        self.transition(order, Order.Status.CONFIRMED)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(
            list(order.status_history.values_list("status", flat=True)),
            [
                Order.Status.PENDING,
                Order.Status.PACKED,
                Order.Status.SHIPPED,
                Order.Status.DELIVERED,
                Order.Status.CONFIRMED,
            ],
        )
        self.assertEqual(StockTransaction.objects.filter(product=self.product).count(), 1)
        self.assertEqual(Sale.objects.filter(order=order).count(), 1)
        self.assertFalse(self.transition(order, Order.Status.CONFIRMED).changed)
        self.assertEqual(Sale.objects.filter(order=order).count(), 1)
        with self.assertRaises(ValidationError):
            self.transition(order, Order.Status.CANCELLED, "Cannot cancel a confirmed order.")
        with self.assertRaises(ValidationError):
            self.transition(order, Order.Status.RETURNED, "Cannot return a confirmed order.")

    def test_invalid_status_skipping_is_rejected(self):
        order = self.create_order()

        with self.assertRaises(ValidationError):
            self.transition(order, Order.Status.CONFIRMED)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.status_history.count(), 1)

    def test_processing_is_not_available_in_forms_or_tracking_steps(self):
        order = self.create_order()
        form = OrderStatusForm(order=order)
        tracking_order = get_order_tracking_queryset().get(pk=order.pk)
        tracking = build_order_tracking_context(tracking_order)

        self.assertNotIn("processing", [value for value, _label in form.fields["status"].choices])
        self.assertNotIn("Processing", [step["label"] for step in tracking["steps"]])

    def test_pending_cancellation_does_not_affect_stock(self):
        order = self.create_order()

        self.transition(order, Order.Status.CANCELLED, "Customer changed their mind.")

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(StockTransaction.objects.filter(product=self.product).exists())

    def test_packed_cancellation_and_delivered_return_restore_stock_once(self):
        cancelled_order = self.create_order()
        self.transition(cancelled_order, Order.Status.PACKED)
        self.transition(cancelled_order, Order.Status.CANCELLED, "Customer cancelled.")

        returned_order = self.create_order()
        for status in (
            Order.Status.PACKED,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ):
            self.transition(returned_order, status)
        self.transition(returned_order, Order.Status.RETURNED, "Goods received back.")

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        transactions = list(StockTransaction.objects.filter(product=self.product).order_by("id"))
        self.assertEqual([item.quantity_change for item in transactions], [-2, 2, -2, 2])
        self.assertEqual(transactions[-1].transaction_type, StockTransaction.TransactionType.SALE_RETURN)

        with self.assertRaises(ValidationError):
            self.transition(returned_order, Order.Status.CANCELLED, "Cannot cancel returned order.")

    def test_tracking_uses_recorded_status_dates_and_keeps_return_marker(self):
        order = self.create_order()
        for status in (
            Order.Status.PACKED,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ):
            self.transition(order, status)
        self.transition(order, Order.Status.RETURNED, "Returned to stock.")

        tracking_order = get_order_tracking_queryset().get(pk=order.pk)
        tracking = build_order_tracking_context(tracking_order)

        self.assertTrue(tracking["is_returned"])
        self.assertNotEqual(tracking["steps"][-2]["recorded_at_display"], "Not recorded")
        self.assertNotEqual(tracking["returned_recorded_at_display"], "Not recorded")
