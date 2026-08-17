from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from company.models import CompanyProfile


class PrivacyPolicyPageTests(TestCase):
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

    def test_privacy_policy_uses_fixed_policy_content_and_dynamic_company_details(self):
        response = self.client.get(reverse("frontend_privacy_policy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Privacy Policy | Next Uniq BD")
        self.assertContains(response, "Last Updated: August 17, 2026")
        self.assertContains(response, self.company.address)
        self.assertContains(response, self.company.phone)
        self.assertContains(response, self.company.email)
        self.assertContains(response, 'href="mailto:nextuniqbd@gmail.com"', html=False)
        self.assertContains(response, reverse("frontend_contact"))

    def test_privacy_policy_discloses_actual_cod_and_session_practices_without_demo_tracking(self):
        response = self.client.get(reverse("frontend_privacy_policy"))

        self.assertContains(response, "Cash on Delivery (COD)")
        self.assertContains(response, "Abandoned Checkout Information")
        self.assertContains(response, "does not currently use third-party advertising pixels or analytics")
        self.assertNotContains(response, "Stripe")
        self.assertNotContains(response, "PayPal")
        self.assertNotContains(response, "{% now")
