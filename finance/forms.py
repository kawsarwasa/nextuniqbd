from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

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


ZERO_AMOUNT = Decimal("0.00")


def _add_class(widget, class_name):
    classes = widget.attrs.get("class", "").split()
    if class_name not in classes:
        classes.append(class_name)
    widget.attrs["class"] = " ".join(classes)


class DashboardFormMixin:
    """Apply the dashboard's Bootstrap/AdminLTE field styling consistently."""

    DATE_FIELDS = {"date", "transaction_date", "due_date", "due_deadline", "payment_date", "start_date", "end_date"}
    MONEY_FIELDS = {"amount", "original_amount"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_dashboard_widgets()

    def apply_dashboard_widgets(self):
        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                _add_class(widget, "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                _add_class(widget, "form-check-input")
            else:
                _add_class(widget, "form-control")

            if field_name in self.DATE_FIELDS:
                widget.input_type = "date"

            if field_name in self.MONEY_FIELDS:
                widget.input_type = "number"
                widget.attrs.update({"step": "0.01", "min": "0.01"})


class DashboardModelForm(DashboardFormMixin, forms.ModelForm):
    pass


class _CashTransactionForm(DashboardModelForm):
    expected_transaction_type = None

    class Meta:
        model = CashTransaction
        fields = [
            "transaction_date",
            "category",
            "description",
            "amount",
            "payment_method",
            "reference",
        ]
        labels = {
            "transaction_date": "Date",
            "category": "Item",
            "description": "Description",
            "amount": "Amount",
            "payment_method": "Payment Method",
            "reference": "Reference",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_category_types = [self.expected_transaction_type, CategoryType.BOTH]
        category_queryset = TransactionCategory.objects.filter(
            Q(category_type__in=allowed_category_types, is_active=True)
        )

        if self.instance.pk and self.instance.category_id:
            current_category = self.instance.category
            if current_category.category_type in allowed_category_types:
                category_queryset = category_queryset | TransactionCategory.objects.filter(
                    pk=current_category.pk
                )

        self.fields["category"].queryset = category_queryset.order_by("name", "pk")

    def clean(self):
        cleaned_data = super().clean()
        expected_type = self.expected_transaction_type
        previous_transaction_type = self.instance.transaction_type
        if self.instance.pk and previous_transaction_type != expected_type:
            self.add_error(None, "This form cannot change a Cash In transaction into Cash Out, or vice versa.")
        self.instance.transaction_type = expected_type

        category = cleaned_data.get("category")
        allowed_category_types = {expected_type, CategoryType.BOTH}
        if category is not None:
            if category.category_type not in allowed_category_types:
                self.add_error("category", "Select a category that matches this transaction type.")

            existing_category_id = self.instance.category_id if self.instance.pk else None
            if not category.is_active and category.pk != existing_category_id:
                self.add_error("category", "Inactive categories cannot be selected for a new or changed transaction.")

        for field_name in ("description", "reference"):
            if field_name in cleaned_data and cleaned_data[field_name] is not None:
                cleaned_data[field_name] = cleaned_data[field_name].strip()

        self.instance.description = cleaned_data.get("description", "")
        self.instance.reference = cleaned_data.get("reference", "")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.transaction_type = self.expected_transaction_type
        instance.description = (self.cleaned_data.get("description") or "").strip()
        instance.reference = (self.cleaned_data.get("reference") or "").strip()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class CashInForm(_CashTransactionForm):
    expected_transaction_type = TransactionType.CASH_IN


class CashOutForm(_CashTransactionForm):
    expected_transaction_type = TransactionType.CASH_OUT


class DueAccountForm(DashboardModelForm):
    class Meta:
        model = DueAccount
        fields = [
            "due_date",
            "due_type",
            "party_name",
            "phone",
            "description",
            "original_amount",
            "due_deadline",
            "reference",
            "notes",
        ]
        labels = {
            "due_date": "Date",
            "due_type": "Due Type",
            "party_name": "Party Name",
            "phone": "Phone",
            "description": "Description",
            "original_amount": "Due Amount",
            "due_deadline": "Due Deadline",
            "reference": "Reference",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_type"].choices = [
            (DueType.RECEIVABLE, "Receivable — Money we will receive"),
            (DueType.PAYABLE, "Payable — Money we need to pay"),
        ]
        self.fields["original_amount"].min_value = Decimal("0.01")

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("party_name", "phone", "description", "reference", "notes"):
            if field_name in cleaned_data and cleaned_data[field_name] is not None:
                cleaned_data[field_name] = cleaned_data[field_name].strip()

        original_amount = cleaned_data.get("original_amount")
        if original_amount is not None and original_amount <= ZERO_AMOUNT:
            self.add_error("original_amount", "Due amount must be greater than zero.")

        due_date = cleaned_data.get("due_date")
        due_deadline = cleaned_data.get("due_deadline")
        if due_date and due_deadline and due_deadline < due_date:
            self.add_error("due_deadline", "Due deadline cannot be earlier than the due date.")

        if self.instance.pk and original_amount is not None:
            paid_amount = self.instance.paid_amount
            if original_amount < paid_amount:
                self.add_error(
                    "original_amount",
                    f"Due amount cannot be less than the amount already paid (৳{paid_amount:,.2f}).",
                )
        return cleaned_data


class DuePaymentForm(DashboardModelForm):
    class Meta:
        model = DuePayment
        fields = ["payment_date", "amount", "payment_method", "reference", "notes"]
        labels = {
            "payment_date": "Date",
            "amount": "Amount",
            "payment_method": "Payment Method",
            "reference": "Reference",
            "notes": "Notes",
        }

    def __init__(self, *args, due=None, **kwargs):
        if not isinstance(due, DueAccount) or not due.pk:
            raise ValueError("A saved DueAccount instance is required.")
        if kwargs.get("instance") is not None and kwargs["instance"].pk:
            instance = kwargs["instance"]
            if instance.due_id != due.pk:
                raise ValueError("The payment does not belong to the supplied DueAccount.")

        self.due = due
        super().__init__(*args, **kwargs)
        self.remaining_amount = self.calculate_remaining_amount()
        self.fields["amount"].min_value = Decimal("0.01")

    def calculate_remaining_amount(self):
        current_payment_id = self.instance.pk if self.instance and self.instance.pk else None
        paid_amount = (
            DuePayment.objects.filter(due_id=self.due.pk)
            .exclude(pk=current_payment_id)
            .aggregate(total=Sum("amount"))["total"]
            or ZERO_AMOUNT
        )
        return max(self.due.original_amount - paid_amount, ZERO_AMOUNT)

    def clean(self):
        cleaned_data = super().clean()
        self.instance.due = self.due
        for field_name in ("reference", "notes"):
            if field_name in cleaned_data and cleaned_data[field_name] is not None:
                cleaned_data[field_name] = cleaned_data[field_name].strip()

        self.remaining_amount = self.calculate_remaining_amount()
        amount = cleaned_data.get("amount")
        if amount is not None:
            if amount <= ZERO_AMOUNT:
                self.add_error("amount", "Payment amount must be greater than zero.")
            elif amount > self.remaining_amount:
                self.add_error(
                    "amount",
                    f"Payment cannot exceed the remaining amount of ৳{self.remaining_amount:,.2f}.",
                )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.due = self.due
        instance.reference = (self.cleaned_data.get("reference") or "").strip()
        instance.notes = (self.cleaned_data.get("notes") or "").strip()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class TransactionCategoryForm(DashboardModelForm):
    class Meta:
        model = TransactionCategory
        fields = ["name", "category_type", "is_active"]
        labels = {
            "name": "Category Name",
            "category_type": "Category Type",
            "is_active": "Active",
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Category name cannot be blank.")
        return name


class AccountsReportFilterForm(DashboardFormMixin, forms.Form):
    start_date = forms.DateField(required=False, label="Start Date")
    end_date = forms.DateField(required=False, label="End Date")
    transaction_type = forms.ChoiceField(
        required=False,
        label="Transaction Type",
        choices=[("", "All"), *TransactionType.choices],
    )
    category = forms.ModelChoiceField(
        required=False,
        label="Category",
        queryset=TransactionCategory.objects.none(),
        empty_label="All categories",
    )
    payment_method = forms.ChoiceField(
        required=False,
        label="Payment Method",
        choices=[("", "All"), *PaymentMethod.choices],
    )
    due_type = forms.ChoiceField(
        required=False,
        label="Due Type",
        choices=[("", "All"), *DueType.choices],
    )
    search = forms.CharField(required=False, label="Search")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = TransactionCategory.objects.order_by("name", "pk")
        if not self.is_bound:
            today = timezone.localdate()
            self.initial.setdefault("start_date", today.replace(day=1))
            self.initial.setdefault("end_date", today)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date cannot be earlier than start date.")
        cleaned_data["search"] = (cleaned_data.get("search") or "").strip()
        return cleaned_data


class OpeningBalanceForm(DashboardFormMixin, forms.Form):
    date = forms.DateField(label="Date")
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2, label="Amount")
    payment_method = forms.ChoiceField(label="Payment Method", choices=PaymentMethod.choices)
    description = forms.CharField(required=False, label="Description", widget=forms.Textarea(attrs={"rows": 3}))
    reference = forms.CharField(required=False, label="Reference", max_length=150)
    balance_direction = forms.ChoiceField(
        label="Balance Direction",
        choices=[("positive", "Positive Opening Balance"), ("negative", "Negative Opening Balance")],
        help_text="Enter a positive amount. The direction determines Cash In or Cash Out.",
    )

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_reference(self):
        return (self.cleaned_data.get("reference") or "").strip()
