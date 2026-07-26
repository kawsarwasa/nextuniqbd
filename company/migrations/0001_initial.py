# Generated manually for the company branding app.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CompanyProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company_name", models.CharField(max_length=150)),
                ("slug", models.SlugField(blank=True, max_length=170, unique=True)),
                ("logo", models.ImageField(blank=True, upload_to="company/logos/")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Company Profile",
                "verbose_name_plural": "Company Profiles",
                "ordering": ["sort_order", "company_name", "id"],
            },
        ),
    ]
