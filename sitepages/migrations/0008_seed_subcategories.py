from django.db import migrations
from django.utils.text import slugify


def seed_subcategories(apps, schema_editor):
    Category = apps.get_model("sitepages", "Category")
    SubCategory = apps.get_model("sitepages", "SubCategory")

    subcategories = [
        {
            "category_slug": "fashion",
            "name": "Men's Wear",
            "short_description": "Shirts, t-shirts, pants, and everyday fashion basics.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": True,
        },
        {
            "category_slug": "fashion",
            "name": "Women's Wear",
            "short_description": "Dresses, tops, ethnic wear, and seasonal collections.",
            "sort_order": 30,
            "is_active": True,
            "show_on_homepage": True,
        },
        {
            "category_slug": "electronics",
            "name": "Mobile Phones",
            "short_description": "Smartphones, feature phones, and accessories.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": True,
        },
        {
            "category_slug": "electronics",
            "name": "Audio Devices",
            "short_description": "Headphones, speakers, and wireless audio gear.",
            "sort_order": 30,
            "is_active": True,
            "show_on_homepage": False,
        },
        {
            "category_slug": "grocery",
            "name": "Snacks",
            "short_description": "Chips, biscuits, and ready-to-eat favorites.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": False,
        },
        {
            "category_slug": "cosmetics",
            "name": "Skincare",
            "short_description": "Face wash, serums, moisturizers, and sunscreen.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": True,
        },
    ]

    for data in subcategories:
        category = Category.objects.filter(slug=data["category_slug"]).first()
        if not category:
            continue

        slug = slugify(data["name"])
        SubCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "category": category,
                "name": data["name"],
                "slug": slug,
                "short_description": data["short_description"],
                "sort_order": data["sort_order"],
                "is_active": data["is_active"],
                "show_on_homepage": data["show_on_homepage"],
            },
        )


def unseed_subcategories(apps, schema_editor):
    SubCategory = apps.get_model("sitepages", "SubCategory")
    SubCategory.objects.filter(
        slug__in=[
            "mens-wear",
            "womens-wear",
            "mobile-phones",
            "audio-devices",
            "snacks",
            "skincare",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0007_subcategory"),
    ]

    operations = [
        migrations.RunPython(seed_subcategories, unseed_subcategories),
    ]
