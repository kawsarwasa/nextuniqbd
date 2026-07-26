from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, CharField, Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from sitepages.models import Order, Sale

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


ZERO_AMOUNT = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def _decimal_amount(value):
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Amount must be a valid monetary value.") from exc


def _cash_queryset(*, start_date=None, end_date=None, payment_method=None, category=None):
    queryset = CashTransaction.objects.all()
    if start_date is not None:
        queryset = queryset.filter(transaction_date__gte=start_date)
    if end_date is not None:
        queryset = queryset.filter(transaction_date__lte=end_date)
    if payment_method:
        queryset = queryset.filter(payment_method=payment_method)
    if category is not None:
        queryset = queryset.filter(category=category)
    return queryset


def _cash_total(queryset):
    total = queryset.aggregate(
        total=Coalesce(
            Sum("amount"),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        )
    )["total"]
    return total or ZERO_AMOUNT


def _get_category_for_write(category):
    if not isinstance(category, TransactionCategory) or not category.pk:
        raise ValidationError({"category": "A saved transaction category is required."})
    try:
        return TransactionCategory.objects.get(pk=category.pk)
    except TransactionCategory.DoesNotExist as exc:
        raise ValidationError({"category": "The selected transaction category no longer exists."}) from exc


def _validate_cash_category(category, transaction_type, *, current_category_id=None):
    category = _get_category_for_write(category)
    allowed_types = {
        TransactionType.CASH_IN: {CategoryType.CASH_IN, CategoryType.BOTH},
        TransactionType.CASH_OUT: {CategoryType.CASH_OUT, CategoryType.BOTH},
    }.get(transaction_type)
    if allowed_types is None:
        raise ValidationError("The cash transaction type is invalid.")
    if category.category_type not in allowed_types:
        raise ValidationError({"category": "The selected category does not match the transaction type."})
    if not category.is_active and category.pk != current_category_id:
        raise ValidationError({"category": "Inactive categories cannot be selected for a new or changed transaction."})
    return category


def _validate_positive_amount(amount, field_name="amount"):
    amount = _decimal_amount(amount)
    if amount <= ZERO_AMOUNT:
        raise ValidationError({field_name: "Amount must be greater than zero."})
    return amount


