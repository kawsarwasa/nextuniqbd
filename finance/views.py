from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, CharField, Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from sitepages.permissions import DashboardPermissionMixin
from sitepages.dashboard_pagination import build_dashboard_pagination_context

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
    TransactionType,
)
from .services import (
    create_cash_in_transaction,
    create_cash_out_transaction,
    create_due_payment,
    delete_due_payment,
    empty_accounts_report_data,
    get_accounts_dashboard_metrics,
    get_accounts_report_data,
    create_opening_balance,
    update_cash_transaction,
    update_due_payment,
)


ZERO_AMOUNT = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
PAGE_SIZE = 20

ACCOUNTS_VIEW_PERMISSIONS = (
    "finance.view_transactioncategory",
    "finance.view_cashtransaction",
    "finance.view_dueaccount",
    "finance.view_duepayment",
)


def user_can_view_accounts(user):
    return bool(
        getattr(user, "is_superuser", False)
        or any(user.has_perm(permission) for permission in ACCOUNTS_VIEW_PERMISSIONS)
    )


class AccountsAnyViewPermissionMixin(DashboardPermissionMixin):
    def has_permission(self):
        return user_can_view_accounts(self.request.user)


def _add_validation_error(form, error):
    if hasattr(error, "message_dict"):
        for field_name, field_errors in error.message_dict.items():
            for message in field_errors:
                form.add_error(field_name if field_name != "__all__" else None, message)
    else:
        form.add_error(None, error.messages)


