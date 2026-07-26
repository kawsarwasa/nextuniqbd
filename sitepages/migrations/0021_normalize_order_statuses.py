from django.db import migrations, models


def normalize_order_statuses(apps, schema_editor):
    Order = apps.get_model("sitepages", "Order")

    Order.objects.filter(status__in=["processing", "shipped", "delivered"]).update(status="confirmed")
    Order.objects.exclude(status__in=["pending", "confirmed", "cancelled"]).update(status="pending")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0020_order_orderitem"),
    ]

    operations = [
        migrations.RunPython(normalize_order_statuses, noop_reverse),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
                default="pending",
                max_length=20,
            ),
        ),
    ]
