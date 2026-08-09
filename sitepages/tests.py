from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from PIL import Image
from io import BytesIO
from pathlib import Path
import json
import shutil
import tempfile

from category.models import Brand, Category, Product, ProductReview
from sitepages.models import (
    AbandonedCheckout,
    HeroSlide,
    Order,
    OrderItem,
    OrderStatusHistory,
    RoleProfile,
    Sale,
    UserProfile,
)
from sitepages.permissions import ensure_default_roles


User = get_user_model()


def build_uploaded_test_image(filename, color="white"):
    image_buffer = BytesIO()
    Image.new("RGB", (40, 40), color).save(image_buffer, format="JPEG")
    image_buffer.seek(0)
    return SimpleUploadedFile(filename, image_buffer.getvalue(), content_type="image/jpeg")


class DashboardAuthMixin:
    def setUp(self):
        super().setUp()
        self.dashboard_user = User.objects.create_superuser(
            username="dashboard-admin",
            email="dashboard-admin@example.com",
            password="Admin@100%",
        )


class FrontendProductDetailTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Home Goods")
        self.brand = Brand.objects.create(name="Northline")
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Atlas Desk Lamp",
            regular_price="150.00",
            current_price="120.00",
            sku="ATLAS001",
            status=Product.Status.PUBLISHED,
            availability="In Stock",
            short_description="A focused task lamp for desks.",
            full_description="<p>Dynamic lamp description.</p>",
        )
        self.related_product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Atlas Shelf Lamp",
            regular_price="170.00",
            current_price="140.00",
            sku="ATLAS002",
            status=Product.Status.PUBLISHED,
            availability="In Stock",
            short_description="A matching shelf lamp.",
            full_description="<p>Related product description.</p>",
        )
        ProductReview.objects.create(
            product=self.product,
            reviewer_name="Jessica Doe",
            reviewer_email="jessica@example.com",
            title="Excellent",
            body="Looks great on my desk.",
            rating=5,
            verified_purchase=True,
            review_date="2026-04-01",
        )

    def test_slug_product_detail_route_renders_requested_product(self):
        response = self.client.get(reverse("frontend_product_detail", args=[self.product.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product"], self.product)
        self.assertContains(response, "Atlas Desk Lamp")
        self.assertContains(response, "Dynamic lamp description.")
        self.assertContains(response, reverse("frontend_product_detail", args=[self.related_product.slug]))

    def test_legacy_product_details_route_accepts_slug_query(self):
        response = self.client.get(reverse("frontend_product_details"), {"slug": self.related_product.slug})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product"], self.related_product)
        self.assertContains(response, "Atlas Shelf Lamp")

    def test_legacy_product_details_route_falls_back_to_first_published_product(self):
        response = self.client.get(reverse("frontend_product_details"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product"], self.product)
        self.assertContains(response, "Atlas Desk Lamp")

    def test_product_detail_review_submission_creates_review(self):
        response = self.client.post(
            reverse("frontend_product_detail", args=[self.product.slug]),
            data={
                "reviewer_name": "Rahim Uddin",
                "reviewer_email": "rahim@example.com",
                "title": "Very useful lamp",
                "body": "The quality is strong and the light output is great.",
                "rating": "4",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.product.reviews.count(), 2)
        review = self.product.reviews.order_by("-id").first()
        self.assertEqual(review.reviewer_name, "Rahim Uddin")
        self.assertEqual(review.rating, 4)

    def test_product_detail_review_submission_shows_errors_when_invalid(self):
        response = self.client.post(
            reverse("frontend_product_detail", args=[self.product.slug]),
            data={
                "reviewer_name": "",
                "reviewer_email": "not-an-email",
                "title": "",
                "body": "",
                "rating": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please fix the highlighted review fields and submit again.")
        self.assertContains(response, "Please select a rating from 1 to 5 stars.")
        self.assertEqual(self.product.reviews.count(), 1)


class HeroSlideDashboardTests(DashboardAuthMixin, TestCase):
    def test_dashboard_hero_slide_list_renders(self):
        self.client.force_login(self.dashboard_user)
        response = self.client.get(reverse("dashboard_hero_slide_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hero Carousel")

    def test_hero_slide_slug_is_generated(self):
        image_buffer = BytesIO()
        Image.new("RGB", (20, 20), "white").save(image_buffer, format="JPEG")
        image_buffer.seek(0)
        with tempfile.TemporaryDirectory(prefix="revo-hero-test-") as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                slide = HeroSlide.objects.create(
                    name="Summer Hero",
                    title="Summer Sale",
                    image=SimpleUploadedFile("test.jpg", image_buffer.getvalue(), content_type="image/jpeg"),
                )

        self.assertEqual(slide.slug, "summer-hero")


class RoleDashboardTests(DashboardAuthMixin, TestCase):
    def setUp(self):
        super().setUp()
        ensure_default_roles()

    def test_role_list_page_renders(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_role_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Roles & Permissions")
        self.assertContains(response, "admins")

    def test_role_create_persists_group_and_profile(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_role_list"),
            data={
                "name": "manager",
                "description": "Handles day-to-day operations.",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        role = Group.objects.get(name="manager")
        profile = RoleProfile.objects.get(group=role)
        self.assertEqual(profile.description, "Handles day-to-day operations.")
        self.assertTrue(profile.is_active)

    def test_role_permission_page_updates_group_permissions(self):
        self.client.force_login(self.dashboard_user)
        role = Group.objects.create(name="support")
        RoleProfile.objects.create(group=role, description="Support team")
        permission = Permission.objects.get(codename="view_category")

        response = self.client.post(
            reverse("dashboard_role_permissions", args=[role.pk]),
            data={"permission_cells": ["category:view"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_role_list"))
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())

    def test_role_permission_page_does_not_include_removed_footer_module(self):
        self.client.force_login(self.dashboard_user)
        role = Group.objects.create(name="editor")
        RoleProfile.objects.create(group=role, description="Editor")

        response = self.client.get(reverse("dashboard_role_permissions", args=[role.pk]))

        self.assertEqual(response.status_code, 200)
        labels = [row["label"] for row in response.context["role_permission_rows"]]
        self.assertNotIn("Footer", labels)
        self.assertNotIn("Footer Content", labels)
        self.assertNotIn("Footer Group", labels)
        self.assertNotIn("Footer Link", labels)
        self.assertNotIn("Social Link", labels)
        self.assertNotIn("Payment Icon", labels)

    def test_role_permission_page_groups_blog_items_under_single_blog_row(self):
        self.client.force_login(self.dashboard_user)
        role = Group.objects.create(name="writer")
        RoleProfile.objects.create(group=role, description="Writer")

        response = self.client.get(reverse("dashboard_role_permissions", args=[role.pk]))

        self.assertEqual(response.status_code, 200)
        labels = [row["label"] for row in response.context["role_permission_rows"]]
        self.assertIn("Blog", labels)
        self.assertNotIn("Blog Category", labels)
        self.assertNotIn("Blog Tag", labels)
        self.assertNotIn("Blog Post", labels)
        self.assertNotIn("Blog Comment", labels)

    def test_system_role_permissions_are_not_reset_after_manual_update(self):
        self.client.force_login(self.dashboard_user)
        role = Group.objects.get(name="customers")
        permission = Permission.objects.get(codename="view_category")

        response = self.client.post(
            reverse("dashboard_role_permissions", args=[role.pk]),
            data={"permission_cells": ["category:view"]},
        )

        self.assertEqual(response.status_code, 302)
        role.refresh_from_db()
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())

        ensure_default_roles()
        role.refresh_from_db()
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())


class UserPermissionDashboardTests(DashboardAuthMixin, TestCase):
    def setUp(self):
        super().setUp()
        ensure_default_roles()

    def test_user_permission_page_saves_direct_permissions_and_redirects_to_user_list(self):
        self.client.force_login(self.dashboard_user)
        target_user = User.objects.create_user(
            username="customer-special@example.com",
            email="customer-special@example.com",
            password="StrongPass@123",
        )
        customer_role = Group.objects.get(name="customers")
        target_user.groups.add(customer_role)
        permission = Permission.objects.get(codename="view_category")

        response = self.client.post(
            reverse("dashboard_user_permissions", args=[target_user.pk]),
            data={
                "role": str(customer_role.pk),
                "is_active": "on",
                "is_staff": "on",
                "permission_cells": ["category:view"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_user_list"))
        target_user.refresh_from_db()
        self.assertTrue(target_user.user_permissions.filter(pk=permission.pk).exists())
        self.assertFalse(customer_role.permissions.filter(pk=permission.pk).exists())
        self.assertTrue(target_user.is_staff)

    def test_user_permission_page_can_disable_staff_status(self):
        self.client.force_login(self.dashboard_user)
        target_user = User.objects.create_user(
            username="staff-toggle@example.com",
            email="staff-toggle@example.com",
            password="StrongPass@123",
            is_staff=True,
        )
        customer_role = Group.objects.get(name="customers")
        target_user.groups.add(customer_role)

        response = self.client.post(
            reverse("dashboard_user_permissions", args=[target_user.pk]),
            data={
                "role": str(customer_role.pk),
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        target_user.refresh_from_db()
        self.assertFalse(target_user.is_staff)

    def test_user_permission_page_context_shows_role_permissions_on_user_page(self):
        self.client.force_login(self.dashboard_user)
        target_user = User.objects.create_user(
            username="catalog-user@example.com",
            email="catalog-user@example.com",
            password="StrongPass@123",
        )
        role = Group.objects.get(name="catalog_managers")
        target_user.groups.add(role)

        response = self.client.get(reverse("dashboard_user_permissions", args=[target_user.pk]), {"role": role.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["direct_permission_count"], 0)
        category_row = next(row for row in response.context["user_permission_rows"] if row["key"] == "category")
        self.assertTrue(category_row["permissions"]["view"]["checked"])
        self.assertTrue(category_row["permissions"]["view"]["readonly"])
        self.assertFalse(category_row["permissions"]["view"]["granted_directly"])


class DashboardProfileTests(DashboardAuthMixin, TestCase):
    def test_dashboard_profile_page_renders(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Details")
        self.assertContains(response, "Change Password")

    def test_dashboard_profile_update_persists_user_and_profile_fields(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_profile"),
            data={
                "form_type": "profile",
                "name": "Sohel Rana",
                "username": "dashboard-admin",
                "email": "sohel@example.com",
                "phone": "+8801712345678",
                "address": "Dhaka, Bangladesh",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_profile"))
        self.dashboard_user.refresh_from_db()
        profile = UserProfile.objects.get(user=self.dashboard_user)
        self.assertEqual(self.dashboard_user.first_name, "Sohel")
        self.assertEqual(self.dashboard_user.last_name, "Rana")
        self.assertEqual(self.dashboard_user.email, "sohel@example.com")
        self.assertEqual(self.dashboard_user.username, "dashboard-admin")
        self.assertEqual(profile.phone, "+8801712345678")
        self.assertEqual(profile.address, "Dhaka, Bangladesh")

    def test_dashboard_profile_updates_username(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_profile"),
            data={
                "form_type": "profile",
                "name": "Sohel Rana",
                "username": "sohel-rana",
                "email": "sohel@example.com",
                "phone": "+8801712345678",
                "address": "Dhaka, Bangladesh",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.dashboard_user.refresh_from_db()
        self.assertEqual(self.dashboard_user.username, "sohel-rana")

    def test_dashboard_profile_rejects_another_users_username(self):
        User.objects.create_user(
            username="taken-username",
            email="taken@example.com",
            password="StrongPass@123",
        )
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_profile"),
            data={
                "form_type": "profile",
                "name": "Sohel Rana",
                "username": " taken-username ",
                "email": "sohel@example.com",
                "phone": "+8801712345678",
                "address": "Dhaka, Bangladesh",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this username already exists.")
        self.dashboard_user.refresh_from_db()
        self.assertEqual(self.dashboard_user.username, "dashboard-admin")

    def test_dashboard_profile_password_change_updates_password(self):
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_profile"),
            data={
                "form_type": "password",
                "old_password": "Admin@100%",
                "new_password1": "NewStrongPass@123",
                "new_password2": "NewStrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_profile"))
        self.dashboard_user.refresh_from_db()
        self.assertTrue(self.dashboard_user.check_password("NewStrongPass@123"))

    def test_dashboard_profile_image_replacement_deletes_previous_file(self):
        temp_media_root = Path.cwd() / "test_media_root"
        shutil.rmtree(temp_media_root, ignore_errors=True)
        temp_media_root.mkdir(exist_ok=True)
        try:
            with override_settings(MEDIA_ROOT=str(temp_media_root)):
                self.client.force_login(self.dashboard_user)

                first_response = self.client.post(
                    reverse("dashboard_profile"),
                    data={
                        "form_type": "profile",
                        "name": "Dashboard Admin",
                        "email": "dashboard-admin@example.com",
                        "phone": "",
                        "address": "",
                        "image": build_uploaded_test_image("profile-1.jpg", color="red"),
                    },
                )

                self.assertEqual(first_response.status_code, 302)
                profile = UserProfile.objects.get(user=self.dashboard_user)
                first_image_name = profile.image.name
                first_image_path = Path(profile.image.path)
                self.assertTrue(first_image_path.exists())
                profile.image.close()

                second_response = self.client.post(
                    reverse("dashboard_profile"),
                    data={
                        "form_type": "profile",
                        "name": "Dashboard Admin",
                        "email": "dashboard-admin@example.com",
                        "phone": "",
                        "address": "",
                        "image": build_uploaded_test_image("profile-2.jpg", color="blue"),
                    },
                )

                self.assertEqual(second_response.status_code, 302)
                profile.refresh_from_db()
                self.assertNotEqual(profile.image.name, first_image_name)
                self.assertFalse(UserProfile.objects.filter(image=first_image_name).exists())
                self.assertTrue(Path(profile.image.path).exists())
        finally:
            shutil.rmtree(temp_media_root, ignore_errors=True)


class FrontendCartTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Lighting")
        self.brand = Brand.objects.create(name="Luma")
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Nova Floor Lamp",
            regular_price="220.00",
            current_price="180.00",
            sku="LAMP001",
            status=Product.Status.PUBLISHED,
            availability="In Stock",
            stock_quantity=10,
            short_description="Floor lamp for testing cart sessions.",
        )

    def test_cart_add_endpoint_stores_product_in_session(self):
        response = self.client.post(
            reverse("cart_add"),
            data='{"product_id": %d, "quantity": 2}' % self.product.pk,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart"]["item_count"], 2)
        self.assertEqual(self.client.session["storefront_cart"][str(self.product.pk)], 2)

    def test_cart_page_renders_items_from_session(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 3}
        session.save()

        response = self.client.get(reverse("frontend_cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nova Floor Lamp")
        self.assertContains(response, 'value="3"', html=False)
        self.assertEqual(response.context["cart_state"]["item_count"], 3)

    def test_checkout_page_renders_session_cart_items(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 2}
        session.save()

        response = self.client.get(reverse("frontend_checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nova Floor Lamp")
        self.assertContains(response, "Qty: 2")
        self.assertContains(response, "৳360.00")

    def test_checkout_page_uses_selected_delivery_zone_from_session(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session["storefront_delivery_zone"] = "outside_dhaka"
        session.save()

        response = self.client.get(reverse("frontend_checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "৳130.00")
        self.assertContains(response, "3-5 business days")

    def test_checkout_page_shows_empty_state_when_cart_is_empty(self):
        response = self.client.get(reverse("frontend_checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your cart is empty.")
        self.assertContains(response, reverse("frontend_products"))

    def test_checkout_page_prefills_shipping_information_for_logged_in_user(self):
        user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="StrongPass@123",
            first_name="Buyer",
            last_name="User",
        )
        profile = UserProfile.objects.get(user=user)
        profile.phone = "+8801711111111"
        profile.address = "House 10, Road 12, Dhaka"
        profile.save(update_fields=["phone", "address"])

        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()
        self.client.force_login(user)

        response = self.client.get(reverse("frontend_checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Buyer User"', html=False)
        self.assertContains(response, 'value="+8801711111111"', html=False)
        self.assertContains(response, 'value="buyer@example.com"', html=False)
        self.assertContains(response, "House 10, Road 12, Dhaka")

    def test_logged_in_checkout_visit_creates_pending_abandoned_checkout(self):
        user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="StrongPass@123",
            first_name="Buyer",
            last_name="User",
        )
        profile = UserProfile.objects.get(user=user)
        profile.phone = "+8801711111111"
        profile.address = "House 10, Road 12, Dhaka"
        profile.save(update_fields=["phone", "address"])
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 2}
        session.save()
        self.client.force_login(user)

        response = self.client.get(reverse("frontend_checkout"))

        abandoned_checkout = AbandonedCheckout.objects.get(user=user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(abandoned_checkout.status, AbandonedCheckout.Status.PENDING)
        self.assertEqual(abandoned_checkout.full_name, "Buyer User")
        self.assertEqual(abandoned_checkout.phone_number, "+8801711111111")
        self.assertEqual(abandoned_checkout.subtotal, 360)
        self.assertEqual(abandoned_checkout.shipping_charge, 60)
        self.assertEqual(abandoned_checkout.total_amount, 420)
        self.assertEqual(abandoned_checkout.cart_items[0]["quantity"], 2)

    def test_guest_phone_capture_creates_and_updates_single_pending_checkout(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()

        first_response = self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps({"phone": "+8801711111111"}),
            content_type="application/json",
        )
        second_response = self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps(
                {
                    "phone": "+8801711111111",
                    "full_name": "Guest Buyer",
                    "address": "Dhaka",
                    "district": "Dhaka",
                    "thana": "Banani",
                    "postal": "1213",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(
            first_response.json(),
            {
                "success": True,
                "message": "Abandoned checkout saved",
            },
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(AbandonedCheckout.objects.count(), 1)
        abandoned_checkout = AbandonedCheckout.objects.get()
        self.assertIsNone(abandoned_checkout.user)
        self.assertEqual(abandoned_checkout.session_key, self.client.session.session_key)
        self.assertEqual(abandoned_checkout.full_name, "Guest Buyer")
        self.assertEqual(abandoned_checkout.phone_number, "01711111111")
        self.assertEqual(abandoned_checkout.area_thana, "Banani")
        self.assertEqual(abandoned_checkout.postal_code, "1213")

    def test_guest_partial_or_invalid_phone_does_not_create_abandoned_checkout(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()

        for phone_number in (
            "0",
            "017",
            "0171111111",
            "+880171111111",
            "8801211111111",
            "019111111111",
        ):
            response = self.client.post(
                reverse("save_abandoned_checkout"),
                data=json.dumps({"phone": phone_number}),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["success"])

        self.assertFalse(AbandonedCheckout.objects.exists())

    def test_guest_bd_phone_formats_are_normalized_before_capture(self):
        for phone_number in ("+8801711111111", "8801711111111", "01711111111"):
            with self.subTest(phone_number=phone_number):
                AbandonedCheckout.objects.all().delete()
                session = self.client.session
                session["storefront_cart"] = {str(self.product.pk): 1}
                session.save()

                response = self.client.post(
                    reverse("save_abandoned_checkout"),
                    data=json.dumps({"phone": phone_number}),
                    content_type="application/json",
                )

                self.assertTrue(response.json()["success"])
                self.assertEqual(
                    AbandonedCheckout.objects.get().phone_number,
                    "01711111111",
                )

    def test_partial_phone_does_not_overwrite_existing_guest_abandoned_checkout(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()
        self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps({"phone": "01711111111", "full_name": "Guest Buyer"}),
            content_type="application/json",
        )

        response = self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps({"phone": "0171", "full_name": "Changed Name"}),
            content_type="application/json",
        )

        self.assertFalse(response.json()["success"])
        self.assertEqual(AbandonedCheckout.objects.count(), 1)
        abandoned_checkout = AbandonedCheckout.objects.get()
        self.assertEqual(abandoned_checkout.phone_number, "01711111111")
        self.assertEqual(abandoned_checkout.full_name, "Guest Buyer")

    def test_guest_checkout_is_not_captured_without_phone_or_cart(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()

        no_phone_response = self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps({"full_name": "Guest Buyer"}),
            content_type="application/json",
        )
        session = self.client.session
        session["storefront_cart"] = {}
        session.save()
        empty_cart_response = self.client.post(
            reverse("save_abandoned_checkout"),
            data=json.dumps({"phone": "+8801711111111"}),
            content_type="application/json",
        )

        self.assertFalse(no_phone_response.json()["success"])
        self.assertFalse(empty_cart_response.json()["success"])
        self.assertFalse(AbandonedCheckout.objects.exists())

    def test_checkout_post_creates_order_with_items_and_redirects_to_success(self):
        user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="StrongPass@123",
        )
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 2}
        session["storefront_delivery_zone"] = "outside_dhaka"
        session.save()
        self.client.force_login(user)

        response = self.client.post(
            reverse("frontend_checkout"),
            data={
                "full_name": "Buyer User",
                "phone": "+8801711111111",
                "email": "buyer@example.com",
                "address": "House 10, Road 12, Dhaka",
                "district": "Dhaka",
                "thana": "Banani",
                "postal": "1213",
                "order_notes": "Call before delivery",
            },
        )

        order = Order.objects.get(user=user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("frontend_order_success", args=[order.order_id]))
        self.assertEqual(len(order.order_id), 12)
        self.assertEqual(order.order_id, order.order_id.upper())
        self.assertTrue(order.order_id.isalnum())
        self.assertTrue(any(character.isalpha() for character in order.order_id))
        self.assertTrue(any(character.isdigit() for character in order.order_id))
        self.assertEqual(order.phone, "+8801711111111")
        self.assertEqual(order.address, "House 10, Road 12, Dhaka")
        self.assertEqual(order.district, "Dhaka")
        self.assertEqual(order.thana, "Banani")
        self.assertEqual(order.postal_code, "1213")
        self.assertEqual(order.order_notes, "Call before delivery")
        self.assertEqual(order.delivery_zone, "outside_dhaka")
        self.assertEqual(order.items.count(), 1)
        order_item = order.items.get()
        self.assertEqual(order_item.product, self.product)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(self.client.session["storefront_cart"], {})
        abandoned_checkout = AbandonedCheckout.objects.get(user=user)
        self.assertEqual(abandoned_checkout.status, AbandonedCheckout.Status.CONVERTED)

    def test_cart_update_and_clear_endpoints_mutate_session(self):
        session = self.client.session
        session["storefront_cart"] = {str(self.product.pk): 1}
        session.save()

        update_response = self.client.post(
            reverse("cart_update"),
            data='{"product_id": %d, "quantity": 4}' % self.product.pk,
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["cart"]["item_count"], 4)

        clear_response = self.client.post(
            reverse("cart_clear"),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["cart"]["item_count"], 0)
        self.assertEqual(self.client.session["storefront_cart"], {})

    def test_cart_delivery_zone_endpoint_persists_selection(self):
        response = self.client.post(
            reverse("cart_set_delivery_zone"),
            data='{"zone": "outside_dhaka"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["delivery_zone"]["amount"], "130.00")
        self.assertEqual(self.client.session["storefront_delivery_zone"], "outside_dhaka")

    def test_products_page_sets_csrf_cookie_for_session_cart_requests(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        products_response = client.get(reverse("frontend_products"))

        self.assertEqual(products_response.status_code, 200)
        self.assertIn("csrftoken", products_response.cookies)

        response = client.post(
            reverse("cart_add"),
            data='{"product_id": %d, "quantity": 1}' % self.product.pk,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=products_response.cookies["csrftoken"].value,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart"]["item_count"], 1)


class AuthenticationFlowTests(TestCase):
    def test_register_creates_user_and_assigns_customer_role(self):
        response = self.client.post(
            reverse("auth_register"),
            data={
                "name": "Sohel Rana",
                "username": "sohelrana",
                "email": "sohel@example.com",
                "password": "StrongPass@123",
                "confirm_password": "StrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_home"))
        user = User.objects.get(email="sohel@example.com")
        self.assertEqual(user.username, "sohelrana")
        self.assertEqual(user.email, "sohel@example.com")
        self.assertTrue(user.groups.filter(name="customers").exists())
        self.assertTrue(user.has_perm("sitepages.view_order"))
        self.assertFalse(user.has_perm("sitepages.view_sale"))

    def test_register_requires_matching_confirm_password(self):
        response = self.client.post(
            reverse("auth_register"),
            data={
                "name": "Sohel Rana",
                "username": "sohelrana",
                "email": "sohel@example.com",
                "password": "StrongPass@123",
                "confirm_password": "WrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")
        self.assertFalse(User.objects.filter(email="sohel@example.com").exists())

    def test_register_rejects_duplicate_username_after_trimming(self):
        User.objects.create_user(
            username="member-user",
            email="member@example.com",
            password="StrongPass@123",
        )

        response = self.client.post(
            reverse("auth_register"),
            data={
                "name": "Another Member",
                "username": " member-user ",
                "email": "another@example.com",
                "password": "StrongPass@123",
                "confirm_password": "StrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this username already exists.")
        self.assertFalse(User.objects.filter(email="another@example.com").exists())

    def test_login_uses_username_and_password(self):
        user = User.objects.create_user(
            username="member-user",
            email="member@example.com",
            password="StrongPass@123",
        )

        response = self.client.post(
            reverse("auth_login"),
            data={
                "username": "member-user",
                "password": "StrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_rejects_email_instead_of_username(self):
        user = User.objects.create_user(
            username="member-user",
            email="member@example.com",
            password="StrongPass@123",
        )

        response = self.client.post(
            reverse("auth_login"),
            data={
                "username": user.email,
                "password": "StrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_wrong_password(self):
        user = User.objects.create_user(
            username="member-user",
            email="member@example.com",
            password="StrongPass@123",
        )

        response = self.client.post(
            reverse("auth_login"),
            data={
                "username": user.username,
                "password": "WrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_default_superuser_uses_a_username_separate_from_its_email(self):
        from sitepages.apps import SitepagesConfig
        from sitepages.signals import (
            SUPERUSER_EMAIL,
            SUPERUSER_USERNAME,
            seed_default_auth_records,
        )

        seed_default_auth_records(sender=SitepagesConfig)

        user = User.objects.get(email=SUPERUSER_EMAIL)
        self.assertEqual(user.username, SUPERUSER_USERNAME)

    def test_login_rejects_inactive_user(self):
        user = User.objects.create_user(
            username="inactive-user",
            email="inactive@example.com",
            password="StrongPass@123",
            is_active=False,
        )

        response = self.client.post(
            reverse("auth_login"),
            data={
                "username": user.username,
                "password": "StrongPass@123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard_home"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("auth_login"), response.url)

    def test_customer_can_access_blank_dashboard_home(self):
        ensure_default_roles()
        user = User.objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            password="StrongPass@123",
        )
        user.groups.add(Group.objects.get(name="customers"))
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard_home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "New Orders")
        self.assertNotContains(response, "Sales Value")


class DashboardHomeTests(DashboardAuthMixin, TestCase):
    def create_order(self, *, suffix, status=Order.Status.PENDING):
        return Order.objects.create(
            user=self.dashboard_user,
            full_name=f"Buyer {suffix}",
            phone=f"+88017000000{suffix}",
            email=f"buyer{suffix}@example.com",
            address=f"Address {suffix}",
            district="Dhaka",
            thana="Banani",
            postal_code="1213",
            order_notes="",
            delivery_zone="inside_dhaka",
            delivery_label="Inside Dhaka",
            delivery_estimate="1-2 business days",
            shipping_amount="60.00",
            subtotal_amount="100.00",
            total_amount="160.00",
            item_count=1,
            status=status,
        )

    def test_dashboard_home_uses_dynamic_metrics_and_chart_data(self):
        self.create_order(suffix="1")
        self.create_order(suffix="2", status=Order.Status.CONFIRMED)
        User.objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            password="StrongPass@123",
        )
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["new_order_total"], 1)
        self.assertEqual(response.context["user_registration_total"], User.objects.count())
        self.assertGreaterEqual(response.context["unique_visitor_total"], 1)
        self.assertEqual(len(response.context["dashboard_sales_chart"]["categories"]), 7)
        series = {
            item["name"]: item["data"]
            for item in response.context["dashboard_sales_chart"]["series"]
        }
        self.assertEqual(sum(series["Order Value"]), 320.0)
        self.assertEqual(sum(series["Sales Value"]), 160.0)
        self.assertNotContains(response, "Digital Goods")
        self.assertContains(response, "dashboard-sales-chart-data")


class DashboardAbandonedCheckoutTests(DashboardAuthMixin, TestCase):
    def create_abandoned_checkout(self, **overrides):
        defaults = {
            "full_name": "Pending Buyer",
            "phone_number": "+8801711111111",
            "email": "pending@example.com",
            "district": "Dhaka",
            "delivery_area": "inside_dhaka",
            "cart_items": [
                {
                    "name": "Test Product",
                    "sku": "TEST-1",
                    "quantity": 2,
                    "unit_price": "50.00",
                    "line_total": "100.00",
                    "image_url": "",
                }
            ],
            "subtotal": "100.00",
            "shipping_charge": "60.00",
            "total_amount": "160.00",
        }
        defaults.update(overrides)
        return AbandonedCheckout.objects.create(**defaults)

    def test_list_excludes_converted_checkouts(self):
        pending_checkout = self.create_abandoned_checkout()
        self.create_abandoned_checkout(
            full_name="Converted Buyer",
            phone_number="+8801722222222",
            status=AbandonedCheckout.Status.CONVERTED,
        )
        self.create_abandoned_checkout(
            full_name="Contacted Buyer",
            phone_number="+8801733333333",
            status=AbandonedCheckout.Status.CONTACTED,
        )
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_abandoned_checkout_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_checkout.full_name)
        self.assertNotContains(response, "Converted Buyer")
        self.assertNotContains(response, "Contacted Buyer")
        self.assertEqual(response.context["abandoned_checkout_total"], 1)

    def test_list_supports_search_and_explicit_status_filter(self):
        self.create_abandoned_checkout(full_name="Dhaka Buyer")
        contacted = self.create_abandoned_checkout(
            full_name="Chattogram Buyer",
            email="contacted@example.com",
            district="Chattogram",
            status=AbandonedCheckout.Status.CONTACTED,
        )
        self.client.force_login(self.dashboard_user)

        response = self.client.get(
            reverse("dashboard_abandoned_checkout_list"),
            {"status": "contacted", "q": "contacted@", "district": "Chattogram", "user_type": "guest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, contacted.full_name)
        self.assertNotContains(response, "Dhaka Buyer")

    def test_detail_shows_customer_cart_and_summary(self):
        checkout = self.create_abandoned_checkout(address="Road 1", area_thana="Banani", postal_code="1213")
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_abandoned_checkout_detail", args=[checkout.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Product")
        self.assertContains(response, "TEST-1")
        self.assertContains(response, "Road 1")
        self.assertContains(response, "160.00")

    def test_status_action_marks_pending_checkout_contacted(self):
        checkout = self.create_abandoned_checkout()
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_abandoned_checkout_status", args=[checkout.pk, "contacted"])
        )

        checkout.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(checkout.status, AbandonedCheckout.Status.CONTACTED)

    def test_converted_checkout_detail_is_hidden(self):
        checkout = self.create_abandoned_checkout(status=AbandonedCheckout.Status.CONVERTED)
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_abandoned_checkout_detail", args=[checkout.pk]))

        self.assertEqual(response.status_code, 404)

    def test_list_is_paginated(self):
        for index in range(21):
            self.create_abandoned_checkout(
                full_name=f"Buyer {index}",
                phone_number=f"+880170000{index:03d}",
                email=f"buyer{index}@example.com",
            )
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_abandoned_checkout_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["abandoned_checkouts"]), 20)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)


class DashboardOrderTests(DashboardAuthMixin, TestCase):
    def create_order(self, *, user, suffix):
        return Order.objects.create(
            user=user,
            full_name=f"Buyer {suffix}",
            phone=f"+88017000000{suffix}",
            email=f"buyer{suffix}@example.com",
            address=f"Address {suffix}",
            district="Dhaka",
            thana="Banani",
            postal_code="1213",
            order_notes="",
            delivery_zone="inside_dhaka",
            delivery_label="Inside Dhaka",
            delivery_estimate="1-2 business days",
            shipping_amount="60.00",
            subtotal_amount="100.00",
            total_amount="160.00",
            item_count=1,
        )

    def test_order_defaults_to_pending_status(self):
        order = self.create_order(user=self.dashboard_user, suffix="0")

        self.assertEqual(order.status, Order.Status.PENDING)

    def test_dashboard_order_list_shows_all_orders_for_staff_user(self):
        own_order = self.create_order(user=self.dashboard_user, suffix="1")
        other_user = User.objects.create_user(
            username="customer-2@example.com",
            email="customer-2@example.com",
            password="StrongPass@123",
        )
        other_order = self.create_order(user=other_user, suffix="2")
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_order.order_id)
        self.assertContains(response, other_order.order_id)

    def test_dashboard_order_list_paginates_thirty_records_per_page(self):
        for index in range(31):
            self.create_order(user=self.dashboard_user, suffix=f"pagination-{index}")
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_order_list"))
        second_page = self.client.get(reverse("dashboard_order_list"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["orders"]), 30)
        self.assertContains(response, "dashboard-pagination")
        self.assertEqual(len(second_page.context["orders"]), 1)

    def test_dashboard_order_list_shows_only_own_orders_for_non_staff_user(self):
        viewer = User.objects.create_user(
            username="viewer@example.com",
            email="viewer@example.com",
            password="StrongPass@123",
            is_staff=False,
        )
        view_order_permission = Permission.objects.get(codename="view_order")
        viewer.user_permissions.add(view_order_permission)

        own_order = self.create_order(user=viewer, suffix="3")
        other_user = User.objects.create_user(
            username="customer-4@example.com",
            email="customer-4@example.com",
            password="StrongPass@123",
        )
        other_order = self.create_order(user=other_user, suffix="4")
        self.client.force_login(viewer)

        response = self.client.get(reverse("dashboard_order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_order.order_id)
        self.assertNotContains(response, other_order.order_id)

        detail_response = self.client.get(reverse("dashboard_order_detail", args=[other_order.order_id]))
        self.assertEqual(detail_response.status_code, 404)

    def test_customer_role_order_list_shows_only_own_orders(self):
        ensure_default_roles()
        viewer = User.objects.create_user(
            username="customer-orders@example.com",
            email="customer-orders@example.com",
            password="StrongPass@123",
            is_staff=False,
        )
        viewer.groups.add(Group.objects.get(name="customers"))
        own_order = self.create_order(user=viewer, suffix="11")
        other_user = User.objects.create_user(
            username="customer-other@example.com",
            email="customer-other@example.com",
            password="StrongPass@123",
        )
        other_order = self.create_order(user=other_user, suffix="12")
        self.client.force_login(viewer)

        response = self.client.get(reverse("dashboard_order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_order.order_id)
        self.assertNotContains(response, other_order.order_id)
        self.assertNotContains(response, reverse("dashboard_sale_list"))

    def test_dashboard_order_detail_updates_status(self):
        order = self.create_order(user=self.dashboard_user, suffix="5")
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            data={"status": Order.Status.CONFIRMED},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_order_detail", args=[order.order_id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        history = OrderStatusHistory.objects.get(order=order, status=Order.Status.CONFIRMED)
        self.assertEqual(history.changed_by, self.dashboard_user)
        self.assertEqual(history.source, OrderStatusHistory.Source.DASHBOARD)
        sale = Sale.objects.get(order=order)
        self.assertEqual(sale.sale_id, f"S{order.order_id}")
        self.assertEqual(sale.total_amount, order.total_amount)

    def test_confirmed_order_can_be_cancelled(self):
        order = self.create_order(user=self.dashboard_user, suffix="7")
        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.dashboard_user)

        response = self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            data={"status": Order.Status.CANCELLED, "note": "Customer cancelled."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard_order_detail", args=[order.order_id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(Sale.objects.filter(order=order).count(), 1)

    def test_dashboard_sale_list_shows_confirmed_order_sales(self):
        order = self.create_order(user=self.dashboard_user, suffix="8")
        OrderItem.objects.create(
            order=order,
            product_name="Individual Sale Product",
            product_sku="SALE001",
            category_name="Accessories",
            brand_name="Northline",
            quantity=2,
            unit_price="50.00",
            subtotal="100.00",
        )
        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])
        sale = Sale.objects.get(order=order)
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_sale_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sales")
        self.assertContains(response, sale.sale_id)
        self.assertContains(response, "Buyer 8")
        self.assertContains(response, "Cash on Delivery")
        self.assertContains(response, reverse("dashboard_sale_detail", args=[sale.sale_id]))
        self.assertContains(response, reverse("dashboard_sale_list"))

        detail_response = self.client.get(reverse("dashboard_sale_detail", args=[sale.sale_id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Individual Sale Product")
        self.assertContains(detail_response, "SALE001")
        self.assertContains(detail_response, "Accessories / Northline")

    def test_dashboard_sale_list_paginates_thirty_records_per_page(self):
        for index in range(31):
            order = self.create_order(user=self.dashboard_user, suffix=f"sale-pagination-{index}")
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_sale_list"))
        second_page = self.client.get(reverse("dashboard_sale_list"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["sales"]), 30)
        self.assertContains(response, "dashboard-pagination")
        self.assertEqual(len(second_page.context["sales"]), 1)

    def test_dashboard_order_list_shows_confirmed_orders_for_workflow_progression(self):
        pending_order = self.create_order(user=self.dashboard_user, suffix="9")
        confirmed_order = self.create_order(user=self.dashboard_user, suffix="10")
        confirmed_order.status = Order.Status.CONFIRMED
        confirmed_order.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.dashboard_user)

        response = self.client.get(reverse("dashboard_order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_order.order_id)
        self.assertContains(response, confirmed_order.order_id)
        self.assertContains(response, reverse("dashboard_sale_list"))

    def test_dashboard_order_detail_blocks_status_update_without_permission(self):
        viewer = User.objects.create_user(
            username="viewer-update@example.com",
            email="viewer-update@example.com",
            password="StrongPass@123",
            is_staff=False,
        )
        viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
        order = self.create_order(user=viewer, suffix="6")
        self.client.force_login(viewer)

        response = self.client.post(
            reverse("dashboard_order_detail", args=[order.order_id]),
            data={"status": Order.Status.CANCELLED},
        )

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
