from django.db import migrations, transaction


REQUIRED_CATEGORIES = (
    ("Due Collection", "cash_in"),
    ("Due Payment", "cash_out"),
    ("Opening Balance", "both"),
)


def get_or_prepare_category(category_model, name, category_type, using):
    manager = category_model.objects.using(using)
    matches = list(manager.filter(name__iexact=name).order_by("pk"))
    matching_type = next((category for category in matches if category.category_type == category_type), None)
    if matching_type is not None:
        return matching_type
    if matches:
        category = matches[0]
        if category.transactions.using(using).exists():
            raise RuntimeError(
                f'Cannot change category "{category.name}" to type "{category_type}" because it is already in use.'
            )
        category.category_type = category_type
        category.save(update_fields=["category_type"])
        return category
    return category_model.objects.create(name=name, category_type=category_type, is_active=True)


def forwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Category = apps.get_model("finance", "TransactionCategory")
    CashTransaction = apps.get_model("finance", "CashTransaction")
    DuePayment = apps.get_model("finance", "DuePayment")

    with transaction.atomic(using=db_alias):
        categories = {
            (name, category_type): get_or_prepare_category(Category, name, category_type, db_alias)
            for name, category_type in REQUIRED_CATEGORIES
        }
        for payment in DuePayment.objects.using(db_alias).select_related("due").filter(cash_transaction__isnull=True).iterator():
            if payment.due.due_type == "receivable":
                transaction_type = "cash_in"
                category = categories[("Due Collection", "cash_in")]
                description = f"Payment received from {payment.due.party_name}"
            elif payment.due.due_type == "payable":
                transaction_type = "cash_out"
                category = categories[("Due Payment", "cash_out")]
                description = f"Payment paid to {payment.due.party_name}"
            else:
                raise RuntimeError(f"DuePayment {payment.pk} has an invalid due type.")

            cash_transaction = CashTransaction.objects.using(db_alias).create(
                transaction_date=payment.payment_date,
                transaction_type=transaction_type,
                category_id=category.pk,
                description=description.strip(),
                amount=payment.amount,
                payment_method=payment.payment_method,
                reference=(payment.reference or payment.due.reference or "").strip(),
                created_by_id=payment.created_by_id,
                source_type="due_payment",
            )
            payment.cash_transaction_id = cash_transaction.pk
            payment.save(update_fields=["cash_transaction"])


def backwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Category = apps.get_model("finance", "TransactionCategory")
    CashTransaction = apps.get_model("finance", "CashTransaction")
    DuePayment = apps.get_model("finance", "DuePayment")

    with transaction.atomic(using=db_alias):
        for payment in DuePayment.objects.using(db_alias).all().iterator():
            transaction_id = payment.cash_transaction_id
            if not transaction_id:
                continue
            cash_transaction = CashTransaction.objects.using(db_alias).filter(pk=transaction_id).first()
            if cash_transaction is None or cash_transaction.source_type != "due_payment":
                continue
            payment.cash_transaction_id = None
            payment.save(update_fields=["cash_transaction"])
            cash_transaction.delete()

        for name, category_type in REQUIRED_CATEGORIES:
            category = Category.objects.using(db_alias).filter(name__iexact=name, category_type=category_type).first()
            if category is not None and not category.transactions.using(db_alias).exists():
                category.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0003_cashtransaction_source_type_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