def _remaining_due_amount(due, *, exclude_payment_id=None):
    paid_amount = (
        DuePayment.objects.filter(due_id=due.pk)
        .exclude(pk=exclude_payment_id)
        .aggregate(total=Coalesce(Sum("amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD))["total"]
        or ZERO_AMOUNT
    )
    return max(due.original_amount - paid_amount, ZERO_AMOUNT)


def _validate_available_payment(amount, available_amount):
    amount = _validate_positive_amount(amount)
    if amount > available_amount:
        raise ValidationError(
            {"amount": f"Payment cannot exceed the remaining amount of ৳{available_amount:,.2f}."}
        )
    return amount


@transaction.atomic
def create_cash_in_transaction(
    *,
    transaction_date,
    category,
    description,
    amount,
    payment_method,
    reference="",
    created_by=None,
):
    category = _validate_cash_category(category, TransactionType.CASH_IN)
    cash_transaction = CashTransaction(
        transaction_date=transaction_date,
        transaction_type=TransactionType.CASH_IN,
        category=category,
        description=(description or "").strip(),
        amount=_validate_positive_amount(amount),
        payment_method=payment_method,
        reference=(reference or "").strip(),
        created_by=created_by,
        source_type=TransactionSource.MANUAL,
    )
    cash_transaction.full_clean()
    cash_transaction.save()
    return cash_transaction


@transaction.atomic
def create_cash_out_transaction(
    *,
    transaction_date,
    category,
    description,
    amount,
    payment_method,
    reference="",
    created_by=None,
):
    category = _validate_cash_category(category, TransactionType.CASH_OUT)
    cash_transaction = CashTransaction(
        transaction_date=transaction_date,
        transaction_type=TransactionType.CASH_OUT,
        category=category,
        description=(description or "").strip(),
        amount=_validate_positive_amount(amount),
        payment_method=payment_method,
        reference=(reference or "").strip(),
        created_by=created_by,
        source_type=TransactionSource.MANUAL,
    )
    cash_transaction.full_clean()
    cash_transaction.save()
    return cash_transaction


@transaction.atomic
def update_cash_transaction(
    cash_transaction,
    *,
    transaction_date,
    category,
    description,
    amount,
    payment_method,
    reference="",
):
    if not isinstance(cash_transaction, CashTransaction) or not cash_transaction.pk:
        raise ValidationError("A saved cash transaction is required.")
    if cash_transaction.source_type != TransactionSource.MANUAL:
        raise ValidationError("Generated transactions must be changed through their source record.")

    try:
        locked_transaction = (
            CashTransaction.objects.select_for_update()
            .select_related("category")
            .get(pk=cash_transaction.pk)
        )
    except CashTransaction.DoesNotExist as exc:
        raise ValidationError("The cash transaction no longer exists.") from exc

    category = _validate_cash_category(
        category,
        locked_transaction.transaction_type,
        current_category_id=locked_transaction.category_id,
    )
    locked_transaction.transaction_date = transaction_date
    locked_transaction.category = category
    locked_transaction.description = (description or "").strip()
    locked_transaction.amount = _validate_positive_amount(amount)
    locked_transaction.payment_method = payment_method
    locked_transaction.reference = (reference or "").strip()
    locked_transaction.full_clean()
    locked_transaction.save()
    return locked_transaction


@transaction.atomic
def create_due_payment(
    *,
    due,
    payment_date,
    amount,
    payment_method,
    reference="",
    notes="",
    created_by=None,
):
    due_id = getattr(due, "pk", None)
    if not due_id:
        raise ValidationError({"due": "A saved DueAccount is required."})
    try:
        with transaction.atomic():
            locked_due = DueAccount.objects.select_for_update().get(pk=due_id)
            payment_amount = _validate_available_payment(amount, _remaining_due_amount(locked_due))
            payment = DuePayment(
                due=locked_due,
                payment_date=payment_date,
                amount=payment_amount,
                payment_method=payment_method,
                reference=(reference or "").strip(),
                notes=(notes or "").strip(),
                created_by=created_by,
            )
            payment.full_clean()
            payment.save()
            cash_transaction = CashTransaction(**build_due_payment_transaction_data(payment))
            cash_transaction.full_clean()
            cash_transaction.save()
            payment.cash_transaction = cash_transaction
            payment.save(update_fields=["cash_transaction", "updated_at"])
            return payment
    except DueAccount.DoesNotExist as exc:
        raise ValidationError({"due": "The DueAccount no longer exists."}) from exc


@transaction.atomic
def update_due_payment(
    payment,
    *,
    payment_date,
    amount,
    payment_method,
    reference="",
    notes="",
):
    if not isinstance(payment, DuePayment) or not payment.pk:
        raise ValidationError("A saved DuePayment is required.")
    try:
        with transaction.atomic():
            locked_payment = DuePayment.objects.select_for_update().select_related("due").get(pk=payment.pk)
            locked_due = DueAccount.objects.select_for_update().get(pk=locked_payment.due_id)
            linked_transaction = None
            if locked_payment.cash_transaction_id:
                linked_transaction = CashTransaction.objects.select_for_update().get(
                    pk=locked_payment.cash_transaction_id
                )
                _validate_due_payment_transaction_link(locked_payment, linked_transaction)

            payment_amount = _validate_available_payment(
                amount,
                _remaining_due_amount(locked_due, exclude_payment_id=locked_payment.pk),
            )
            locked_payment.due = locked_due
            locked_payment.payment_date = payment_date
            locked_payment.amount = payment_amount
            locked_payment.payment_method = payment_method
            locked_payment.reference = (reference or "").strip()
            locked_payment.notes = (notes or "").strip()
            locked_payment.full_clean()
            locked_payment.save()

            transaction_data = build_due_payment_transaction_data(locked_payment)
            if linked_transaction is None:
                linked_transaction = CashTransaction(**transaction_data)
            else:
                for field_name, value in transaction_data.items():
                    setattr(linked_transaction, field_name, value)
            linked_transaction.full_clean()
            linked_transaction.save()
            if locked_payment.cash_transaction_id != linked_transaction.pk:
                locked_payment.cash_transaction = linked_transaction
                locked_payment.save(update_fields=["cash_transaction", "updated_at"])
            return locked_payment
    except (DuePayment.DoesNotExist, DueAccount.DoesNotExist) as exc:
        raise ValidationError("The payment or its DueAccount no longer exists.") from exc


@transaction.atomic
def delete_due_payment(payment):
    if not isinstance(payment, DuePayment) or not payment.pk:
        raise ValidationError("A saved DuePayment is required.")
    try:
        with transaction.atomic():
            locked_payment = DuePayment.objects.select_for_update().get(pk=payment.pk)
            DueAccount.objects.select_for_update().get(pk=locked_payment.due_id)
            linked_transaction = None
            if locked_payment.cash_transaction_id:
                linked_transaction = CashTransaction.objects.select_for_update().get(
                    pk=locked_payment.cash_transaction_id
                )
                _validate_due_payment_transaction_link(locked_payment, linked_transaction)
                locked_payment.cash_transaction = None
                locked_payment.save(update_fields=["cash_transaction", "updated_at"])
                linked_transaction.delete()
            locked_payment.delete()
            return True
    except (DuePayment.DoesNotExist, DueAccount.DoesNotExist) as exc:
        raise ValidationError("The payment or its DueAccount no longer exists.") from exc


def _get_system_category(name, category_type):
    category = TransactionCategory.objects.filter(
        name__iexact=name,
        category_type=category_type,
    ).first()
    if category is None:
        raise ValidationError({"category": f'The required system category "{name}" is missing.'})
    return category


def build_due_payment_transaction_data(due_payment):
    """Build the complete system CashTransaction payload for a DuePayment."""
    due = due_payment.due
    if due.due_type == DueType.RECEIVABLE:
        transaction_type = TransactionType.CASH_IN
        category = _get_system_category("Due Collection", CategoryType.CASH_IN)
        description = f"Payment received from {due.party_name}"
    elif due.due_type == DueType.PAYABLE:
        transaction_type = TransactionType.CASH_OUT
        category = _get_system_category("Due Payment", CategoryType.CASH_OUT)
        description = f"Payment paid to {due.party_name}"
    else:
        raise ValidationError({"due": "The DueAccount type is invalid."})
    return {
        "transaction_date": due_payment.payment_date,
        "transaction_type": transaction_type,
        "category": category,
        "description": description.strip(),
        "amount": _decimal_amount(due_payment.amount),
        "payment_method": due_payment.payment_method,
        "reference": (due_payment.reference or due.reference or "").strip(),
        "created_by": due_payment.created_by,
        "source_type": TransactionSource.DUE_PAYMENT,
    }


def _validate_due_payment_transaction_link(payment, cash_transaction):
    if cash_transaction.source_type != TransactionSource.DUE_PAYMENT:
        raise ValidationError("The linked transaction is not a DuePayment-generated transaction.")
    linked_payment = DuePayment.objects.filter(cash_transaction_id=cash_transaction.pk).first()
    if linked_payment is None or linked_payment.pk != payment.pk:
        raise ValidationError("The linked transaction belongs to another record.")


@transaction.atomic
def create_opening_balance(*, balance_date, amount, payment_method, description="", reference="", balance_direction, created_by=None):
    amount = _validate_positive_amount(amount)
    category = _get_system_category("Opening Balance", CategoryType.BOTH)
    transaction_type = (
        TransactionType.CASH_IN
        if balance_direction == "positive"
        else TransactionType.CASH_OUT
        if balance_direction == "negative"
        else None
    )
    if transaction_type is None:
        raise ValidationError({"balance_direction": "Select a valid opening balance direction."})
    cash_transaction = CashTransaction(
        transaction_date=balance_date,
        transaction_type=transaction_type,
        category=category,
        description=(description or "Opening Balance").strip(),
        amount=amount,
        payment_method=payment_method,
        reference=(reference or "").strip(),
        created_by=created_by,
        source_type=TransactionSource.OPENING_BALANCE,
    )
    cash_transaction.full_clean()
    cash_transaction.save()
    return cash_transaction


def calculate_total_cash_in(*, start_date=None, end_date=None, payment_method=None, category=None):
    return _cash_total(
        _cash_queryset(
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
            category=category,
        ).filter(transaction_type=TransactionType.CASH_IN)
    )


def calculate_total_cash_out(*, start_date=None, end_date=None, payment_method=None, category=None):
    return _cash_total(
        _cash_queryset(
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
            category=category,
        ).filter(transaction_type=TransactionType.CASH_OUT)
    )


def calculate_net_balance(*, start_date=None, end_date=None, payment_method=None, category=None):
    return calculate_total_cash_in(
        start_date=start_date,
        end_date=end_date,
        payment_method=payment_method,
        category=category,
    ) - calculate_total_cash_out(
        start_date=start_date,
        end_date=end_date,
        payment_method=payment_method,
        category=category,
    )


def calculate_cash_in_hand(*, start_date=None, end_date=None, category=None):
    return calculate_net_balance(
        start_date=start_date,
        end_date=end_date,
        payment_method=PaymentMethod.CASH,
        category=category,
    )


def calculate_payment_method_balances(*, start_date=None, end_date=None, category=None):
    balances = {
        method.value: {
            "display_name": method.label,
            "cash_in": ZERO_AMOUNT,
            "cash_out": ZERO_AMOUNT,
            "balance": ZERO_AMOUNT,
        }
        for method in PaymentMethod
    }
    rows = (
        _cash_queryset(start_date=start_date, end_date=end_date, category=category)
        .values("payment_method", "transaction_type")
        .annotate(
            total=Coalesce(
                Sum("amount"),
                Value(ZERO_AMOUNT),
                output_field=MONEY_FIELD,
            )
        )
    )
    for row in rows:
        method_balances = balances.get(row["payment_method"])
        if method_balances is None:
            continue
        key = "cash_in" if row["transaction_type"] == TransactionType.CASH_IN else "cash_out"
        method_balances[key] = row["total"] or ZERO_AMOUNT
        method_balances["balance"] = method_balances["cash_in"] - method_balances["cash_out"]
    return balances


def _due_balance_queryset(due_type=None):
    queryset = DueAccount.objects.all()
    if due_type:
        queryset = queryset.filter(due_type=due_type)
    queryset = queryset.annotate(
        paid_total=Coalesce(
            Sum("payments__amount"),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        )
    )
    return queryset.annotate(
        remaining_total=Greatest(
            F("original_amount") - F("paid_total"),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        )
    ).annotate(
        status_value=Case(
            When(remaining_total__lte=ZERO_AMOUNT, then=Value("paid")),
            When(due_deadline__lt=timezone.localdate(), remaining_total__gt=ZERO_AMOUNT, then=Value("overdue")),
            When(paid_total__gt=ZERO_AMOUNT, remaining_total__gt=ZERO_AMOUNT, then=Value("partially_paid")),
            default=Value("unpaid"),
            output_field=CharField(),
        )
    )


def _total_due_balance(queryset):
    return (
        queryset.aggregate(
            total=Coalesce(
                Sum("remaining_total"),
                Value(ZERO_AMOUNT),
                output_field=MONEY_FIELD,
            )
        )["total"]
        or ZERO_AMOUNT
    )


def calculate_total_receivable_due():
    return _total_due_balance(_due_balance_queryset(DueType.RECEIVABLE))


def calculate_total_payable_due():
    return _total_due_balance(_due_balance_queryset(DueType.PAYABLE))


def calculate_total_overdue(*, due_type=None):
    queryset = _due_balance_queryset(due_type).filter(
        due_deadline__lt=timezone.localdate(),
        remaining_total__gt=ZERO_AMOUNT,
    )
    return _total_due_balance(queryset)


def _date_window(start_date, end_date):
    """Return an inclusive local-date window as timezone-aware datetimes."""
    current_tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), current_tz)
    end_exclusive = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        current_tz,
    )
    return start, end_exclusive