def _parse_date_filter(request, parameter, label):
    value = (request.GET.get(parameter) or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        messages.error(request, f"Invalid {label} filter was ignored.")
        return None


def _filter_values(request, names):
    return {name: (request.GET.get(name) or "").strip() for name in names}


def _pagination_query(request):
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()


@login_required
def finance_dashboard(request):
    if not user_can_view_accounts(request.user):
        messages.error(request, "You do not have permission to access Accounts.")
        return redirect("dashboard_home")
    context = get_accounts_dashboard_metrics()
    return render(request, "dashboard/finance/dashboard.html", context)


class OpeningBalanceCreateView(DashboardPermissionMixin, View):
    permission_required = "finance.add_cashtransaction"
    template_name = "dashboard/finance/opening_balance_form.html"

    def render_form(self, request, form):
        return render(request, self.template_name, {"form": form, "page_title": "Opening Balance"})

    def get(self, request):
        return self.render_form(request, OpeningBalanceForm(initial={"date": timezone.localdate()}))

    def post(self, request):
        form = OpeningBalanceForm(request.POST)
        if form.is_valid():
            create_opening_balance(
                balance_date=form.cleaned_data["date"],
                amount=form.cleaned_data["amount"],
                payment_method=form.cleaned_data["payment_method"],
                description=form.cleaned_data["description"],
                reference=form.cleaned_data["reference"],
                balance_direction=form.cleaned_data["balance_direction"],
                created_by=request.user,
            )
            messages.success(request, "Opening Balance added successfully.", extra_tags="toast-create")
            return redirect("finance:transaction_list")
        return self.render_form(request, form)


class FinanceTransactionListView(DashboardPermissionMixin, View):
    permission_required = "finance.view_cashtransaction"
    template_name = "dashboard/finance/transaction_list.html"
    fixed_transaction_type = None
    page_title = "Transactions"

    def get_queryset(self, request):
        filters = _filter_values(
            request,
            ("start_date", "end_date", "transaction_type", "category", "payment_method", "search"),
        )
        start_date = _parse_date_filter(request, "start_date", "start date")
        end_date = _parse_date_filter(request, "end_date", "end date")
        if start_date and end_date and end_date < start_date:
            messages.error(request, "End date cannot be earlier than start date; the date range was ignored.")
            start_date = end_date = None

        queryset = CashTransaction.objects.select_related(
            "category", "created_by", "due_payment__due"
        )
        transaction_type = self.fixed_transaction_type
        if transaction_type is None:
            requested_type = filters["transaction_type"]
            if requested_type in {choice.value for choice in TransactionType}:
                transaction_type = requested_type
            elif requested_type:
                messages.error(request, "Invalid transaction type filter was ignored.")
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)

        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        category_id = filters["category"]
        if category_id:
            try:
                category_id = int(category_id)
            except ValueError:
                category_id = None
                messages.error(request, "Invalid category filter was ignored.")
            if category_id and TransactionCategory.objects.filter(pk=category_id).exists():
                queryset = queryset.filter(category_id=category_id)
            elif category_id:
                messages.error(request, "The selected category filter was ignored.")

        payment_method = filters["payment_method"]
        if payment_method:
            valid_methods = {choice.value for choice in PaymentMethod}
            if payment_method in valid_methods:
                queryset = queryset.filter(payment_method=payment_method)
            else:
                messages.error(request, "Invalid payment method filter was ignored.")

        search = filters["search"]
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search)
                | Q(reference__icontains=search)
                | Q(category__name__icontains=search)
                | Q(created_by__username__icontains=search)
                | Q(created_by__email__icontains=search)
            )

        self.filter_values = filters
        self.transaction_type_filter = transaction_type or ""
        self.filtered_total = (
            queryset.aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Value(ZERO_AMOUNT),
                    output_field=MONEY_FIELD,
                )
            )["total"]
            or ZERO_AMOUNT
        )
        return queryset.order_by(*CashTransaction._meta.ordering)

    def get_context_data(self, request, page_obj):
        allowed_types = [self.fixed_transaction_type] if self.fixed_transaction_type else [choice.value for choice in TransactionType]
        context = {
            "transactions": page_obj.object_list,
            "page_obj": page_obj,
            "page_title": self.page_title,
            "filtered_total": self.filtered_total,
            "transaction_total": self.filtered_total,
            "filter_values": self.filter_values,
            "transaction_type_filter": self.transaction_type_filter,
            "transaction_types": TransactionType.choices,
            "payment_methods": PaymentMethod.choices,
            "categories": TransactionCategory.objects.filter(
                category_type__in=allowed_types + [CategoryType.BOTH],
                is_active=True,
            ).order_by("name", "pk"),
            **build_dashboard_pagination_context(request, page_obj),
        }
        if self.fixed_transaction_type == TransactionType.CASH_IN:
            context["cash_in_total"] = self.filtered_total
        elif self.fixed_transaction_type == TransactionType.CASH_OUT:
            context["cash_out_total"] = self.filtered_total
        return context

    def get(self, request):
        queryset = self.get_queryset(request)
        paginator = Paginator(queryset, PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page"))
        return render(request, self.template_name, self.get_context_data(request, page_obj))


class TransactionListView(FinanceTransactionListView):
    page_title = "All Transactions"


class CashInListView(FinanceTransactionListView):
    fixed_transaction_type = TransactionType.CASH_IN
    template_name = "dashboard/finance/cash_in_list.html"
    page_title = "Cash In"


class CashOutListView(FinanceTransactionListView):
    fixed_transaction_type = TransactionType.CASH_OUT
    template_name = "dashboard/finance/cash_out_list.html"
    page_title = "Cash Out"


class CashTransactionCreateView(DashboardPermissionMixin, View):
    form_class = None
    service = None
    template_name = "dashboard/finance/cash_in_form.html"
    page_title = "Add Cash Transaction"
    submit_label = "Save"
    success_url_name = "finance:transaction_list"
    success_message = "Cash transaction added successfully."

    def get_form(self, data=None):
        return self.form_class(data=data)

    def render_form(self, request, form):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": self.page_title,
                "submit_label": self.submit_label,
            },
        )

    def get(self, request):
        return self.render_form(request, self.get_form())

    def post(self, request):
        form = self.get_form(request.POST)
        if form.is_valid():
            try:
                self.service(
                    transaction_date=form.cleaned_data["transaction_date"],
                    category=form.cleaned_data["category"],
                    description=form.cleaned_data["description"],
                    amount=form.cleaned_data["amount"],
                    payment_method=form.cleaned_data["payment_method"],
                    reference=form.cleaned_data["reference"],
                    created_by=request.user,
                )
            except ValidationError as error:
                _add_validation_error(form, error)
            else:
                messages.success(request, self.success_message, extra_tags="toast-create")
                return redirect(self.success_url_name)
        return self.render_form(request, form)


