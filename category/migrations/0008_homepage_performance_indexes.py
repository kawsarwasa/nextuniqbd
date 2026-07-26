from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0007_product_sku_format"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["is_active", "sort_order"], name="cat_home_active_sort"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["status", "category", "-created_at"],
                name="prod_home_status_cat_date",
            ),
        ),
        migrations.AddIndex(
            model_name="productimage",
            index=models.Index(fields=["product", "sort_order"], name="prodimg_product_sort"),
        ),
    ]