def _valid_sales_queryset():
    # Sale has no status column. Confirmed orders are the existing source of
    # truth because Order.save() creates Sale rows only for confirmed orders,
    # and confirmed orders cannot transition to another status.
    return Sale.objects.filter(order__status=Order.Status.CONFIRMED)


def _sales_total(*, start_date=None, end_date=None):
    queryset = _valid_sales_queryset()
    if start_date is not None:
        start, _ = _date_window(start_date, start_date)
        queryset = queryset.filter(sale_date__gte=start)
    if end_date is not None:
        _, end_exclusive = _date_window(end_date, end_date)
        queryset = queryset.filter(sale_date__lt=end_exclusive)
    return (
        queryset
        .aggregate(
            total=Coalesce(
                Sum("total_amount"),
                Value(ZERO_AMOUNT),
                output_field=MONEY_FIELD,
            )
        )["total"]
        or ZERO_AMOUNT
    )


def empty_accounts_report_data():
    empty_totals = {
        "total_sales": ZERO_AMOUNT,
        "total_cash_in": ZERO_AMOUNT,
        "total_cash_out": ZERO_AMOUNT,
        "net_cash_flow": ZERO_AMOUNT,
        "receivable_due_created": ZERO_AMOUNT,
        "payable_due_created": ZERO_AMOUNT,
        "due_payments_received": ZERO_AMOUNT,
        "due_payments_paid": ZERO_AMOUNT,
        "due_original_total": ZERO_AMOUNT,
        "due_paid_total": ZERO_AMOUNT,
        "due_remaining_total": ZERO_AMOUNT,
    }
    return {
        "summary": empty_totals,
        "cash_in_by_category": [],
        "cash_out_by_category": [],
        "payment_method_summary": {
            method.value: {
                "display_name": method.label,
                "cash_in": ZERO_AMOUNT,
                "cash_out": ZERO_AMOUNT,
                "balance": ZERO_AMOUNT,
            }
            for method in PaymentMethod
        },
        "transactions": CashTransaction.objects.none(),
        "dues": DueAccount.objects.none(),
    }


