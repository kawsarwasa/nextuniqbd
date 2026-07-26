from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0008_homepage_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="brands/logos/"),
        ),
    ]
