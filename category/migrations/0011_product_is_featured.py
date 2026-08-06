from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0010_product_low_stock_threshold_product_stock_quantity_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_featured",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["status", "is_featured", "-created_at"], name="prod_home_featured_date"
            ),
        ),
    ]