def get_accounts_dashboard_metrics():
    """Return all Accounts overview metrics with Decimal-safe empty values."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    today_start, tomorrow_start = _date_window(today, today)
    month_start_dt, tomorrow_start = _date_window(month_start, today)
    previous_month_start_dt, month_start_dt = _date_window(previous_month_start, previous_month_end)

    sales = _valid_sales_queryset()
    sales_totals = sales.aggregate(
        today_sales=Coalesce(
            Sum("total_amount", filter=Q(sale_date__gte=today_start, sale_date__lt=tomorrow_start)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        current_month_sales=Coalesce(
            Sum("total_amount", filter=Q(sale_date__gte=month_start_dt, sale_date__lt=tomorrow_start)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        last_month_sales=Coalesce(
            Sum("total_amount", filter=Q(sale_date__gte=previous_month_start_dt, sale_date__lt=month_start_dt)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )

    cash_totals = CashTransaction.objects.aggregate(
        today_cash_in=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_IN, transaction_date=today)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        today_cash_out=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_OUT, transaction_date=today)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        total_cash_in=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_IN)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        total_cash_out=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_OUT)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        cash_in_hand_in=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_IN, payment_method=PaymentMethod.CASH)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        cash_in_hand_out=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_OUT, payment_method=PaymentMethod.CASH)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )
    total_cash_in = cash_totals["total_cash_in"] or ZERO_AMOUNT
    total_cash_out = cash_totals["total_cash_out"] or ZERO_AMOUNT

    due_totals = _due_balance_queryset().aggregate(
        total_receivable_due=Coalesce(
            Sum("remaining_total", filter=Q(due_type=DueType.RECEIVABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        total_payable_due=Coalesce(
            Sum("remaining_total", filter=Q(due_type=DueType.PAYABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        total_overdue=Coalesce(
            Sum(
                "remaining_total",
                filter=Q(due_deadline__lt=today, remaining_total__gt=ZERO_AMOUNT),
            ),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        overdue_receivable=Coalesce(
            Sum(
                "remaining_total",
                filter=Q(
                    due_type=DueType.RECEIVABLE,
                    due_deadline__lt=today,
                    remaining_total__gt=ZERO_AMOUNT,
                ),
            ),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        overdue_payable=Coalesce(
            Sum(
                "remaining_total",
                filter=Q(
                    due_type=DueType.PAYABLE,
                    due_deadline__lt=today,
                    remaining_total__gt=ZERO_AMOUNT,
                ),
            ),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )

    payment_method_balances = calculate_payment_method_balances()
    recent_cash_in = (
        CashTransaction.objects.select_related("category", "created_by", "due_payment__due")
        .filter(transaction_type=TransactionType.CASH_IN)
        .order_by(*CashTransaction._meta.ordering)[:10]
    )
    recent_cash_out = (
        CashTransaction.objects.select_related("category", "created_by", "due_payment__due")
        .filter(transaction_type=TransactionType.CASH_OUT)
        .order_by(*CashTransaction._meta.ordering)[:10]
    )
    recent_dues = (
        _due_balance_queryset()
        .select_related("created_by")
        .filter(remaining_total__gt=ZERO_AMOUNT)
        .order_by(*DueAccount._meta.ordering)[:10]
    )

    metrics = {
        **sales_totals,
        **cash_totals,
        **due_totals,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "net_balance": total_cash_in - total_cash_out,
        "cash_in_hand": (cash_totals["cash_in_hand_in"] or ZERO_AMOUNT)
        - (cash_totals["cash_in_hand_out"] or ZERO_AMOUNT),
        "payment_method_balances": payment_method_balances,
        "recent_cash_in": recent_cash_in,
        "recent_cash_out": recent_cash_out,
        "recent_dues": recent_dues,
    }
    return {key: (value or ZERO_AMOUNT if isinstance(value, Decimal) else value) for key, value in metrics.items()}


def get_accounts_report_data(*, filters):
    """Build filtered Accounts report querysets and aggregate summaries."""
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    category = filters.get("category")
    payment_method = filters.get("payment_method")
    transaction_type = filters.get("transaction_type")
    due_type = filters.get("due_type")
    search = (filters.get("search") or "").strip()

    cash_queryset = CashTransaction.objects.select_related("category", "created_by", "due_payment__due")
    if start_date is not None:
        cash_queryset = cash_queryset.filter(transaction_date__gte=start_date)
    if end_date is not None:
        cash_queryset = cash_queryset.filter(transaction_date__lte=end_date)
    if transaction_type:
        cash_queryset = cash_queryset.filter(transaction_type=transaction_type)
    if category is not None:
        cash_queryset = cash_queryset.filter(category=category)
    if payment_method:
        cash_queryset = cash_queryset.filter(payment_method=payment_method)
    if search:
        cash_queryset = cash_queryset.filter(
            Q(description__icontains=search)
            | Q(reference__icontains=search)
            | Q(category__name__icontains=search)
        )

    cash_aggregate = cash_queryset.aggregate(
        total_cash_in=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_IN)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        total_cash_out=Coalesce(
            Sum("amount", filter=Q(transaction_type=TransactionType.CASH_OUT)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )
    total_cash_in = cash_aggregate["total_cash_in"] or ZERO_AMOUNT
    total_cash_out = cash_aggregate["total_cash_out"] or ZERO_AMOUNT

    cash_in_by_category = list(
        cash_queryset.filter(transaction_type=TransactionType.CASH_IN)
        .values(category_name=F("category__name"))
        .annotate(
            transaction_count=Count("pk"),
            total_amount=Coalesce(Sum("amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        )
        .order_by("-total_amount", "category_name")
    )
    cash_out_by_category = list(
        cash_queryset.filter(transaction_type=TransactionType.CASH_OUT)
        .values(category_name=F("category__name"))
        .annotate(
            transaction_count=Count("pk"),
            total_amount=Coalesce(Sum("amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        )
        .order_by("-total_amount", "category_name")
    )

    payment_method_summary = {
        method: {
            "display_name": label,
            "cash_in": ZERO_AMOUNT,
            "cash_out": ZERO_AMOUNT,
            "balance": ZERO_AMOUNT,
        }
        for method, label in PaymentMethod.choices
    }
    for row in cash_queryset.values("payment_method", "transaction_type").annotate(
        total=Coalesce(Sum("amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD)
    ):
        method_summary = payment_method_summary.get(row["payment_method"])
        if method_summary is None:
            continue
        key = "cash_in" if row["transaction_type"] == TransactionType.CASH_IN else "cash_out"
        method_summary[key] = row["total"] or ZERO_AMOUNT
    for method_summary in payment_method_summary.values():
        method_summary["balance"] = method_summary["cash_in"] - method_summary["cash_out"]

    due_queryset = _due_balance_queryset().select_related("created_by")
    if start_date is not None:
        due_queryset = due_queryset.filter(due_date__gte=start_date)
    if end_date is not None:
        due_queryset = due_queryset.filter(due_date__lte=end_date)
    if due_type:
        due_queryset = due_queryset.filter(due_type=due_type)
    if search:
        due_queryset = due_queryset.filter(
            Q(party_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(description__icontains=search)
            | Q(reference__icontains=search)
            | Q(notes__icontains=search)
        )

    due_totals = due_queryset.aggregate(
        due_original_total=Coalesce(Sum("original_amount"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        due_paid_total=Coalesce(Sum("paid_total"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        due_remaining_total=Coalesce(Sum("remaining_total"), Value(ZERO_AMOUNT), output_field=MONEY_FIELD),
        receivable_due_created=Coalesce(
            Sum("original_amount", filter=Q(due_type=DueType.RECEIVABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        payable_due_created=Coalesce(
            Sum("original_amount", filter=Q(due_type=DueType.PAYABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )

    payment_queryset = DuePayment.objects.all()
    if start_date is not None:
        payment_queryset = payment_queryset.filter(payment_date__gte=start_date)
    if end_date is not None:
        payment_queryset = payment_queryset.filter(payment_date__lte=end_date)
    if due_type:
        payment_queryset = payment_queryset.filter(due__due_type=due_type)
    if search:
        payment_queryset = payment_queryset.filter(
            Q(due__party_name__icontains=search)
            | Q(due__phone__icontains=search)
            | Q(due__description__icontains=search)
            | Q(due__reference__icontains=search)
            | Q(due__notes__icontains=search)
        )
    payment_totals = payment_queryset.aggregate(
        due_payments_received=Coalesce(
            Sum("amount", filter=Q(due__due_type=DueType.RECEIVABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
        due_payments_paid=Coalesce(
            Sum("amount", filter=Q(due__due_type=DueType.PAYABLE)),
            Value(ZERO_AMOUNT),
            output_field=MONEY_FIELD,
        ),
    )

    total_sales = _sales_total(start_date=start_date, end_date=end_date)
    summary = {
        "total_sales": total_sales,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "net_cash_flow": total_cash_in - total_cash_out,
        **due_totals,
        **payment_totals,
    }
    summary = {key: value or ZERO_AMOUNT for key, value in summary.items()}
    return {
        "summary": summary,
        "cash_in_by_category": cash_in_by_category,
        "cash_out_by_category": cash_out_by_category,
        "payment_method_summary": payment_method_summary,
        "transactions": cash_queryset.order_by(*CashTransaction._meta.ordering),
        "dues": due_queryset.order_by(*DueAccount._meta.ordering),
    }
