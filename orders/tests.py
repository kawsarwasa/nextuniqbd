from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from sitepages.models import Order
from sitepages.order_status import change_order_status


User = get_user_model()


class DashboardOrderTrackingTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser(
            username="tracking-manager",
            email="tracking-manager@example.com",
            password="test-password",
        )
        self.order = self.create_order("primary")

    def create_order(self, suffix, *, user=None):
        return Order.objects.create(
            user=user,
            full_name=f"Tracking Customer {suffix}",
            phone="01700000000",
            email=f"tracking-{suffix}@example.com",
            address="Dhaka",
            district="Dhaka",
            subtotal_amount="100.00",
            total_amount="160.00",
            item_count=1,
        )

    def get_tracking(self, order=None):
        self.client.force_login(self.manager)
        return self.client.get(reverse("dashboard_order_tracking", args=[(order or self.order).order_id]))

    def test_order_list_includes_the_tracking_control(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard_order_list"))

        self.assertContains(response, "js-order-tracking-trigger")
        self.assertContains(response, reverse("dashboard_order_tracking", args=[self.order.order_id]))

    def test_pending_tracking_returns_recorded_placement_and_unrecorded_future_steps(self):
        response = self.get_tracking()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["order_number"], self.order.order_id)
        self.assertIn("Order Placed", payload["html"])
        self.assertIn("Current status", payload["html"])
        self.assertIn("Not recorded", payload["html"])

    def test_packed_and_cancelled_history_uses_recorded_dates_and_notes(self):
        change_order_status(
            order=self.order,
            new_status=Order.Status.PACKED,
            changed_by=self.manager,
            note="Packed for shipment.",
            source="dashboard",
        )
        change_order_status(
            order=self.order,
            new_status=Order.Status.CANCELLED,
            changed_by=self.manager,
            note="Customer cancelled.",
            source="dashboard",
        )

        payload = self.get_tracking().json()

        self.assertIn("Order cancelled", payload["html"])
        self.assertIn("Customer cancelled.", payload["html"])
        self.assertIn("Packed for shipment.", payload["html"])
        self.assertIn("Not recorded", payload["html"])

    def test_order_without_history_shows_not_recorded_instead_of_a_fabricated_date(self):
        self.order.status_history.all().delete()

        payload = self.get_tracking().json()

        self.assertIn("Not recorded", payload["html"])

    def test_customer_cannot_access_the_tracking_endpoint_or_control(self):
        customer = User.objects.create_user(
            username="tracking-customer",
            email="tracking-customer@example.com",
            password="test-password",
        )
        customer.user_permissions.add(Permission.objects.get(codename="view_order"))
        customer_order = self.create_order("customer", user=customer)
        self.client.force_login(customer)

        endpoint_response = self.client.get(reverse("dashboard_order_tracking", args=[customer_order.order_id]))
        list_response = self.client.get(reverse("dashboard_order_list"))

        self.assertEqual(endpoint_response.status_code, 403)
        self.assertNotContains(list_response, "js-order-tracking-trigger")

    def test_invalid_tracking_order_returns_not_found(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard_order_tracking", args=["UNKNOWN123"]))

        self.assertEqual(response.status_code, 404)

    def test_order_detail_reuses_the_tracking_timeline_partial_for_staff(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard_order_detail", args=[self.order.order_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order Tracking")
        self.assertContains(response, "Recorded status history")
