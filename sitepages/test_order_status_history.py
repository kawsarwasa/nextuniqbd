from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Order, OrderStatusHistory
from .order_status import change_order_status


User = get_user_model()


class OrderStatusHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="order-history-manager",
            email="order-history-manager@example.com",
            password="test-password",
        )

    def create_order(self):
        return Order.objects.create(
            full_name="Order History Customer",
            phone="01700000000",
            email="customer@example.com",
            address="Dhaka",
            district="Dhaka",
            subtotal_amount="100.00",
            total_amount="160.00",
            item_count=1,
        )

    def test_order_creation_records_the_actual_initial_status_and_timestamp(self):
        order = self.create_order()

        history = OrderStatusHistory.objects.get(order=order)
        self.assertEqual(history.status, Order.Status.PENDING)
        self.assertEqual(history.changed_at, order.created_at)
        self.assertEqual(history.source, OrderStatusHistory.Source.SYSTEM)

    def test_status_change_records_the_user_timestamp_note_and_source(self):
        order = self.create_order()

        result = change_order_status(
            order=order,
            new_status=Order.Status.PACKED,
            changed_by=self.user,
            note="Payment verified by phone.",
            source=OrderStatusHistory.Source.DASHBOARD,
        )

        history = OrderStatusHistory.objects.get(order=order, status=Order.Status.PACKED)
        self.assertTrue(result.changed)
        self.assertEqual(result.previous_status, Order.Status.PENDING)
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.previous_status, Order.Status.PENDING)
        self.assertEqual(history.note, "Payment verified by phone.")
        self.assertEqual(history.source, OrderStatusHistory.Source.DASHBOARD)
        self.assertIsNotNone(history.changed_at)

    def test_unchanged_status_does_not_create_a_duplicate_history_record(self):
        order = self.create_order()

        first_change = change_order_status(
            order=order,
            new_status=Order.Status.PACKED,
            changed_by=self.user,
            source=OrderStatusHistory.Source.DASHBOARD,
        )
        repeated_change = change_order_status(
            order=order,
            new_status=Order.Status.PACKED,
            changed_by=self.user,
            source=OrderStatusHistory.Source.DASHBOARD,
        )

        self.assertTrue(first_change.changed)
        self.assertFalse(repeated_change.changed)
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 2)

    def test_direct_model_status_change_is_recorded_once_as_a_system_change(self):
        order = self.create_order()

        order.status = Order.Status.PACKED
        order.save(update_fields=["status", "updated_at"])
        order.save(update_fields=["status", "updated_at"])

        history = list(OrderStatusHistory.objects.filter(order=order))
        self.assertEqual([entry.status for entry in history], [Order.Status.PENDING, Order.Status.PACKED])
        self.assertEqual(history[-1].source, OrderStatusHistory.Source.SYSTEM)

    def test_cancellation_is_recorded_after_confirmation(self):
        order = self.create_order()
        change_order_status(
            order=order,
            new_status=Order.Status.PACKED,
            changed_by=self.user,
            source=OrderStatusHistory.Source.DASHBOARD,
        )
        change_order_status(
            order=order,
            new_status=Order.Status.CANCELLED,
            changed_by=self.user,
            note="Customer requested cancellation.",
            source=OrderStatusHistory.Source.DASHBOARD,
        )

        self.assertEqual(
            list(OrderStatusHistory.objects.filter(order=order).values_list("status", flat=True)),
            [Order.Status.PENDING, Order.Status.PACKED, Order.Status.CANCELLED],
        )

    def test_failed_history_write_rolls_back_the_status_update(self):
        order = self.create_order()

        with patch(
            "sitepages.order_status.OrderStatusHistory.objects.create",
            side_effect=RuntimeError("history write failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "history write failed"):
                change_order_status(
                    order=order,
                    new_status=Order.Status.PACKED,
                    changed_by=self.user,
                    source=OrderStatusHistory.Source.DASHBOARD,
                )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)

    def test_failed_status_update_does_not_create_history(self):
        order = self.create_order()

        with patch.object(Order, "save", side_effect=RuntimeError("status update failed")):
            with self.assertRaisesMessage(RuntimeError, "status update failed"):
                change_order_status(
                    order=order,
                    new_status=Order.Status.PACKED,
                    changed_by=self.user,
                    source=OrderStatusHistory.Source.DASHBOARD,
                )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), 1)
