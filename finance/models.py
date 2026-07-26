from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Lower
from django.utils import timezone


ZERO_AMOUNT = Decimal("0.00")


class TransactionType(models.TextChoices):
    CASH_IN = "cash_in", "Cash In"
    CASH_OUT = "cash_out", "Cash Out"


class TransactionSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    DUE_PAYMENT = "due_payment", "Due Payment"
    OPENING_BALANCE = "opening_balance", "Opening Balance"


class CategoryType(models.TextChoices):
    CASH_IN = "cash_in", "Cash In"
    CASH_OUT = "cash_out", "Cash Out"
    BOTH = "both", "Both"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    BKASH = "bkash", "bKash"
    NAGAD = "nagad", "Nagad"
    ROCKET = "rocket", "Rocket"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class DueType(models.TextChoices):
    RECEIVABLE = "receivable", "Receivable"
    PAYABLE = "payable", "Payable"


class TransactionCategory(models.Model):
    name = models.CharField(max_length=100)
    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.BOTH,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category_type", "name"]
        verbose_name = "Account Category"
        verbose_name_plural = "Account Categories"
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "category_type",
                name="finance_category_type_name_ci_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.get_category_type_display()}"

    def clean(self):
        self.name = (self.name or "").strip()
        super().clean()

        if not self.name or not self.category_type:
            return

        duplicate = TransactionCategory.objects.filter(
            category_type=self.category_type,
            name__iexact=self.name,
        )
        if self.pk:
            duplicate = duplicate.exclude(pk=self.pk)
        if duplicate.exists():
            raise ValidationError({"name": "A category with this name and type already exists."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CashTransaction(models.Model):
    transaction_date = models.DateField(default=timezone.localdate)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField(max_length=150, blank=True)
    source_type = models.CharField(
        max_length=30,
        choices=TransactionSource.choices,
        default=TransactionSource.MANUAL,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_cash_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-transaction_date", "-id"]
        verbose_name = "Cash Transaction"
        verbose_name_plural = "Cash Transactions"
        indexes = [
            models.Index(fields=["transaction_date"], name="finance_txn_date_idx"),
            models.Index(fields=["transaction_type"], name="finance_txn_type_idx"),
            models.Index(fields=["payment_method"], name="finance_txn_method_idx"),
            models.Index(
                fields=["transaction_type", "transaction_date"],
                name="finance_txn_type_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=ZERO_AMOUNT),
                name="finance_cash_transaction_amount_gt_zero",
            ),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.category.name} - ৳{self.amount:,.2f}"

    def clean(self):
        self.reference = (self.reference or "").strip()
        super().clean()

        errors = {}
        if self.amount is not None and self.amount <= ZERO_AMOUNT:
            errors["amount"] = "Amount must be greater than zero."

        if self.category_id:
            category = self.category
            if self.transaction_type == TransactionType.CASH_IN and category.category_type not in (
                CategoryType.CASH_IN,
                CategoryType.BOTH,
            ):
                errors["category"] = "Cash In transactions require a Cash In or Both category."
            elif self.transaction_type == TransactionType.CASH_OUT and category.category_type not in (
                CategoryType.CASH_OUT,
                CategoryType.BOTH,
            ):
                errors["category"] = "Cash Out transactions require a Cash Out or Both category."

            if self._state.adding and not category.is_active:
                errors["category"] = "Inactive categories cannot be used for new transactions."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DueAccount(models.Model):
    due_date = models.DateField(default=timezone.localdate)
    due_type = models.CharField(max_length=20, choices=DueType.choices)
    party_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    description = models.TextField(blank=True)
    original_amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_deadline = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_due_accounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-due_date", "-id"]
        verbose_name = "Due Account"
        verbose_name_plural = "Due Accounts"
        indexes = [
            models.Index(fields=["due_date"], name="finance_due_date_idx"),
            models.Index(fields=["due_type"], name="finance_due_type_idx"),
            models.Index(fields=["due_deadline"], name="finance_due_deadline_idx"),
            models.Index(
                fields=["due_type", "due_date"],
                name="finance_due_type_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(original_amount__gt=ZERO_AMOUNT),
                name="finance_due_original_amount_gt_zero",
            ),
        ]

    def __str__(self):
        return f"{self.party_name} — {self.get_due_type_display()} — ৳{self.original_amount:,.2f}"

    def clean(self):
        self.party_name = (self.party_name or "").strip()
        self.phone = (self.phone or "").strip()
        self.reference = (self.reference or "").strip()
        super().clean()

        errors = {}
        if self.original_amount is not None and self.original_amount <= ZERO_AMOUNT:
            errors["original_amount"] = "Original amount must be greater than zero."
        if self.due_deadline and self.due_date and self.due_deadline < self.due_date:
            errors["due_deadline"] = "Due deadline cannot be earlier than the due date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def paid_amount(self):
        if not self.pk:
            return ZERO_AMOUNT

        annotated_amount = getattr(self, "_paid_amount", None)
        if annotated_amount is not None:
            return annotated_amount

        return self.payments.aggregate(total=Sum("amount"))["total"] or ZERO_AMOUNT

    @property
    def balance_due(self):
        balance = self.original_amount - self.paid_amount
        return max(balance, ZERO_AMOUNT)

    @property
    def status(self):
        balance = self.balance_due
        if balance == ZERO_AMOUNT:
            return "paid"

        if self.due_deadline and self.due_deadline < timezone.localdate():
            return "overdue"

        if self.paid_amount > ZERO_AMOUNT:
            return "partially_paid"
        return "unpaid"

    @property
    def status_display(self):
        return {
            "unpaid": "Unpaid",
            "partially_paid": "Partially Paid",
            "paid": "Paid",
            "overdue": "Overdue",
        }[self.status]


class DuePaymentManager(models.Manager):
    def create_with_locked_due(self, *, due, **kwargs):
        using = self.db
        due_model = self.model._meta.get_field("due").remote_field.model
        due_id = due.pk if isinstance(due, due_model) else due
        kwargs["due"] = due_id

        with transaction.atomic(using=using):
            locked_due = (
                due_model._default_manager.using(using)
                .select_for_update()
                .get(pk=due_id)
            )
            payment = self.model(due=locked_due, **{key: value for key, value in kwargs.items() if key != "due"})
            payment.save(using=using)
        return payment


class DuePayment(models.Model):
    due = models.ForeignKey(
        DueAccount,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    cash_transaction = models.OneToOneField(
        CashTransaction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="due_payment",
    )
    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_due_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DuePaymentManager()

    class Meta:
        ordering = ["-payment_date", "-id"]
        verbose_name = "Due Payment"
        verbose_name_plural = "Due Payments"
        indexes = [
            models.Index(fields=["payment_date"], name="finance_payment_date_idx"),
            models.Index(fields=["payment_method"], name="finance_payment_method_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=ZERO_AMOUNT),
                name="finance_due_payment_amount_gt_zero",
            ),
        ]

    def __str__(self):
        return f"{self.due.party_name} — ৳{self.amount:,.2f} — {self.payment_date}"

    def available_amount(self):
        if not self.due_id:
            return ZERO_AMOUNT

        paid_by_other_payments = (
            DuePayment.objects.filter(due_id=self.due_id)
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
            or ZERO_AMOUNT
        )
        return max(self.due.original_amount - paid_by_other_payments, ZERO_AMOUNT)

    def clean(self):
        self.reference = (self.reference or "").strip()
        super().clean()

        errors = {}
        if self.amount is not None and self.amount <= ZERO_AMOUNT:
            errors["amount"] = "Payment amount must be greater than zero."
        if self.due_id and self.amount is not None and self.amount > self.available_amount():
            errors["amount"] = "Payment cannot be greater than the remaining due balance."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