class CashInCreateView(CashTransactionCreateView):
    permission_required = "finance.add_cashtransaction"
    form_class = CashInForm
    service = staticmethod(create_cash_in_transaction)
    template_name = "dashboard/finance/cash_in_form.html"
    page_title = "Add Cash In"
    submit_label = "Save Cash In"
    success_url_name = "finance:cash_in_list"
    success_message = "Cash In entry added successfully."


class CashOutCreateView(CashTransactionCreateView):
    permission_required = "finance.add_cashtransaction"
    form_class = CashOutForm
    service = staticmethod(create_cash_out_transaction)
    template_name = "dashboard/finance/cash_out_form.html"
    page_title = "Add Cash Out"
    submit_label = "Save Cash Out"
    success_url_name = "finance:cash_out_list"
    success_message = "Cash Out entry added successfully."


class CashTransactionUpdateView(DashboardPermissionMixin, View):
    form_class = None
    template_name = "dashboard/finance/cash_in_form.html"
    page_title = "Edit Cash Transaction"
    submit_label = "Update"
    success_url_name = "finance:transaction_list"
    success_message = "Cash transaction updated successfully."

    def get_queryset(self):
        return CashTransaction.objects.select_related("category", "created_by", "due_payment__due").filter(
            transaction_type=self.expected_transaction_type,
            source_type="manual",
        )

    def get_object(self, pk):
        return get_object_or_404(self.get_queryset(), pk=pk)

    def get_form(self, instance, data=None):
        return self.form_class(instance=instance, data=data)

    def render_form(self, request, form):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": self.page_title,
                "submit_label": self.submit_label,
            },
        )

    def get(self, request, pk):
        instance = self.get_object(pk)
        return self.render_form(request, self.get_form(instance))

    def post(self, request, pk):
        instance = self.get_object(pk)
        form = self.get_form(instance, request.POST)
        if form.is_valid():
            try:
                updated = update_cash_transaction(
                    instance,
                    transaction_date=form.cleaned_data["transaction_date"],
                    category=form.cleaned_data["category"],
                    description=form.cleaned_data["description"],
                    amount=form.cleaned_data["amount"],
                    payment_method=form.cleaned_data["payment_method"],
                    reference=form.cleaned_data["reference"],
                )
            except ValidationError as error:
                _add_validation_error(form, error)
            else:
                messages.success(request, self.success_message, extra_tags="toast-edit")
                return redirect(self.success_url_name)
        return self.render_form(request, form)


class CashInUpdateView(CashTransactionUpdateView):
    permission_required = "finance.change_cashtransaction"
    expected_transaction_type = TransactionType.CASH_IN
    form_class = CashInForm
    template_name = "dashboard/finance/cash_in_form.html"
    page_title = "Edit Cash In"
    submit_label = "Update Cash In"
    success_url_name = "finance:cash_in_list"
    success_message = "Cash In entry updated successfully."


class CashOutUpdateView(CashTransactionUpdateView):
    permission_required = "finance.change_cashtransaction"
    expected_transaction_type = TransactionType.CASH_OUT
    form_class = CashOutForm
    template_name = "dashboard/finance/cash_out_form.html"
    page_title = "Edit Cash Out"
    submit_label = "Update Cash Out"
    success_url_name = "finance:cash_out_list"
    success_message = "Cash Out entry updated successfully."


class CashTransactionDeleteView(DashboardPermissionMixin, View):
    permission_required = None
    template_name = "dashboard/finance/confirm_delete.html"
    success_url_name = "finance:transaction_list"
    object_label = "cash transaction"

    def get_queryset(self):
        return CashTransaction.objects.filter(
            transaction_type=self.expected_transaction_type,
            source_type="manual",
        )

    def get_object(self, pk):
        return get_object_or_404(self.get_queryset(), pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk)
        return render(
            request,
            self.template_name,
            {
                "object": obj,
                "object_label": self.object_label,
                "object_description": str(obj),
                "page_title": f"Delete {self.object_label}",
                "cancel_url": reverse(self.success_url_name),
            },
        )

    def post(self, request, pk):
        obj = self.get_object(pk)
        label = str(obj)
        obj.delete()
        messages.success(request, f"{label} deleted successfully.", extra_tags="toast-delete")
        return redirect(self.success_url_name)


