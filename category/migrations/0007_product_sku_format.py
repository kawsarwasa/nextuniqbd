import secrets
import string

from django.db import migrations, models


SKU_PREFIX = "NUB"
SKU_LENGTH = 12
SKU_ALPHABET = string.ascii_uppercase + string.digits


def generate_sku(existing_skus):
    while True:
        suffix = "".join(
            secrets.choice(SKU_ALPHABET) for _ in range(SKU_LENGTH - len(SKU_PREFIX))
        )
        sku = f"{SKU_PREFIX}{suffix}"
        if sku not in existing_skus:
            existing_skus.add(sku)
            return sku


def replace_existing_skus(apps, schema_editor):
    Product = apps.get_model("category", "Product")
    existing_skus = set(Product.objects.values_list("sku", flat=True))

    for product in Product.objects.order_by("pk").iterator():
        product.sku = generate_sku(existing_skus)
        product.save(update_fields=["sku"])


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0006_category_icon_class"),
    ]

    operations = [
        migrations.RunPython(replace_existing_skus, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(max_length=12, unique=True),
        ),
    ]
