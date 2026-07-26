from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sitepages.permissions import ensure_default_roles, get_permission_matrix
from sitepages.models import Order, Sale

from .forms import (
    AccountsReportFilterForm,
    CashInForm,
    CashOutForm,
    DueAccountForm,
    DuePaymentForm,
    OpeningBalanceForm,
    TransactionCategoryForm,
)
from .models import (
    CategoryType,
    CashTransaction,
    DueAccount,
    DuePayment,
    DueType,
    PaymentMethod,
    TransactionCategory,
    TransactionSource,
    TransactionType,
)
from .services import (
    calculate_cash_in_hand,
    calculate_net_balance,
    calculate_payment_method_balances,
    calculate_total_cash_in,
    calculate_total_cash_out,
    calculate_total_overdue,
    calculate_total_payable_due,
    calculate_total_receivable_due,
    create_cash_in_transaction,
    create_cash_out_transaction,
    create_due_payment,
    create_opening_balance,
    delete_due_payment,
    get_accounts_dashboard_metrics,
    get_accounts_report_data,
    update_due_payment,
)
from .templatetags.finance_tags import money


User = get_user_model()


class FinanceTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="finance-test@example.com",
            email="finance-test@example.com",
            password="Admin@100%",
        )
        self.cash_in_category = TransactionCategory.objects.create(
            name="Test Cash In",
            category_type=CategoryType.CASH_IN,
        )
        self.cash_out_category = TransactionCategory.objects.create(
            name="Test Cash Out",
            category_type=CategoryType.CASH_OUT,
        )
        self.both_category = TransactionCategory.objects.create(
            name="Test Both",
            category_type=CategoryType.BOTH,
        )

    def grant_permissions(self, *codenames):
        permissions = Permission.objects.filter(
            content_type__app_label="finance",
            codename__in=codenames,
        )
        self.user.user_permissions.add(*permissions)
        return permissions

    def cash_data(self, category, amount="100.00", **extra):
        return {
            "transaction_date": timezone.localdate().isoformat(),
            "category": str(category.pk),
            "description": "  Test description  ",
            "amount": amount,
            "payment_method": PaymentMethod.CASH,
            "reference": "  REF-001  ",
            **extra,
        }

    def due_data(self, *, due_type=DueType.RECEIVABLE, amount="1000.00", **extra):
        return {
            "due_date": timezone.localdate().isoformat(),
            "due_type": due_type,
            "party_name": "  Test Party  ",
            "phone": "  01700000000  ",
            "description": "  Test due  ",
            "original_amount": amount,
            "due_deadline": "",
            "reference": "  DUE-001  ",
            "notes": "  Notes  ",
            **extra,
        }

    def payment_data(self, amount="100.00", **extra):
        return {
            "payment_date": timezone.localdate().isoformat(),
            "amount": amount,
            "payment_method": PaymentMethod.CASH,
            "reference": "  PAY-001  ",
            "notes": "  Payment note  ",
            **extra,
        }


class DashboardFinanceTests(FinanceTestBase):
    def test_dashboard_requires_login(self):
        from django.urls import reverse

        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders_for_authenticated_user(self):
        self.grant_permissions("view_cashtransaction")
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accounts")


class FinanceTemplateRenderingTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_accounts_sidebar_is_visible_and_expanded_for_authorized_user(self):
        self.grant_permissions("view_cashtransaction")
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accounts")
        self.assertContains(response, "Overview")
        self.assertContains(response, "All Transactions")
        self.assertContains(response, "menu-open")

    def test_accounts_sidebar_is_hidden_without_finance_permissions(self):
        self.grant_non_finance_dashboard_permission()
        response = self.client.get(reverse("dashboard_home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "finance:dashboard")
        self.assertNotContains(response, ">Accounts<")

    def grant_non_finance_dashboard_permission(self):
        permission = Permission.objects.filter(content_type__app_label="sitepages", codename="view_sale").first()
        if permission is None:
            permission = Permission.objects.filter(content_type__app_label="sitepages").first()
        self.user.user_permissions.add(permission)

    def test_cash_in_and_due_navigation_active_on_nested_pages(self):
        self.grant_permissions("view_cashtransaction", "add_cashtransaction", "view_dueaccount", "add_dueaccount")
        response = self.client.get(reverse("finance:cash_in_create"))
        self.assertContains(response, "Cash In")
        self.assertContains(response, "Save Cash In")
        response = self.client.get(reverse("finance:due_create"))
        self.assertContains(response, "Receivable: money the business will receive")

    def test_lists_render_headings_totals_empty_states_and_filter_pagination(self):
        self.grant_permissions("view_cashtransaction", "view_dueaccount", "view_transactioncategory")
        response = self.client.get(reverse("finance:cash_out_list"), {"search": "missing", "page": "1"})
        self.assertContains(response, "Payment Method")
        self.assertContains(response, "Total Cash Out")
        self.assertContains(response, "No Cash Out entries found")
        response = self.client.get(reverse("finance:due_list"))
        self.assertContains(response, "Original Amount")
        self.assertContains(response, "Remaining Amount")
        response = self.client.get(reverse("finance:category_list"))
        self.assertContains(response, "Transaction Count")

    def test_due_detail_hides_payment_action_when_fully_paid(self):
        self.grant_permissions("view_dueaccount", "add_duepayment")
        due = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Paid Party",
            original_amount=Decimal("100.00"),
        )
        DuePayment.objects.create(due=due, amount=Decimal("100.00"))
        response = self.client.get(reverse("finance:due_detail", args=[due.pk]))
        self.assertNotContains(response, "Add Payment")
        self.assertContains(response, "Payment History")

    def test_forms_show_field_and_non_field_errors_and_delete_uses_post_csrf(self):
        self.grant_permissions("add_cashtransaction", "view_cashtransaction", "delete_cashtransaction")
        response = self.client.post(reverse("finance:cash_in_create"), {"amount": "0"})
        self.assertContains(response, "This field is required")
        self.assertContains(response, "Amount must be greater than zero")
        transaction = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("25.00"),
        )
        response = self.client.get(reverse("finance:cash_in_delete", args=[transaction.pk]))
        self.assertContains(response, '<form method="post"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_money_filter_formats_decimal_and_none(self):
        self.assertEqual(money(Decimal("1250.5")), "৳1,250.50")
        self.assertEqual(money(None), "৳0.00")


class AccountsMetricsTests(FinanceTestBase):
    def test_dashboard_view_supplies_all_required_metrics_and_labels(self):
        self.grant_permissions("view_cashtransaction")
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        for key in (
            "today_sales",
            "current_month_sales",
            "last_month_sales",
            "today_cash_in",
            "today_cash_out",
            "total_cash_in",
            "total_cash_out",
            "net_balance",
            "cash_in_hand",
            "total_receivable_due",
            "total_payable_due",
            "total_overdue",
            "overdue_receivable",
            "overdue_payable",
            "payment_method_balances",
            "recent_cash_in",
            "recent_cash_out",
            "recent_dues",
        ):
            with self.subTest(key=key):
                self.assertIn(key, response.context)
        for label in ("Today Sales", "Net Balance", "Receivable Due", "Overdue", "Payment Method Balances"):
            self.assertContains(response, label)

    def make_sale(self, sale_date, amount, suffix):
        order = Order.objects.create(
            order_id=f"METRICS{suffix:02d}",
            full_name="Metrics Customer",
            phone="01700000000",
            email="metrics@example.com",
            address="Metrics address",
            district="Dhaka",
            total_amount=amount,
            status=Order.Status.PENDING,
        )
        order.status = Order.Status.CONFIRMED
        order.save()
        sale = Sale.objects.get(order=order)
        sale.total_amount = amount
        sale.sale_date = timezone.make_aware(datetime.combine(sale_date, datetime.min.time()))
        sale.save(update_fields=["total_amount", "sale_date"])
        return sale

    def test_dashboard_metrics_use_valid_sales_and_calendar_months(self):
        with mock.patch("finance.services.timezone.localdate", return_value=date(2026, 1, 15)):
            self.make_sale(date(2026, 1, 15), Decimal("300.00"), 1)
            self.make_sale(date(2025, 12, 20), Decimal("200.00"), 2)
            CashTransaction.objects.create(
                transaction_type=TransactionType.CASH_IN,
                category=self.cash_in_category,
                transaction_date=date(2026, 1, 15),
                amount=Decimal("999.00"),
            )
            metrics = get_accounts_dashboard_metrics()
        self.assertEqual(metrics["today_sales"], Decimal("300.00"))
        self.assertEqual(metrics["current_month_sales"], Decimal("300.00"))
        self.assertEqual(metrics["last_month_sales"], Decimal("200.00"))

    def test_dashboard_cash_due_and_payment_method_metrics_are_zero_safe(self):
        today = timezone.localdate()
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            transaction_date=today,
            payment_method=PaymentMethod.CASH,
            amount=Decimal("1000.00"),
        )
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            transaction_date=today - timedelta(days=2),
            payment_method=PaymentMethod.BKASH,
            amount=Decimal("500.00"),
        )
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_OUT,
            category=self.cash_out_category,
            transaction_date=today,
            payment_method=PaymentMethod.CASH,
            amount=Decimal("250.00"),
        )
        receivable = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Receivable metrics",
            original_amount=Decimal("1000.00"),
            due_date=today - timedelta(days=5),
            due_deadline=today - timedelta(days=1),
        )
        payable = DueAccount.objects.create(
            due_type=DueType.PAYABLE,
            party_name="Payable metrics",
            original_amount=Decimal("600.00"),
            due_deadline=today + timedelta(days=2),
        )
        DuePayment.objects.create(due=receivable, amount=Decimal("400.00"))
        metrics = get_accounts_dashboard_metrics()
        self.assertEqual(metrics["today_cash_in"], Decimal("1000.00"))
        self.assertEqual(metrics["today_cash_out"], Decimal("250.00"))
        self.assertEqual(metrics["total_cash_in"], Decimal("1500.00"))
        self.assertEqual(metrics["total_cash_out"], Decimal("250.00"))
        self.assertEqual(metrics["net_balance"], Decimal("1250.00"))
        self.assertEqual(metrics["cash_in_hand"], Decimal("750.00"))
        self.assertEqual(metrics["total_receivable_due"], Decimal("600.00"))
        self.assertEqual(metrics["total_payable_due"], Decimal("600.00"))
        self.assertEqual(metrics["total_overdue"], Decimal("600.00"))
        self.assertEqual(metrics["overdue_receivable"], Decimal("600.00"))
        self.assertEqual(metrics["overdue_payable"], Decimal("0.00"))
        self.assertEqual(set(metrics["payment_method_balances"]), {choice.value for choice in PaymentMethod})
        self.assertEqual(metrics["payment_method_balances"][PaymentMethod.BKASH]["balance"], Decimal("500.00"))
        self.assertEqual(metrics["payment_method_balances"][PaymentMethod.CARD]["balance"], Decimal("0.00"))
        self.assertEqual({due.pk for due in metrics["recent_dues"]}, {receivable.pk, payable.pk})

    def test_recent_activity_is_limited_and_paid_dues_are_excluded(self):
        for index in range(12):
            CashTransaction.objects.create(
                transaction_type=TransactionType.CASH_IN,
                category=self.cash_in_category,
                amount=Decimal("10.00"),
                description=f"Recent {index}",
            )
        due = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Paid metrics",
            original_amount=Decimal("10.00"),
        )
        DuePayment.objects.create(due=due, amount=Decimal("10.00"))
        metrics = get_accounts_dashboard_metrics()
        self.assertEqual(len(metrics["recent_cash_in"]), 10)
        self.assertEqual(len(metrics["recent_cash_out"]), 0)
        self.assertEqual(len(metrics["recent_dues"]), 0)


class AccountsReportTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def report_filters(self, **overrides):
        values = {
            "start_date": timezone.localdate().replace(day=1),
            "end_date": timezone.localdate(),
            "category": self.cash_in_category,
            "transaction_type": "",
            "payment_method": "",
            "due_type": "",
            "search": "",
        }
        values.update(overrides)
        return values

    def test_report_filter_form_defaults_and_rejects_reversed_dates(self):
        form = AccountsReportFilterForm()
        self.assertEqual(form.initial["start_date"], timezone.localdate().replace(day=1))
        self.assertEqual(form.initial["end_date"], timezone.localdate())
        invalid = AccountsReportFilterForm(data={"start_date": "2026-02-01", "end_date": "2026-01-01"})
        self.assertFalse(invalid.is_valid())
        self.assertIn("End date cannot be earlier", str(invalid.non_field_errors()))
        self.assertEqual([value for value, _ in invalid.fields["payment_method"].choices], ["", *[choice.value for choice in PaymentMethod]])

    def test_report_summary_filters_and_separates_due_payments(self):
        today = timezone.localdate()
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            transaction_date=today,
            payment_method=PaymentMethod.CASH,
            description="report cash",
            amount=Decimal("100.00"),
        )
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_OUT,
            category=self.cash_out_category,
            transaction_date=today,
            payment_method=PaymentMethod.BANK,
            amount=Decimal("40.00"),
        )
        receivable = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Report Receivable",
            original_amount=Decimal("500.00"),
            due_date=today,
        )
        DuePayment.objects.create(due=receivable, payment_date=today, amount=Decimal("125.00"))
        data = get_accounts_report_data(filters=self.report_filters(category=None))
        self.assertEqual(data["summary"]["total_cash_in"], Decimal("100.00"))
        self.assertEqual(data["summary"]["total_cash_out"], Decimal("40.00"))
        self.assertEqual(data["summary"]["net_cash_flow"], Decimal("60.00"))
        self.assertEqual(data["summary"]["receivable_due_created"], Decimal("500.00"))
        self.assertEqual(data["summary"]["due_payments_received"], Decimal("125.00"))
        self.assertEqual(data["summary"]["due_payments_paid"], Decimal("0.00"))
        self.assertEqual(data["payment_method_summary"][PaymentMethod.CASH]["balance"], Decimal("100.00"))
        self.assertEqual(data["cash_in_by_category"][0]["transaction_count"], 1)

    def test_report_view_paginates_transactions_and_preserves_filters(self):
        self.grant_permissions("view_cashtransaction")
        for index in range(51):
            CashTransaction.objects.create(
                transaction_type=TransactionType.CASH_IN,
                category=self.cash_in_category,
                amount=Decimal("1.00"),
                description="report page",
            )
        response = self.client.get(
            reverse("finance:reports"),
            {"start_date": "2020-01-01", "end_date": "2030-01-01", "search": "report", "page": "2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["transaction_page_obj"].paginator.count, 51)
        self.assertEqual(len(response.context["report_transactions"]), 1)
        self.assertIn("search=report", response.context["pagination_query"])
        self.assertNotIn("page=", response.context["pagination_query"])
        self.assertContains(response, "Due payments are reported separately")
        self.assertContains(response, "Cash In by Category")


class DuePaymentIntegrationTests(FinanceTestBase):
    def create_due(self, due_type=DueType.RECEIVABLE, amount="1000.00"):
        return DueAccount.objects.create(
            due_type=due_type,
            party_name="Integration Party",
            original_amount=Decimal(amount),
            reference="DUE-REF",
        )

    def test_receivable_and_payable_payments_create_linked_transactions(self):
        receivable = self.create_due(DueType.RECEIVABLE)
        payment = create_due_payment(
            due=receivable,
            payment_date=timezone.localdate(),
            amount=Decimal("300.00"),
            payment_method=PaymentMethod.CASH,
            reference="PAY-REF",
            created_by=self.user,
        )
        transaction = payment.cash_transaction
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_IN)
        self.assertEqual(transaction.category.name, "Due Collection")
        self.assertEqual(transaction.amount, Decimal("300.00"))
        self.assertEqual(transaction.transaction_date, payment.payment_date)
        self.assertEqual(transaction.payment_method, payment.payment_method)
        self.assertEqual(transaction.reference, "PAY-REF")
        self.assertEqual(transaction.created_by, self.user)
        self.assertEqual(transaction.source_type, TransactionSource.DUE_PAYMENT)
        self.assertEqual(transaction.due_payment.pk, payment.pk)

        payable = self.create_due(DueType.PAYABLE)
        payable_payment = create_due_payment(
            due=payable,
            payment_date=timezone.localdate(),
            amount=Decimal("250.00"),
            payment_method=PaymentMethod.BANK,
            created_by=self.user,
        )
        self.assertEqual(payable_payment.cash_transaction.transaction_type, TransactionType.CASH_OUT)
        self.assertEqual(payable_payment.cash_transaction.category.name, "Due Payment")
        self.assertEqual(payable_payment.cash_transaction.reference, "DUE-REF")

    def test_payment_update_synchronizes_one_transaction_and_legacy_payment_is_repaired(self):
        due = self.create_due()
        payment = create_due_payment(
            due=due,
            payment_date=timezone.localdate(),
            amount=Decimal("300.00"),
            payment_method=PaymentMethod.CASH,
            created_by=self.user,
        )
        transaction_id = payment.cash_transaction_id
        updated = update_due_payment(
            payment,
            payment_date=timezone.localdate() - timedelta(days=1),
            amount=Decimal("400.00"),
            payment_method=PaymentMethod.BKASH,
            reference="UPDATED",
            notes="Updated note",
        )
        self.assertEqual(updated.cash_transaction_id, transaction_id)
        updated_transaction = CashTransaction.objects.get(pk=transaction_id)
        self.assertEqual(updated_transaction.amount, Decimal("400.00"))
        self.assertEqual(updated_transaction.payment_method, PaymentMethod.BKASH)
        self.assertEqual(updated_transaction.reference, "UPDATED")
        self.assertEqual(updated_transaction.transaction_date, updated.payment_date)
        self.assertEqual(CashTransaction.objects.filter(due_payment=updated).count(), 1)

        legacy_due = self.create_due(amount="500.00")
        legacy_payment = DuePayment.objects.create(
            due=legacy_due,
            payment_date=timezone.localdate(),
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
            created_by=self.user,
        )
        self.assertIsNone(legacy_payment.cash_transaction_id)
        repaired = update_due_payment(
            legacy_payment,
            payment_date=legacy_payment.payment_date,
            amount=Decimal("150.00"),
            payment_method=PaymentMethod.CASH,
            reference="REPAIRED",
        )
        self.assertIsNotNone(repaired.cash_transaction_id)
        self.assertEqual(repaired.cash_transaction.amount, Decimal("150.00"))

    def test_payment_delete_removes_only_linked_generated_transaction(self):
        due = self.create_due()
        payment = create_due_payment(
            due=due,
            payment_date=timezone.localdate(),
            amount=Decimal("300.00"),
            payment_method=PaymentMethod.CASH,
        )
        transaction_id = payment.cash_transaction_id
        delete_due_payment(payment)
        self.assertFalse(DuePayment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(CashTransaction.objects.filter(pk=transaction_id).exists())
        self.assertTrue(DueAccount.objects.filter(pk=due.pk).exists())
        self.assertEqual(due.refresh_from_db(), None)
        self.assertEqual(due.paid_amount, Decimal("0.00"))

    def test_invalid_link_blocks_delete_and_creation_rolls_back(self):
        due = self.create_due()
        payment = create_due_payment(
            due=due,
            payment_date=timezone.localdate(),
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
        )
        transaction = payment.cash_transaction
        transaction.source_type = TransactionSource.MANUAL
        transaction.save(update_fields=["source_type"])
        with self.assertRaises(ValidationError):
            delete_due_payment(payment)
        self.assertTrue(DuePayment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(CashTransaction.objects.filter(pk=transaction.pk).exists())

        rollback_due = self.create_due()
        with mock.patch.object(CashTransaction, "save", side_effect=ValidationError("transaction failure")):
            with self.assertRaises(ValidationError):
                create_due_payment(
                    due=rollback_due,
                    payment_date=timezone.localdate(),
                    amount=Decimal("100.00"),
                    payment_method=PaymentMethod.CASH,
                )
        self.assertFalse(DuePayment.objects.filter(due=rollback_due).exists())

    def test_generated_transactions_are_rejected_by_manual_edit_and_delete_urls(self):
        self.client.force_login(self.user)
        self.grant_permissions("view_cashtransaction", "change_cashtransaction", "delete_cashtransaction")
        due = self.create_due()
        payment = create_due_payment(
            due=due,
            payment_date=timezone.localdate(),
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
        )
        response = self.client.get(reverse("finance:cash_in_update", args=[payment.cash_transaction_id]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("finance:cash_in_delete", args=[payment.cash_transaction_id]))
        self.assertEqual(response.status_code, 404)


class OpeningBalanceTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_opening_balance_form_and_service_map_direction_to_source(self):
        form = OpeningBalanceForm(
            data={
                "date": timezone.localdate().isoformat(),
                "amount": "2000.00",
                "payment_method": PaymentMethod.CASH,
                "description": "Opening cash",
                "reference": "OPEN-1",
                "balance_direction": "positive",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        opening = create_opening_balance(
            balance_date=form.cleaned_data["date"],
            amount=form.cleaned_data["amount"],
            payment_method=form.cleaned_data["payment_method"],
            description=form.cleaned_data["description"],
            reference=form.cleaned_data["reference"],
            balance_direction=form.cleaned_data["balance_direction"],
            created_by=self.user,
        )
        self.assertEqual(opening.transaction_type, TransactionType.CASH_IN)
        self.assertEqual(opening.category.name, "Opening Balance")
        self.assertEqual(opening.source_type, TransactionSource.OPENING_BALANCE)
        self.assertEqual(opening.created_by, self.user)
        negative = create_opening_balance(
            balance_date=timezone.localdate(),
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.BANK,
            balance_direction="negative",
            created_by=self.user,
        )
        self.assertEqual(negative.transaction_type, TransactionType.CASH_OUT)

    def test_opening_balance_view_requires_add_permission_and_redirects_after_post(self):
        url = reverse("finance:opening_balance")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.grant_permissions("add_cashtransaction", "view_cashtransaction")
        response = self.client.post(
            url,
            {
                "date": timezone.localdate().isoformat(),
                "amount": "1000.00",
                "payment_method": PaymentMethod.CASH,
                "description": "Opening",
                "reference": "",
                "balance_direction": "positive",
            },
        )
        self.assertRedirects(response, reverse("finance:transaction_list"))
        self.assertTrue(CashTransaction.objects.filter(source_type=TransactionSource.OPENING_BALANCE).exists())


class CashInFormTests(FinanceTestBase):
    def test_valid_cash_in_form(self):
        form = CashInForm(data=self.cash_data(self.cash_in_category))
        self.assertTrue(form.is_valid(), form.errors)
        transaction = form.save()
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_IN)
        self.assertEqual(transaction.description, "Test description")
        self.assertEqual(transaction.reference, "REF-001")

    def test_cash_out_only_category_is_rejected(self):
        form = CashInForm(data=self.cash_data(self.cash_out_category))
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_inactive_category_is_rejected(self):
        self.cash_in_category.is_active = False
        self.cash_in_category.save()
        form = CashInForm(data=self.cash_data(self.cash_in_category))
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_zero_and_negative_amounts_are_rejected(self):
        for amount in ("0.00", "-1.00"):
            with self.subTest(amount=amount):
                form = CashInForm(data=self.cash_data(self.cash_in_category, amount=amount))
                self.assertFalse(form.is_valid())
                self.assertIn("amount", form.errors)

    def test_transaction_type_is_forced_even_when_posted(self):
        form = CashInForm(
            data=self.cash_data(
                self.cash_in_category,
                transaction_type=TransactionType.CASH_OUT,
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("transaction_type", form.fields)
        transaction = form.save()
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_IN)

    def test_existing_inactive_category_remains_available_during_edit(self):
        transaction = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("100.00"),
        )
        self.cash_in_category.is_active = False
        self.cash_in_category.save()
        form = CashInForm(instance=transaction, data=self.cash_data(self.cash_in_category))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(self.cash_in_category, form.fields["category"].queryset)


class CashOutFormTests(FinanceTestBase):
    def test_valid_cash_out_form(self):
        form = CashOutForm(data=self.cash_data(self.cash_out_category))
        self.assertTrue(form.is_valid(), form.errors)
        transaction = form.save()
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_OUT)

    def test_cash_in_only_category_is_rejected(self):
        form = CashOutForm(data=self.cash_data(self.cash_in_category))
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_inactive_category_is_rejected(self):
        self.cash_out_category.is_active = False
        self.cash_out_category.save()
        form = CashOutForm(data=self.cash_data(self.cash_out_category))
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_transaction_type_is_forced_even_when_posted(self):
        form = CashOutForm(
            data=self.cash_data(
                self.cash_out_category,
                transaction_type=TransactionType.CASH_IN,
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
        transaction = form.save()
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_OUT)


class DueAccountFormTests(FinanceTestBase):
    def test_valid_receivable_due(self):
        form = DueAccountForm(data=self.due_data())
        self.assertTrue(form.is_valid(), form.errors)
        due = form.save()
        self.assertEqual(due.due_type, DueType.RECEIVABLE)
        self.assertEqual(due.party_name, "Test Party")
        self.assertEqual(due.phone, "01700000000")

    def test_valid_payable_due_and_readable_choices(self):
        form = DueAccountForm(data=self.due_data(due_type=DueType.PAYABLE))
        self.assertTrue(form.is_valid(), form.errors)
        labels = dict(form.fields["due_type"].choices)
        self.assertEqual(labels[DueType.PAYABLE], "Payable — Money we need to pay")

    def test_zero_amount_is_rejected(self):
        form = DueAccountForm(data=self.due_data(amount="0.00"))
        self.assertFalse(form.is_valid())
        self.assertIn("original_amount", form.errors)

    def test_deadline_before_due_date_is_rejected(self):
        today = timezone.localdate()
        form = DueAccountForm(
            data=self.due_data(
                due_date=(today - timedelta(days=1)).isoformat(),
                due_deadline=(today - timedelta(days=2)).isoformat(),
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("due_deadline", form.errors)

    def test_original_amount_cannot_be_reduced_below_paid_amount(self):
        due = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Paid Party",
            original_amount=Decimal("1000.00"),
        )
        DuePayment.objects.create(due=due, amount=Decimal("400.00"))
        form = DueAccountForm(
            instance=due,
            data=self.due_data(amount="300.00", party_name="Paid Party"),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("original_amount", form.errors)


class DuePaymentFormTests(FinanceTestBase):
    def create_due(self, amount="1000.00"):
        return DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Payment Party",
            original_amount=Decimal(amount),
        )

    def test_valid_partial_payment_assigns_due_server_side(self):
        due = self.create_due()
        form = DuePaymentForm(data=self.payment_data("400.00"), due=due)
        self.assertEqual(form.remaining_amount, Decimal("1000.00"))
        self.assertTrue(form.is_valid(), form.errors)
        payment = form.save()
        self.assertEqual(payment.due, due)
        self.assertEqual(payment.reference, "PAY-001")

    def test_full_payment_is_accepted(self):
        due = self.create_due()
        form = DuePaymentForm(data=self.payment_data("1000.00"), due=due)
        self.assertTrue(form.is_valid(), form.errors)

    def test_overpayment_error_includes_available_amount(self):
        due = self.create_due()
        DuePayment.objects.create(due=due, amount=Decimal("600.00"))
        form = DuePaymentForm(data=self.payment_data("401.00"), due=due)
        self.assertFalse(form.is_valid())
        self.assertIn("৳400.00", str(form.errors))

    def test_zero_payment_is_rejected(self):
        form = DuePaymentForm(data=self.payment_data("0.00"), due=self.create_due())
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test_fully_paid_due_rejects_new_payment(self):
        due = self.create_due()
        DuePayment.objects.create(due=due, amount=Decimal("1000.00"))
        form = DuePaymentForm(data=self.payment_data("1.00"), due=due)
        self.assertFalse(form.is_valid())
        self.assertIn("৳0.00", str(form.errors))

    def test_editing_payment_excludes_current_amount(self):
        due = self.create_due("10000.00")
        DuePayment.objects.create(due=due, amount=Decimal("2000.00"))
        current_payment = DuePayment.objects.create(due=due, amount=Decimal("3000.00"))
        form = DuePaymentForm(
            instance=current_payment,
            data=self.payment_data("8000.00"),
            due=due,
        )
        self.assertEqual(form.remaining_amount, Decimal("8000.00"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_due_account_is_rejected(self):
        with self.assertRaises(ValueError):
            DuePaymentForm(data=self.payment_data(), due=None)


class TransactionCategoryFormTests(FinanceTestBase):
    def test_valid_category(self):
        form = TransactionCategoryForm(
            data={"name": "  New Category  ", "category_type": CategoryType.CASH_IN, "is_active": "on"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        category = form.save()
        self.assertEqual(category.name, "New Category")

    def test_whitespace_only_name_is_rejected(self):
        form = TransactionCategoryForm(
            data={"name": "   ", "category_type": CategoryType.CASH_IN, "is_active": "on"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_case_insensitive_duplicate_is_rejected(self):
        form = TransactionCategoryForm(
            data={"name": " test cash in ", "category_type": CategoryType.CASH_IN, "is_active": "on"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_editing_same_category_without_name_change_is_allowed(self):
        form = TransactionCategoryForm(
            instance=self.cash_in_category,
            data={
                "name": self.cash_in_category.name,
                "category_type": self.cash_in_category.category_type,
                "is_active": "on",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)


class FinanceServiceTests(FinanceTestBase):
    def test_cash_services_force_correct_transaction_types(self):
        cash_in = create_cash_in_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_in_category,
            description="  In  ",
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
            reference="  IN-1  ",
            created_by=self.user,
        )
        cash_out = create_cash_out_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_out_category,
            description="  Out  ",
            amount=Decimal("40.00"),
            payment_method=PaymentMethod.CASH,
            reference="  OUT-1  ",
            created_by=self.user,
        )
        self.assertEqual(cash_in.transaction_type, TransactionType.CASH_IN)
        self.assertEqual(cash_out.transaction_type, TransactionType.CASH_OUT)
        self.assertEqual(cash_in.description, "In")
        self.assertEqual(cash_out.reference, "OUT-1")

    def test_cash_service_rejects_invalid_category_type(self):
        with self.assertRaises(ValidationError):
            create_cash_in_transaction(
                transaction_date=timezone.localdate(),
                category=self.cash_out_category,
                description="Invalid",
                amount=Decimal("10.00"),
                payment_method=PaymentMethod.CASH,
            )

    def test_due_payment_service_creates_and_rejects_overpayment(self):
        due = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Service Party",
            original_amount=Decimal("1000.00"),
        )
        payment = create_due_payment(
            due=due,
            payment_date=timezone.localdate(),
            amount=Decimal("600.00"),
            payment_method=PaymentMethod.BANK,
        )
        self.assertEqual(payment.amount, Decimal("600.00"))
        with self.assertRaises(ValidationError):
            create_due_payment(
                due=due,
                payment_date=timezone.localdate(),
                amount=Decimal("400.01"),
                payment_method=PaymentMethod.CASH,
            )

    def test_update_due_payment_excludes_current_amount(self):
        due = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Update Party",
            original_amount=Decimal("10000.00"),
        )
        DuePayment.objects.create(due=due, amount=Decimal("2000.00"))
        current_payment = DuePayment.objects.create(due=due, amount=Decimal("3000.00"))
        updated = update_due_payment(
            current_payment,
            payment_date=timezone.localdate(),
            amount=Decimal("8000.00"),
            payment_method=PaymentMethod.CASH,
        )
        self.assertEqual(updated.amount, Decimal("8000.00"))

    def test_delete_payment_leaves_due_account_intact(self):
        due = DueAccount.objects.create(
            due_type=DueType.PAYABLE,
            party_name="Delete Party",
            original_amount=Decimal("1000.00"),
        )
        payment = DuePayment.objects.create(due=due, amount=Decimal("100.00"))
        self.assertTrue(delete_due_payment(payment))
        self.assertTrue(DueAccount.objects.filter(pk=due.pk).exists())
        self.assertFalse(DuePayment.objects.filter(pk=payment.pk).exists())

    def test_empty_cash_totals_return_decimal_zero(self):
        self.assertEqual(calculate_total_cash_in(), Decimal("0.00"))
        self.assertEqual(calculate_total_cash_out(), Decimal("0.00"))
        self.assertIsInstance(calculate_total_cash_in(), Decimal)

    def test_cash_in_hand_and_net_balance_use_expected_methods(self):
        create_cash_in_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_in_category,
            description="Cash sale",
            amount=Decimal("1000.00"),
            payment_method=PaymentMethod.CASH,
        )
        create_cash_in_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_in_category,
            description="Bank sale",
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.BANK,
        )
        create_cash_out_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_out_category,
            description="Cash expense",
            amount=Decimal("300.00"),
            payment_method=PaymentMethod.CASH,
        )
        create_cash_out_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_out_category,
            description="Bank expense",
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.BANK,
        )
        self.assertEqual(calculate_total_cash_in(), Decimal("1500.00"))
        self.assertEqual(calculate_total_cash_out(), Decimal("400.00"))
        self.assertEqual(calculate_net_balance(), Decimal("1100.00"))
        self.assertEqual(calculate_cash_in_hand(), Decimal("700.00"))

    def test_payment_method_balance_contains_every_method(self):
        create_cash_in_transaction(
            transaction_date=timezone.localdate(),
            category=self.cash_in_category,
            description="Cash",
            amount=Decimal("1000.00"),
            payment_method=PaymentMethod.CASH,
        )
        balances = calculate_payment_method_balances()
        self.assertEqual(set(balances), {method.value for method in PaymentMethod})
        self.assertEqual(balances[PaymentMethod.CASH]["cash_in"], Decimal("1000.00"))
        self.assertEqual(balances[PaymentMethod.BANK]["balance"], Decimal("0.00"))

    def test_due_calculations_subtract_payments_and_find_overdue_balance(self):
        receivable = DueAccount.objects.create(
            due_type=DueType.RECEIVABLE,
            party_name="Receivable",
            original_amount=Decimal("1000.00"),
        )
        payable = DueAccount.objects.create(
            due_type=DueType.PAYABLE,
            party_name="Payable",
            original_amount=Decimal("500.00"),
        )
        overdue = DueAccount.objects.create(
            due_date=timezone.localdate() - timedelta(days=5),
            due_type=DueType.RECEIVABLE,
            party_name="Overdue",
            original_amount=Decimal("800.00"),
            due_deadline=timezone.localdate() - timedelta(days=1),
        )
        create_due_payment(
            due=receivable,
            payment_date=timezone.localdate(),
            amount=Decimal("200.00"),
            payment_method=PaymentMethod.CASH,
        )
        create_due_payment(
            due=payable,
            payment_date=timezone.localdate(),
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
        )
        create_due_payment(
            due=overdue,
            payment_date=timezone.localdate(),
            amount=Decimal("300.00"),
            payment_method=PaymentMethod.CASH,
        )
        self.assertEqual(calculate_total_receivable_due(), Decimal("1300.00"))
        self.assertEqual(calculate_total_payable_due(), Decimal("400.00"))
        self.assertEqual(calculate_total_overdue(), Decimal("500.00"))
        self.assertEqual(calculate_total_overdue(due_type=DueType.PAYABLE), Decimal("0.00"))


class FinanceUrlAndPermissionTests(FinanceTestBase):
    def test_all_named_finance_urls_reverse(self):
        url_cases = {
            "finance:dashboard": {},
            "finance:transaction_list": {},
            "finance:cash_in_list": {},
            "finance:cash_in_create": {},
            "finance:cash_in_update": {"pk": 1},
            "finance:cash_in_delete": {"pk": 1},
            "finance:cash_out_list": {},
            "finance:cash_out_create": {},
            "finance:cash_out_update": {"pk": 1},
            "finance:cash_out_delete": {"pk": 1},
            "finance:due_list": {},
            "finance:due_create": {},
            "finance:due_detail": {"pk": 1},
            "finance:due_update": {"pk": 1},
            "finance:due_delete": {"pk": 1},
            "finance:due_payment_create": {"due_pk": 1},
            "finance:due_payment_update": {"due_pk": 1, "pk": 1},
            "finance:due_payment_delete": {"due_pk": 1, "pk": 1},
            "finance:category_list": {},
            "finance:category_create": {},
            "finance:category_update": {"pk": 1},
            "finance:category_delete": {"pk": 1},
            "finance:reports": {},
        }
        for name, kwargs in url_cases.items():
            with self.subTest(name=name):
                self.assertTrue(reverse(name, kwargs=kwargs).startswith("/dashboard/accounts/"))

    def test_accounts_permission_matrix_uses_user_facing_accounts_label(self):
        ensure_default_roles()
        accounts_row = next(row for row in get_permission_matrix() if row["key"] == "accounts")
        self.assertEqual(accounts_row["label"], "Accounts")
        for action in ("view", "add", "change", "delete"):
            self.assertEqual(len(accounts_row["permissions"][action]), 4)

        admin_role = Group.objects.get(name="admins")
        self.assertTrue(admin_role.permissions.filter(content_type__app_label="finance").exists())
        for role_name in ("customers", "content_managers", "catalog_managers"):
            role = Group.objects.get(name=role_name)
            self.assertFalse(role.permissions.filter(content_type__app_label="finance").exists())

    def test_anonymous_user_cannot_access_accounts_list_or_write_pages(self):
        urls = (
            reverse("finance:transaction_list"),
            reverse("finance:cash_in_create"),
            reverse("finance:due_list"),
            reverse("finance:category_create"),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("auth_login"), response.url)

    def test_view_permission_is_required_server_side(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:transaction_list"))
        self.assertEqual(response.status_code, 302)
        self.grant_permissions("view_cashtransaction")
        response = self.client.get(reverse("finance:transaction_list"))
        self.assertEqual(response.status_code, 200)

    def test_accounts_dashboard_requires_an_accounts_view_permission(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("finance:dashboard")).status_code, 302)
        self.grant_permissions("view_dueaccount")
        self.assertEqual(self.client.get(reverse("finance:dashboard")).status_code, 200)

    def test_add_change_and_delete_permissions_are_separate(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:cash_in_create"))
        self.assertEqual(response.status_code, 302)

        self.grant_permissions("add_cashtransaction")
        self.assertEqual(self.client.get(reverse("finance:cash_in_create")).status_code, 200)

        transaction = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("10.00"),
        )
        self.assertEqual(self.client.get(reverse("finance:cash_in_update", args=[transaction.pk])).status_code, 302)
        self.grant_permissions("change_cashtransaction", "delete_cashtransaction")
        self.assertEqual(self.client.get(reverse("finance:cash_in_update", args=[transaction.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("finance:cash_in_delete", args=[transaction.pk])).status_code, 200)

    def test_superuser_can_access_accounts_pages(self):
        superuser = User.objects.create_superuser(
            username="finance-superuser@example.com",
            email="finance-superuser@example.com",
            password="Admin@100%",
        )
        self.client.force_login(superuser)
        for url in (
            reverse("finance:dashboard"),
            reverse("finance:transaction_list"),
            reverse("finance:due_list"),
            reverse("finance:category_list"),
            reverse("finance:reports"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class CashTransactionViewTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_cash_in_create_uses_service_and_ignores_posted_type(self):
        self.grant_permissions("add_cashtransaction", "view_cashtransaction")
        response = self.client.post(
            reverse("finance:cash_in_create"),
            self.cash_data(self.cash_in_category, transaction_type=TransactionType.CASH_OUT),
        )
        self.assertRedirects(response, reverse("finance:cash_in_list"))
        transaction = CashTransaction.objects.latest("id")
        self.assertEqual(transaction.transaction_type, TransactionType.CASH_IN)
        self.assertEqual(transaction.created_by, self.user)

    def test_cash_out_create_uses_fixed_cash_out_type(self):
        self.grant_permissions("add_cashtransaction", "view_cashtransaction")
        response = self.client.post(
            reverse("finance:cash_out_create"),
            self.cash_data(self.cash_out_category, transaction_type=TransactionType.CASH_IN),
        )
        self.assertRedirects(response, reverse("finance:cash_out_list"))
        self.assertEqual(CashTransaction.objects.latest("id").transaction_type, TransactionType.CASH_OUT)

    def test_cash_lists_are_type_scoped_and_fixed_type_query_is_ignored(self):
        self.grant_permissions("view_cashtransaction")
        cash_in = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            description="cash in record",
            amount=Decimal("10.00"),
        )
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_OUT,
            category=self.cash_out_category,
            description="cash out record",
            amount=Decimal("20.00"),
        )
        response = self.client.get(
            reverse("finance:cash_in_list"),
            {"transaction_type": TransactionType.CASH_OUT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["transactions"]), [cash_in])

    def test_transaction_search_filters_and_pagination_preserve_query(self):
        self.grant_permissions("view_cashtransaction")
        for index in range(21):
            CashTransaction.objects.create(
                transaction_type=TransactionType.CASH_IN,
                category=self.cash_in_category,
                description=f"Needle {index}",
                amount=Decimal("10.00"),
                reference=f"R-{index}",
                created_by=self.user,
            )
        response = self.client.get(
            reverse("finance:cash_in_list"),
            {"search": "Needle", "page": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertEqual(response.context["filtered_total"], Decimal("210.00"))
        self.assertIn("search=Needle", response.context["pagination_query"])
        self.assertNotIn("page=", response.context["pagination_query"])

    def test_invalid_and_reversed_date_filters_do_not_crash(self):
        self.grant_permissions("view_cashtransaction")
        invalid = self.client.get(reverse("finance:transaction_list"), {"start_date": "not-a-date"})
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Invalid start date filter was ignored.")
        reversed_dates = self.client.get(
            reverse("finance:transaction_list"),
            {"start_date": "2026-01-02", "end_date": "2026-01-01"},
        )
        self.assertEqual(reversed_dates.status_code, 200)
        self.assertContains(reversed_dates, "End date cannot be earlier than start date")

    def test_cash_in_and_cash_out_urls_cannot_cross_edit_or_delete_types(self):
        self.grant_permissions("change_cashtransaction", "delete_cashtransaction")
        cash_in = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("10.00"),
        )
        cash_out = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_OUT,
            category=self.cash_out_category,
            amount=Decimal("10.00"),
        )
        self.assertEqual(self.client.get(reverse("finance:cash_out_update", args=[cash_in.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("finance:cash_in_update", args=[cash_out.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("finance:cash_out_delete", args=[cash_in.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("finance:cash_in_delete", args=[cash_out.pk])).status_code, 404)

    def test_delete_requires_post(self):
        self.grant_permissions("view_cashtransaction", "delete_cashtransaction")
        transaction = CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("10.00"),
        )
        self.assertEqual(self.client.get(reverse("finance:cash_in_delete", args=[transaction.pk])).status_code, 200)
        self.assertTrue(CashTransaction.objects.filter(pk=transaction.pk).exists())
        response = self.client.post(reverse("finance:cash_in_delete", args=[transaction.pk]))
        self.assertRedirects(response, reverse("finance:cash_in_list"))
        self.assertFalse(CashTransaction.objects.filter(pk=transaction.pk).exists())


class DueViewTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def create_due(self, **kwargs):
        defaults = {
            "due_type": DueType.RECEIVABLE,
            "party_name": "View Party",
            "phone": "01700000000",
            "description": "View due",
            "original_amount": Decimal("1000.00"),
        }
        defaults.update(kwargs)
        return DueAccount.objects.create(**defaults)

    def test_due_list_filters_status_and_search(self):
        self.grant_permissions("view_dueaccount")
        due = self.create_due(party_name="Searchable Party")
        DuePayment.objects.create(due=due, amount=Decimal("400.00"))
        response = self.client.get(reverse("finance:due_list"), {"status": "partially_paid", "search": "Searchable"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["filtered_totals"]["remaining_total"], Decimal("600.00"))

    def test_due_detail_shows_payment_history(self):
        self.grant_permissions("view_dueaccount")
        due = self.create_due()
        DuePayment.objects.create(due=due, amount=Decimal("400.00"))
        response = self.client.get(reverse("finance:due_detail", args=[due.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "400.00")

    def test_due_create_sets_created_by(self):
        self.grant_permissions("add_dueaccount", "view_dueaccount")
        response = self.client.post(reverse("finance:due_create"), self.due_data())
        self.assertEqual(response.status_code, 302)
        due = DueAccount.objects.latest("id")
        self.assertEqual(due.created_by, self.user)

    def test_due_delete_with_history_is_blocked_and_empty_due_can_delete(self):
        self.grant_permissions("delete_dueaccount", "view_dueaccount")
        with_payment = self.create_due(party_name="Has Payment")
        DuePayment.objects.create(due=with_payment, amount=Decimal("100.00"))
        response = self.client.post(reverse("finance:due_delete", args=[with_payment.pk]), follow=True)
        self.assertTrue(DueAccount.objects.filter(pk=with_payment.pk).exists())
        self.assertContains(response, "payment history already exists")

        empty_due = self.create_due(party_name="Empty Due")
        response = self.client.post(reverse("finance:due_delete", args=[empty_due.pk]))
        self.assertRedirects(response, reverse("finance:due_list"))
        self.assertFalse(DueAccount.objects.filter(pk=empty_due.pk).exists())

    def test_due_payment_create_update_delete_and_url_scoping(self):
        self.grant_permissions("view_dueaccount", "add_duepayment", "change_duepayment", "delete_duepayment")
        due = self.create_due()
        other_due = self.create_due(party_name="Other Due")
        response = self.client.post(
            reverse("finance:due_payment_create", args=[due.pk]),
            self.payment_data("300.00"),
        )
        self.assertRedirects(response, reverse("finance:due_detail", args=[due.pk]))
        payment = DuePayment.objects.get(due=due)
        self.assertEqual(payment.created_by, self.user)
        self.assertEqual(
            self.client.get(reverse("finance:due_payment_update", args=[other_due.pk, payment.pk])).status_code,
            404,
        )
        response = self.client.post(
            reverse("finance:due_payment_update", args=[due.pk, payment.pk]),
            self.payment_data("400.00"),
        )
        self.assertRedirects(response, reverse("finance:due_detail", args=[due.pk]))
        response = self.client.get(reverse("finance:due_payment_delete", args=[due.pk, payment.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("finance:due_payment_delete", args=[due.pk, payment.pk]))
        self.assertRedirects(response, reverse("finance:due_detail", args=[due.pk]))
        self.assertTrue(DueAccount.objects.filter(pk=due.pk).exists())
        self.assertFalse(DuePayment.objects.filter(pk=payment.pk).exists())

    def test_fully_paid_due_rejects_new_payment(self):
        self.grant_permissions("view_dueaccount", "add_duepayment")
        due = self.create_due()
        DuePayment.objects.create(due=due, amount=Decimal("1000.00"))
        response = self.client.get(reverse("finance:due_payment_create", args=[due.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("finance:due_detail", args=[due.pk]))


class CategoryAndReportsViewTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_category_list_filter_and_crud_permissions(self):
        self.grant_permissions("view_transactioncategory")
        response = self.client.get(reverse("finance:category_list"), {"is_active": "true", "search": "Test"})
        self.assertEqual(response.status_code, 200)
        self.grant_permissions("add_transactioncategory", "change_transactioncategory", "delete_transactioncategory")
        response = self.client.post(
            reverse("finance:category_create"),
            {"name": "Temporary Category", "category_type": CategoryType.CASH_IN, "is_active": "on"},
        )
        self.assertRedirects(response, reverse("finance:category_list"))

    def test_used_category_cannot_be_deleted_and_unused_category_can(self):
        self.grant_permissions("view_transactioncategory", "delete_transactioncategory")
        CashTransaction.objects.create(
            transaction_type=TransactionType.CASH_IN,
            category=self.cash_in_category,
            amount=Decimal("10.00"),
        )
        response = self.client.post(reverse("finance:category_delete", args=[self.cash_in_category.pk]), follow=True)
        self.assertTrue(TransactionCategory.objects.filter(pk=self.cash_in_category.pk).exists())
        self.assertContains(response, "Mark it inactive instead")
        response = self.client.post(reverse("finance:category_delete", args=[self.both_category.pk]))
        self.assertRedirects(response, reverse("finance:category_list"))
        self.assertFalse(TransactionCategory.objects.filter(pk=self.both_category.pk).exists())

    def test_reports_requires_any_accounts_view_permission(self):
        self.assertEqual(self.client.get(reverse("finance:reports")).status_code, 302)
        self.grant_permissions("view_dueaccount")
        self.assertEqual(self.client.get(reverse("finance:reports")).status_code, 200)