class CashInDeleteView(CashTransactionDeleteView):
    permission_required = "finance.delete_cashtransaction"
    expected_transaction_type = TransactionType.CASH_IN
    success_url_name = "finance:cash_in_list"
    object_label = "Cash In entry"


class CashOutDeleteView(CashTransactionDeleteView):
    permission_required = "finance.delete_cashtransaction"
    expected_transaction_type = TransactionType.CASH_OUT
    success_url_name = "finance:cash_out_list"
    object_label = "Cash Out entry"


def _due_payment_total_expression():
    payment_totals = (
        DuePayment.objects.filter(due_id=OuterRef("pk"))
        .order_by()
        .values("due_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    return Coalesce(
        Subquery(payment_totals, output_field=MONEY_FIELD),
        Value(ZERO_AMOUNT),
        output_field=MONEY_FIELD,
    )


def annotated_due_queryset():
    today = timezone.localdate()
    queryset = DueAccount.objects.select_related("created_by").annotate(paid_total=_due_payment_total_expression())
    queryset = queryset.annotate(
        remaining_total=Greatest(
            F("original_amount") - F("paid_total"),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        )
    )
    return queryset.annotate(
        status_value=Case(
            When(remaining_total__lte=ZERO_AMOUNT, then=Value("paid")),
            When(due_deadline__lt=today, remaining_total__gt=ZERO_AMOUNT, then=Value("overdue")),
            When(paid_total__gt=ZERO_AMOUNT, remaining_total__gt=ZERO_AMOUNT, then=Value("partially_paid")),
            default=Value("unpaid"),
            output_field=CharField(),
        )
    )


class DueListView(DashboardPermissionMixin, View):
    permission_required = "finance.view_dueaccount"
    template_name = "dashboard/finance/due_list.html"

    def get_queryset(self, request):
        filters = _filter_values(request, ("start_date", "end_date", "due_type", "status", "search"))
        start_date = _parse_date_filter(request, "start_date", "start date")
        end_date = _parse_date_filter(request, "end_date", "end date")
        if start_date and end_date and end_date < start_date:
            messages.error(request, "End date cannot be earlier than start date; the date range was ignored.")
            start_date = end_date = None

        queryset = annotated_due_queryset()
        due_type = filters["due_type"]
        if due_type in {choice.value for choice in DueType}:
            queryset = queryset.filter(due_type=due_type)
        elif due_type:
            messages.error(request, "Invalid due type filter was ignored.")

        status = filters["status"]
        if status in {"unpaid", "partially_paid", "paid", "overdue"}:
            queryset = queryset.filter(status_value=status)
        elif status:
            messages.error(request, "Invalid due status filter was ignored.")

        if start_date:
            queryset = queryset.filter(due_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(due_date__lte=end_date)

        search = filters["search"]
        if search:
            queryset = queryset.filter(
                Q(party_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(description__icontains=search)
                | Q(reference__icontains=search)
                | Q(notes__icontains=search)
            )

        self.filter_values = filters
        paid_total_expression = _due_payment_total_expression()
        remaining_total_expression = Greatest(
            F("original_amount") - paid_total_expression,
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        )
        self.filtered_totals = queryset.aggregate(
            original_total=Coalesce(Sum("original_amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
            paid_total=Coalesce(Sum(paid_total_expression), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
            remaining_total=Coalesce(Sum(remaining_total_expression), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        )
        return queryset.order_by(*DueAccount._meta.ordering)

    def get(self, request):
        queryset = self.get_queryset(request)
        page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
        context = {
            "dues": page_obj.object_list,
            "page_obj": page_obj,
            "filter_values": self.filter_values,
            "filtered_totals": {key: value or ZERO_AMOUNT for key, value in self.filtered_totals.items()},
            "due_types": DueType.choices,
            "status_choices": (
                ("unpaid", "Unpaid"),
                ("partially_paid", "Partially Paid"),
                ("paid", "Paid"),
                ("overdue", "Overdue"),
            ),
            **build_dashboard_pagination_context(request, page_obj),
        }
        context["original_amount_total"] = context["filtered_totals"]["original_total"]
        context["paid_amount_total"] = context["filtered_totals"]["paid_total"]
        context["remaining_amount_total"] = context["filtered_totals"]["remaining_total"]
        return render(request, self.template_name, context)


class DueAccountCreateView(DashboardPermissionMixin, View):
    permission_required = "finance.add_dueaccount"
    template_name = "dashboard/finance/due_form.html"

    def render_form(self, request, form, page_title="Add Due"):
        return render(request, self.template_name, {"form": form, "page_title": page_title, "submit_label": "Save Due"})

    def get(self, request):
        return self.render_form(request, DueAccountForm())

    def post(self, request):
        form = DueAccountForm(request.POST)
        if form.is_valid():
            due = form.save(commit=False)
            due.created_by = request.user
            due.save()
            messages.success(request, "Due entry added successfully.", extra_tags="toast-create")
            return redirect("finance:due_detail", pk=due.pk)
        return self.render_form(request, form)


class DueAccountUpdateView(DashboardPermissionMixin, View):
    permission_required = "finance.change_dueaccount"
    template_name = "dashboard/finance/due_form.html"

    def get_object(self, pk):
        return get_object_or_404(DueAccount, pk=pk)

    def render_form(self, request, form, page_title="Edit Due"):
        return render(request, self.template_name, {"form": form, "page_title": page_title, "submit_label": "Update Due"})

    def get(self, request, pk):
        due = self.get_object(pk)
        return self.render_form(request, DueAccountForm(instance=due), f"Edit Due: {due.party_name}")

    def post(self, request, pk):
        due = self.get_object(pk)
        form = DueAccountForm(request.POST, instance=due)
        if form.is_valid():
            due = form.save(commit=False)
            due.save()
            messages.success(request, "Due entry updated successfully.", extra_tags="toast-edit")
            return redirect("finance:due_detail", pk=due.pk)
        return self.render_form(request, form, f"Edit Due: {due.party_name}")


class DueDetailView(DashboardPermissionMixin, View):
    permission_required = "finance.view_dueaccount"
    template_name = "dashboard/finance/due_detail.html"

    def get(self, request, pk):
        due = get_object_or_404(
            annotated_due_queryset(),
            pk=pk,
        )
        page_obj = Paginator(
            due.payments.select_related("created_by").order_by("-payment_date", "-id"),
            PAGE_SIZE,
        ).get_page(request.GET.get("page"))
        context = {
            "due": due,
            "payments": page_obj.object_list,
            "page_obj": page_obj,
            "can_add_payment": request.user.is_superuser or request.user.has_perm("finance.add_duepayment"),
            "can_change_payment": request.user.is_superuser or request.user.has_perm("finance.change_duepayment"),
            "can_delete_payment": request.user.is_superuser or request.user.has_perm("finance.delete_duepayment"),
        }
        context.update(build_dashboard_pagination_context(request, page_obj))
        return render(
            request,
            self.template_name,
            context,
        )


class DueAccountDeleteView(DashboardPermissionMixin, View):
    permission_required = "finance.delete_dueaccount"
    template_name = "dashboard/finance/confirm_delete.html"

    def get(self, request, pk):
        due = get_object_or_404(DueAccount, pk=pk)
        return render(
            request,
            self.template_name,
            {
                "object": due,
                "object_label": "Due entry",
                "object_description": f'{due.party_name} ({due.get_due_type_display()})',
                "page_title": "Delete Due",
                "cancel_url": reverse("finance:due_detail", kwargs={"pk": due.pk}),
            },
        )

    def post(self, request, pk):
        with transaction.atomic():
            due = get_object_or_404(DueAccount.objects.select_for_update(), pk=pk)
            if due.payments.exists():
                messages.error(request, "This due cannot be deleted because payment history already exists.")
                return redirect("finance:due_detail", pk=due.pk)
            label = due.party_name
            due.delete()
        messages.success(request, f'"{label}" deleted successfully.', extra_tags="toast-delete")
        return redirect("finance:due_list")


class DuePaymentCreateView(DashboardPermissionMixin, View):
    permission_required = "finance.add_duepayment"
    template_name = "dashboard/finance/due_payment_form.html"

    def get_due(self, due_pk):
        return get_object_or_404(DueAccount, pk=due_pk)

    def render_form(self, request, due, form):
        return render(request, self.template_name, {"due": due, "form": form, "page_title": "Add Due Payment"})

    def redirect_if_fully_paid(self, request, due):
        if due.balance_due <= ZERO_AMOUNT:
            messages.error(request, "This due is already fully paid.")
            return redirect("finance:due_detail", pk=due.pk)
        return None

    def get(self, request, due_pk):
        due = self.get_due(due_pk)
        redirect_response = self.redirect_if_fully_paid(request, due)
        if redirect_response is not None:
            return redirect_response
        return self.render_form(request, due, DuePaymentForm(due=due))

    def post(self, request, due_pk):
        due = self.get_due(due_pk)
        redirect_response = self.redirect_if_fully_paid(request, due)
        if redirect_response is not None:
            return redirect_response
        form = DuePaymentForm(request.POST, due=due)
        if form.is_valid():
            try:
                payment = create_due_payment(
                    due=due,
                    payment_date=form.cleaned_data["payment_date"],
                    amount=form.cleaned_data["amount"],
                    payment_method=form.cleaned_data["payment_method"],
                    reference=form.cleaned_data["reference"],
                    notes=form.cleaned_data["notes"],
                    created_by=request.user,
                )
            except ValidationError as error:
                _add_validation_error(form, error)
            else:
                messages.success(request, "Due payment recorded successfully.", extra_tags="toast-create")
                return redirect("finance:due_detail", pk=payment.due_id)
        return self.render_form(request, due, form)


class DuePaymentUpdateView(DashboardPermissionMixin, View):
    permission_required = "finance.change_duepayment"
    template_name = "dashboard/finance/due_payment_form.html"

    def get_payment(self, due_pk, pk):
        return get_object_or_404(DuePayment.objects.select_related("due"), pk=pk, due_id=due_pk)

    def render_form(self, request, due, form):
        return render(request, self.template_name, {"due": due, "form": form, "page_title": "Edit Due Payment"})

    def get(self, request, due_pk, pk):
        payment = self.get_payment(due_pk, pk)
        return self.render_form(request, payment.due, DuePaymentForm(instance=payment, due=payment.due))

    def post(self, request, due_pk, pk):
        payment = self.get_payment(due_pk, pk)
        form = DuePaymentForm(request.POST, instance=payment, due=payment.due)
        if form.is_valid():
            try:
                updated = update_due_payment(
                    payment,
                    payment_date=form.cleaned_data["payment_date"],
                    amount=form.cleaned_data["amount"],
                    payment_method=form.cleaned_data["payment_method"],
                    reference=form.cleaned_data["reference"],
                    notes=form.cleaned_data["notes"],
                )
            except ValidationError as error:
                _add_validation_error(form, error)
            else:
                messages.success(request, "Due payment updated successfully.", extra_tags="toast-edit")
                return redirect("finance:due_detail", pk=updated.due_id)
        return self.render_form(request, payment.due, form)


class DuePaymentDeleteView(DashboardPermissionMixin, View):
    permission_required = "finance.delete_duepayment"
    template_name = "dashboard/finance/confirm_delete.html"

    def get_payment(self, due_pk, pk):
        return get_object_or_404(DuePayment.objects.select_related("due"), pk=pk, due_id=due_pk)

    def get(self, request, due_pk, pk):
        payment = self.get_payment(due_pk, pk)
        return render(
            request,
            self.template_name,
            {
                "object": payment,
                "object_label": "Due payment",
                "object_description": str(payment),
                "page_title": "Delete Due Payment",
                "cancel_url": reverse("finance:due_detail", kwargs={"pk": payment.due_id}),
            },
        )

    def post(self, request, due_pk, pk):
        payment = self.get_payment(due_pk, pk)
        due_id = payment.due_id
        try:
            delete_due_payment(payment)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Due payment deleted successfully.", extra_tags="toast-delete")
        return redirect("finance:due_detail", pk=due_id)


class TransactionCategoryListView(DashboardPermissionMixin, View):
    permission_required = "finance.view_transactioncategory"
    template_name = "dashboard/finance/category_list.html"

    def get(self, request):
        filters = _filter_values(request, ("category_type", "is_active", "search"))
        queryset = TransactionCategory.objects.annotate(transaction_total=Count("transactions"))
        if filters["category_type"] in {choice.value for choice in CategoryType}:
            queryset = queryset.filter(category_type=filters["category_type"])
        elif filters["category_type"]:
            messages.error(request, "Invalid category type filter was ignored.")
        if filters["is_active"] in {"true", "1", "yes"}:
            queryset = queryset.filter(is_active=True)
        elif filters["is_active"] in {"false", "0", "no"}:
            queryset = queryset.filter(is_active=False)
        elif filters["is_active"]:
            messages.error(request, "Invalid active status filter was ignored.")
        if filters["search"]:
            queryset = queryset.filter(name__icontains=filters["search"])
        queryset = queryset.order_by(*TransactionCategory._meta.ordering)
        page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "categories": page_obj.object_list,
                "page_obj": page_obj,
                "filter_values": filters,
                "category_types": CategoryType.choices,
                **build_dashboard_pagination_context(request, page_obj),
            },
        )


class TransactionCategoryCreateView(DashboardPermissionMixin, View):
    permission_required = "finance.add_transactioncategory"
    template_name = "dashboard/finance/category_form.html"

    def render_form(self, request, form, page_title="Add Category"):
        return render(request, self.template_name, {"form": form, "page_title": page_title, "submit_label": "Save Category"})

    def get(self, request):
        return self.render_form(request, TransactionCategoryForm())

    def post(self, request):
        form = TransactionCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account category added successfully.", extra_tags="toast-create")
            return redirect("finance:category_list")
        return self.render_form(request, form)


class TransactionCategoryUpdateView(DashboardPermissionMixin, View):
    permission_required = "finance.change_transactioncategory"
    template_name = "dashboard/finance/category_form.html"

    def get_object(self, pk):
        return get_object_or_404(TransactionCategory, pk=pk)

    def render_form(self, request, form, page_title="Edit Category"):
        return render(request, self.template_name, {"form": form, "page_title": page_title, "submit_label": "Update Category"})

    def get(self, request, pk):
        category = self.get_object(pk)
        return self.render_form(request, TransactionCategoryForm(instance=category), f"Edit Category: {category.name}")

    def post(self, request, pk):
        category = self.get_object(pk)
        form = TransactionCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Account category updated successfully.", extra_tags="toast-edit")
            return redirect("finance:category_list")
        return self.render_form(request, form, f"Edit Category: {category.name}")


class TransactionCategoryDeleteView(DashboardPermissionMixin, View):
    permission_required = "finance.delete_transactioncategory"

    def get(self, request, pk):
        category = get_object_or_404(TransactionCategory, pk=pk)
        return render(
            request,
            "dashboard/finance/confirm_delete.html",
            {
                "object": category,
                "object_label": "category",
                "object_description": category.name,
                "page_title": "Delete Category",
                "cancel_url": reverse("finance:category_list"),
            },
        )

    def post(self, request, pk):
        category = get_object_or_404(TransactionCategory, pk=pk)
        if category.transactions.exists():
            messages.error(request, "This category is already used by transactions. Mark it inactive instead of deleting it.")
            return redirect("finance:category_list")
        name = category.name
        try:
            category.delete()
        except ProtectedError:
            messages.error(request, "This category cannot be deleted because it is in use.")
        else:
            messages.success(request, f'"{name}" deleted successfully.', extra_tags="toast-delete")
        return redirect("finance:category_list")


class ReportsView(AccountsAnyViewPermissionMixin, View):
    template_name = "dashboard/finance/reports.html"

    def get(self, request):
        form = AccountsReportFilterForm(request.GET or None)
        report_data = empty_accounts_report_data()
        filters = {}
        valid = form.is_valid()
        if valid:
            filters = form.cleaned_data.copy()
            if "start_date" not in request.GET and "end_date" not in request.GET:
                today = timezone.localdate()
                filters["start_date"] = today.replace(day=1)
                filters["end_date"] = today
            report_data = get_accounts_report_data(filters=filters)

        transaction_page_obj = Paginator(report_data["transactions"], PAGE_SIZE).get_page(request.GET.get("page"))
        summary = report_data["summary"]
        return render(
            request,
            self.template_name,
            {
                **report_data,
                "form": form,
                "summary": summary,
                "report_transactions": transaction_page_obj.object_list,
                "transaction_page_obj": transaction_page_obj,
                **build_dashboard_pagination_context(request, transaction_page_obj),
                "report_start_date": filters.get("start_date"),
                "report_end_date": filters.get("end_date"),
            },
        )
