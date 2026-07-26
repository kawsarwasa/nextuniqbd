from django.core.management.base import BaseCommand
from django.utils.text import slugify

from category.models import Category


NAVIGATION_CATEGORIES = [
    {
        "name": "Fashion",
        "icon_class": "fa fa-tshirt",
        "short_description": "Clothing, seasonal looks, and wardrobe staples.",
        "show_on_homepage": True,
    },
    {
        "name": "Kitchen",
        "icon_class": "fa fa-utensils",
        "short_description": "Cookware, dining tools, and kitchen essentials.",
        "show_on_homepage": True,
    },
    {
        "name": "Computer",
        "icon_class": "fa fa-laptop",
        "short_description": "Computing gear, peripherals, and work setups.",
        "show_on_homepage": True,
    },
    {
        "name": "Bags",
        "icon_class": "fa fa-briefcase",
        "short_description": "Backpacks, totes, and travel carry options.",
        "show_on_homepage": True,
    },
    {
        "name": "Watches",
        "icon_class": "fa fa-clock",
        "short_description": "Classic watches and smart wearable picks.",
        "show_on_homepage": False,
    },
    {
        "name": "Smartphone",
        "icon_class": "fa fa-mobile-alt",
        "short_description": "Phones, accessories, and mobile lifestyle gear.",
        "show_on_homepage": False,
    },
    {
        "name": "Health & Beauty",
        "icon_class": "fa fa-spa",
        "short_description": "Skincare, wellness, and personal care products.",
        "show_on_homepage": False,
    },
    {
        "name": "Sport Clothing",
        "icon_class": "fa fa-running",
        "short_description": "Activewear, training apparel, and performance basics.",
        "show_on_homepage": False,
    },
    {
        "name": "Jewelry",
        "icon_class": "fa fa-gem",
        "short_description": "Statement pieces, gifts, and everyday jewelry.",
        "show_on_homepage": False,
    },
    {
        "name": "Accessories",
        "icon_class": "fa fa-glasses",
        "short_description": "Small add-ons that complete the look.",
        "show_on_homepage": False,
    },
]


class Command(BaseCommand):
    help = "Insert or update the frontend navigation categories in the dashboard."

    def handle(self, *args, **options):
        reusable_categories = list(
            Category.objects.filter(name__startswith="Demo Category").order_by("sort_order", "id")
        )
        reused_ids = set()
        created = 0
        updated = 0

        for sort_order, payload in enumerate(NAVIGATION_CATEGORIES):
            category = Category.objects.filter(slug=slugify(payload["name"])).first()
            if category is None:
                category = next(
                    (
                        candidate
                        for candidate in reusable_categories
                        if candidate.pk not in reused_ids
                    ),
                    None,
                )

            if category is None:
                category = Category()
                created += 1
            else:
                updated += 1
                reused_ids.add(category.pk)

            category.name = payload["name"]
            category.icon_class = payload["icon_class"]
            category.short_description = payload["short_description"]
            category.sort_order = sort_order
            category.is_active = True
            category.show_on_homepage = payload["show_on_homepage"]
            category.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Navigation categories synced successfully. created={created} updated={updated}"
            )
        )
