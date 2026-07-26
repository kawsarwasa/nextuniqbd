from django.db import migrations
from django.utils.text import slugify


def seed_categories(apps, schema_editor):
    Category = apps.get_model("sitepages", "Category")

    categories = [
        {
            "name": "Fashion",
            "category_type": "fashion",
            "short_description": "Clothing, accessories, and seasonal style essentials.",
            "description": "Category for apparel, shoes, bags, and fashion accessories.",
            "sort_order": 10,
            "is_active": True,
            "show_on_homepage": True,
            "homepage_title": "Trending Fashion",
        },
        {
            "name": "Electronics",
            "category_type": "electronics",
            "short_description": "Gadgets, accessories, and smart devices.",
            "description": "Category for phones, laptops, audio devices, and accessories.",
            "sort_order": 20,
            "is_active": True,
            "show_on_homepage": True,
            "homepage_title": "Top Electronics",
        },
        {
            "name": "Grocery",
            "category_type": "grocery",
            "short_description": "Daily essentials and pantry supplies.",
            "description": "Category for packaged food, beverages, and household consumables.",
            "sort_order": 30,
            "is_active": True,
            "show_on_homepage": False,
            "homepage_title": "",
        },
        {
            "name": "Cosmetics",
            "category_type": "cosmetics",
            "short_description": "Beauty, skincare, and personal care items.",
            "description": "Category for makeup, skincare products, and personal grooming essentials.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": False,
            "homepage_title": "",
        },
    ]

    for data in categories:
        slug = slugify(data["name"])
        Category.objects.update_or_create(
            slug=slug,
            defaults={**data, "slug": slug},
        )


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("sitepages", "Category")
    Category.objects.filter(slug__in=["fashion", "electronics", "grocery", "cosmetics"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0003_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
