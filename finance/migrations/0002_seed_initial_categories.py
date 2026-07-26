from django.db import migrations


SEED_CATEGORIES = (
    ("Sale", "cash_in"),
    ("Due Collection", "cash_in"),
    ("Owner Investment", "cash_in"),
    ("Loan Received", "cash_in"),
    ("Refund Received", "cash_in"),
    ("Other Income", "cash_in"),
    ("Purchase", "cash_out"),
    ("Salary", "cash_out"),
    ("Rent", "cash_out"),
    ("Delivery Cost", "cash_out"),
    ("Marketing", "cash_out"),
    ("Utility Bill", "cash_out"),
    ("Office Expense", "cash_out"),
    ("Loan Payment", "cash_out"),
    ("Due Payment", "cash_out"),
    ("Refund Paid", "cash_out"),
    ("Other Expense", "cash_out"),
)


def seed_initial_categories(apps, schema_editor):
    TransactionCategory = apps.get_model("finance", "TransactionCategory")

    for name, category_type in SEED_CATEGORIES:
        category = (
            TransactionCategory.objects.filter(
                category_type=category_type,
                name__iexact=name,
            )
            .order_by("pk")
            .first()
        )
        if category is None:
            TransactionCategory.objects.create(
                name=name,
                category_type=category_type,
                is_active=True,
            )


def unseed_initial_categories(apps, schema_editor):
    TransactionCategory = apps.get_model("finance", "TransactionCategory")

    for name, category_type in SEED_CATEGORIES:
        (
            TransactionCategory.objects.filter(
                category_type=category_type,
                name__iexact=name,
                transactions__isnull=True,
            )
            .delete()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_initial_categories, unseed_initial_categories),
    ]
