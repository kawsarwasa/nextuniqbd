from django.db import migrations
from django.utils.text import slugify


def ensure_seed_subcategories(apps, schema_editor):
    Category = apps.get_model("sitepages", "Category")
    SubCategory = apps.get_model("sitepages", "SubCategory")

    categories = [
        {
            "name": "Fashion",
            "slug": "fashion",
            "short_description": "Clothing, accessories, and seasonal style essentials.",
            "sort_order": 10,
            "is_active": True,
            "show_on_homepage": True,
        },
        {
            "name": "Electronics",
            "slug": "electronics",
            "short_description": "Gadgets, accessories, and smart devices.",
            "sort_order": 20,
            "is_active": True,
            "show_on_homepage": True,
        },
        {
            "name": "Grocery",
            "slug": "grocery",
            "short_description": "Daily essentials and pantry supplies.",
            "sort_order": 30,
            "is_active": True,
            "show_on_homepage": False,
        },
        {
            "name": "Cosmetics",
            "slug": "cosmetics",
            "short_description": "Beauty, skincare, and personal care items.",
            "sort_order": 40,
            "is_active": True,
            "show_on_homepage": False,
        },
    ]

    for category_data in categories:
        Category.objects.update_or_create(
            slug=category_data["slug"],
            defaults=category_data,
        )

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
        category = Category.objects.get(slug=data["category_slug"])
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


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0008_seed_subcategories"),
    ]

    operations = [
        migrations.RunPython(ensure_seed_subcategories, migrations.RunPython.noop),
    ]
