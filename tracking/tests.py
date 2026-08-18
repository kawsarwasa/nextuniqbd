import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from category.models import Category, Product
from sitepages.models import Order, OrderItem, OrderStatusHistory
from sitepages.order_status import change_order_status

from .models import MetaEvent, MetaOrderAttribution


TRACKING_SETTINGS = {
    "META_TRACKING_ENABLED": True,
    "META_PIXEL_ID": "1728882544831974",
    "META_CAPI_ACCESS_TOKEN": "test-only-secret-token",
    "META_TEST_EVENT_CODE": "TEST56922",
}


class MetaTrackingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Tracking")
        self.product = Product.objects.create(
            category=self.category,
            name="Tracked Product",
            regular_price="1200.00",
            current_price="999.00",
            sku="NUBTRACKING",
            status=Product.Status.PUBLISHED,
            stock_quantity=10,
        )
        self.user = get_user_model().objects.create_user(
            username="tracked-shopper", email="shopper@example.com", password="test-password"
        )

    def add_product_to_session_cart(self, quantity=2):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): quantity}
        session.save()

    def create_order(self):
        order = Order.objects.create(
            user=self.user,
            full_name="Tracked Shopper",
            phone="01700000000",
            email="shopper@example.com",
            address="Dhaka",
            district="Dhaka",
            postal_code="1217",
            subtotal_amount="1998.00",
            shipping_amount="60.00",
            total_amount="2058.00",
            item_count=2,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            product_sku=self.product.sku,
            quantity=2,
            unit_price="999.00",
            subtotal="1998.00",
        )
        return order

    def transition(self, order, status):
        return change_order_status(
            order=order,
            new_status=status,
            changed_by=self.user,
            source=OrderStatusHistory.Source.DASHBOARD,
        )

    @override_settings(META_TRACKING_ENABLED=False, META_PIXEL_ID="")
    def test_disabled_tracking_renders_no_pixel_and_queues_no_events(self):
        response = self.client.get(reverse("frontend_product_detail", args=[self.product.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "connect.facebook.net")
        self.assertEqual(MetaEvent.objects.count(), 0)

    @override_settings(**TRACKING_SETTINGS)
    def test_view_content_uses_one_shared_browser_and_server_event_id(self):
        response = self.client.get(reverse("frontend_product_detail", args=[self.product.slug]))

        self.assertEqual(response.status_code, 200)
        event = MetaEvent.objects.get(event_name="ViewContent")
        self.assertContains(response, event.event_id)
        self.assertEqual(event.custom_data["content_ids"], [self.product.sku])
        self.assertEqual(event.custom_data["currency"], "BDT")
        self.assertEqual(event.custom_data["value"], 999.0)

    @override_settings(**TRACKING_SETTINGS)
    def test_rendered_product_page_uses_one_standard_page_view_event(self):
        response = self.client.get(reverse("frontend_product_detail", args=[self.product.slug]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count("fbq('track', 'PageView');"), 1)
        self.assertNotIn("trackCustom", content)
        self.assertLess(
            content.index("fbq('init', '1728882544831974');"),
            content.index("fbq('track', 'PageView');"),
        )

    @override_settings(**TRACKING_SETTINGS)
    def test_add_to_cart_success_queues_event_and_returns_shared_browser_event(self):
        response = self.client.post(
            reverse("cart_add"),
            data=json.dumps({"product_id": self.product.pk, "quantity": 2, "event_id": "add_to_cart_test_001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        event = MetaEvent.objects.get(event_name="AddToCart")
        self.assertEqual(event.event_id, "add_to_cart_test_001")
        self.assertEqual(event.custom_data["contents"], [{"id": self.product.sku, "quantity": 2, "item_price": 999.0}])
        self.assertEqual(response.json()["meta_event"]["event_id"], event.event_id)

    @override_settings(**TRACKING_SETTINGS)
    def test_failed_add_to_cart_does_not_queue_an_event(self):
        self.product.stock_quantity = 0
        self.product.save(update_fields=["stock_quantity"])

        response = self.client.post(
            reverse("cart_add"),
            data=json.dumps({"product_id": self.product.pk, "quantity": 1, "event_id": "add_to_cart_fail_001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(MetaEvent.objects.exists())

    @override_settings(**TRACKING_SETTINGS)
    def test_checkout_queues_one_event_for_the_same_cart_and_none_when_empty(self):
        empty_response = self.client.get(reverse("frontend_checkout"))
        self.assertEqual(empty_response.status_code, 200)
        self.assertFalse(MetaEvent.objects.filter(event_name="InitiateCheckout").exists())

        self.add_product_to_session_cart()
        first_response = self.client.get(reverse("frontend_checkout"))
        event = MetaEvent.objects.get(event_name="InitiateCheckout")
        second_response = self.client.get(reverse("frontend_checkout"))

        self.assertContains(first_response, event.event_id)
        self.assertContains(second_response, event.event_id)
        rendered_checkout = first_response.content.decode()
        self.assertEqual(
            rendered_checkout.count(
                "window.fbq(\n            'track',\n            'InitiateCheckout',"
            ),
            1,
        )
        self.assertIn("{ eventID: metaEvent.event_id }", rendered_checkout)
        self.assertEqual(MetaEvent.objects.filter(event_name="InitiateCheckout").count(), 1)
        self.assertEqual(event.custom_data["num_items"], 2)
        self.assertEqual(event.custom_data["value"], 2058.0)

    @override_settings(**TRACKING_SETTINGS)
    def test_order_success_does_not_queue_purchase(self):
        order = self.create_order()

        response = self.client.get(reverse("frontend_order_success", args=[order.order_id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MetaEvent.objects.filter(event_name="Purchase").exists())

    @override_settings(**TRACKING_SETTINGS)
    def test_order_placement_captures_shopper_attribution_but_does_not_queue_purchase(self):
        self.add_product_to_session_cart(quantity=1)
        self.client.cookies["_fbp"] = "fb.1.123.456"
        self.client.cookies["_fbc"] = "fb.1.123.utm"

        response = self.client.post(
            reverse("frontend_checkout"),
            {
                "full_name": "Checkout Shopper",
                "phone": "01700000000",
                "email": "shopper@example.com",
                "address": "Dhaka",
                "district": "Dhaka",
                "thana": "Moghbazar",
                "postal": "1217",
                "order_notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(full_name="Checkout Shopper")
        self.assertEqual(order.meta_attribution.fbp, "fb.1.123.456")
        self.assertEqual(order.meta_attribution.fbc, "fb.1.123.utm")
        self.assertFalse(MetaEvent.objects.filter(event_name="Purchase").exists())

    @override_settings(**TRACKING_SETTINGS)
    def test_delivered_to_confirmed_queues_one_purchase_using_shopper_attribution(self):
        order = self.create_order()
        MetaOrderAttribution.objects.create(
            order=order,
            fbp="fb.1.123.456",
            fbc="fb.1.123.utm",
            client_ip="127.0.0.1",
            client_user_agent="Shopper Browser",
            event_source_url="https://shop.example/checkout/",
        )
        for status in (Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.DELIVERED):
            self.transition(order, status)
        self.transition(order, Order.Status.CONFIRMED)

        event = MetaEvent.objects.get(event_name="Purchase")
        self.assertEqual(event.event_id, f"purchase_{order.order_id}")
        self.assertEqual(event.custom_data["order_id"], order.order_id)
        self.assertEqual(event.custom_data["value"], 2058.0)
        self.assertEqual(event.custom_data["contents"][0]["id"], self.product.sku)
        self.assertEqual(event.user_data["fbp"], "fb.1.123.456")
        self.assertEqual(event.user_data["client_user_agent"], "Shopper Browser")
        self.assertFalse(self.transition(order, Order.Status.CONFIRMED).changed)
        self.assertEqual(MetaEvent.objects.filter(event_name="Purchase").count(), 1)

    @override_settings(**TRACKING_SETTINGS)
    @patch("tracking.management.commands.send_meta_events.post_capi_events")
    def test_sender_marks_sent_events_and_never_resends_them(self, mock_post):
        from django.core.management import call_command

        MetaEvent.objects.create(
            event_id="send_event_001",
            event_name="ViewContent",
            event_time="2026-08-18T00:00:00Z",
            custom_data={"currency": "BDT"},
            user_data={},
        )
        call_command("send_meta_events")
        event = MetaEvent.objects.get(event_id="send_event_001")

        self.assertEqual(event.status, MetaEvent.Status.SENT)
        self.assertEqual(mock_post.call_count, 1)
        call_command("send_meta_events")
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(**TRACKING_SETTINGS)
    @patch(
        "tracking.management.commands.send_meta_events.post_capi_events",
        side_effect=[RuntimeError("upstream response"), {}],
    )
    def test_sender_records_a_safe_failure_and_continues_with_later_events(self, mock_post):
        from django.core.management import call_command

        for event_id in ("failed_event_001", "sent_event_002"):
            MetaEvent.objects.create(
                event_id=event_id,
                event_name="ViewContent",
                event_time="2026-08-18T00:00:00Z",
                custom_data={},
                user_data={},
            )

        call_command("send_meta_events")

        failed_event = MetaEvent.objects.get(event_id="failed_event_001")
        sent_event = MetaEvent.objects.get(event_id="sent_event_002")
        self.assertEqual(failed_event.status, MetaEvent.Status.FAILED)
        self.assertEqual(failed_event.last_error, "Meta CAPI delivery failed.")
        self.assertEqual(sent_event.status, MetaEvent.Status.SENT)
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(**TRACKING_SETTINGS)
    def test_capi_token_is_never_rendered_in_frontend_html(self):
        response = self.client.get(reverse("frontend_home"))

        self.assertContains(response, TRACKING_SETTINGS["META_PIXEL_ID"])
        self.assertNotContains(response, TRACKING_SETTINGS["META_CAPI_ACCESS_TOKEN"])

    @override_settings(**TRACKING_SETTINGS)
    @patch("tracking.meta.urlopen")
    def test_capi_sender_includes_the_configured_test_event_code(self, mock_urlopen):
        from tracking.meta import post_capi_events

        mock_urlopen.return_value.__enter__.return_value.read.return_value = b'{"events_received": 1}'
        post_capi_events([{"event_name": "ViewContent", "event_time": 1, "event_id": "event_001"}])

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["test_event_code"], TRACKING_SETTINGS["META_TEST_EVENT_CODE"])
