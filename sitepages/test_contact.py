from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from company.models import CompanyProfile

from .models import ContactMessage


User = get_user_model()


class ContactPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.company = CompanyProfile.get_singleton()
        if self.company is None:
            self.company = CompanyProfile.objects.create(company_name="Next Uniq BD")
        self.company.company_name = "Next Uniq BD"
        self.company.phone = "(+88) 01883 385 687"
        self.company.email = "nextuniqbd@gmail.com"
        self.company.address = "9, Shahid Tajuddin Road, Moghbazar, Dhaka, Bangladesh"
        self.company.save()

    def test_contact_page_uses_company_profile_contact_data(self):
        response = self.client.get(reverse("frontend_contact"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.company.company_name)
        self.assertContains(response, self.company.phone)
        self.assertContains(response, self.company.email)
        self.assertContains(response, self.company.address)
        self.assertNotContains(response, "San Francisco")
        self.assertNotContains(response, "support@sbrevo.com")
        self.assertContains(response, reverse("frontend_contact"))

    def test_valid_contact_submission_creates_a_new_message_and_redirects(self):
        response = self.client.post(
            reverse("frontend_contact"),
            {
                "name": "Rahim Ahmed",
                "phone": "01700000000",
                "email": "rahim@example.com",
                "area": "Dhaka",
                "message": "Please share delivery details.",
            },
        )

        self.assertRedirects(response, reverse("frontend_contact"))
        contact_message = ContactMessage.objects.get()
        self.assertEqual(contact_message.status, ContactMessage.Status.NEW)
        self.assertEqual(contact_message.name, "Rahim Ahmed")

    def test_invalid_contact_submission_keeps_values_and_does_not_create_a_message(self):
        response = self.client.post(
            reverse("frontend_contact"),
            {"name": "Rahim Ahmed", "phone": "", "email": "not-an-email", "area": "Dhaka", "message": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "Enter a valid email address.")


class DashboardContactMessageTests(TestCase):
    def setUp(self):
        self.contact_message = ContactMessage.objects.create(
            name="Rahim Ahmed",
            phone="01700000000",
            email="rahim@example.com",
            area="Dhaka",
            message="Please share delivery details.",
        )
        self.user = User.objects.create_user(
            username="contact-staff",
            email="contact-staff@example.com",
            password="test-password",
        )
        self.view_permission = Permission.objects.get(codename="view_contactmessage")
        self.change_permission = Permission.objects.get(codename="change_contactmessage")

    def test_unauthorized_user_cannot_open_contact_message_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard_contact_message_list"))

        self.assertRedirects(response, reverse("dashboard_home"))

    def test_user_with_view_permission_can_open_list_and_detail(self):
        self.user.user_permissions.add(self.view_permission)
        self.client.force_login(self.user)

        list_response = self.client.get(reverse("dashboard_contact_message_list"), {"q": "rahim@"})
        detail_response = self.client.get(reverse("dashboard_contact_message_detail", args=[self.contact_message.pk]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, self.contact_message.name)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.contact_message.message)

    def test_detail_marks_new_message_read_and_status_post_can_resolve(self):
        self.user.user_permissions.add(self.view_permission, self.change_permission)
        self.client.force_login(self.user)

        self.client.get(reverse("dashboard_contact_message_detail", args=[self.contact_message.pk]))
        self.contact_message.refresh_from_db()
        self.assertEqual(self.contact_message.status, ContactMessage.Status.READ)

        response = self.client.post(
            reverse("dashboard_contact_message_status", args=[self.contact_message.pk, "resolved"])
        )
        self.contact_message.refresh_from_db()
        self.assertRedirects(response, reverse("dashboard_contact_message_detail", args=[self.contact_message.pk]))
        self.assertEqual(self.contact_message.status, ContactMessage.Status.RESOLVED)
