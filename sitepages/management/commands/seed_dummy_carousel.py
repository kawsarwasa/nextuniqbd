from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from sitepages.models import HeroSlide


class Command(BaseCommand):
    help = "Create 5 dummy hero carousel slides for dashboard testing."

    SLIDES = [
        {
            "name": "New Collection 2024",
            "eyebrow": "New Collection 2024",
            "title": "The Ultimate Shopping List",
            "title_highlight": "Shopping List",
            "description": "Discover the latest trends in fashion, electronics, and more.",
            "primary_button_label": "Shop Now",
            "primary_button_url": "/products/",
            "secondary_button_label": "See More",
            "secondary_button_url": "/blog/",
            "content_alignment": HeroSlide.ContentAlignment.LEFT,
        },
        {
            "name": "Limited Time Electronics",
            "eyebrow": "Limited Time Offer",
            "title": "Up to 50% Off Electronics",
            "title_highlight": "50% Off",
            "description": "Best deals on smartphones, laptops, watches, and accessories.",
            "primary_button_label": "Explore Deals",
            "primary_button_url": "/products/",
            "secondary_button_label": "View All",
            "secondary_button_url": "/products/",
            "content_alignment": HeroSlide.ContentAlignment.RIGHT,
        },
        {
            "name": "Seasonal Sale Sportswear",
            "eyebrow": "Seasonal Sale",
            "title": "Style Meets Comfort",
            "title_highlight": "Comfort",
            "description": "Explore new arrivals in sportswear and outdoor essentials.",
            "primary_button_label": "Shop Collection",
            "primary_button_url": "/products/",
            "secondary_button_label": "Learn More",
            "secondary_button_url": "/about/",
            "content_alignment": HeroSlide.ContentAlignment.LEFT,
        },
        {
            "name": "Premium Accessories",
            "eyebrow": "Premium Picks",
            "title": "Accessories That Finish the Look",
            "title_highlight": "Finish the Look",
            "description": "Bags, watches, and statement pieces selected for everyday styling.",
            "primary_button_label": "Browse Accessories",
            "primary_button_url": "/products/",
            "secondary_button_label": "Read Style Tips",
            "secondary_button_url": "/blog/",
            "content_alignment": HeroSlide.ContentAlignment.CENTER,
        },
        {
            "name": "Weekend Essentials",
            "eyebrow": "Fresh This Week",
            "title": "Weekend Ready Essentials",
            "title_highlight": "Essentials",
            "description": "Build a lighter, cleaner rotation with bestselling casual pieces.",
            "primary_button_label": "Shop Essentials",
            "primary_button_url": "/products/",
            "secondary_button_label": "Explore Blog",
            "secondary_button_url": "/blog/",
            "content_alignment": HeroSlide.ContentAlignment.RIGHT,
        },
    ]

    def handle(self, *args, **options):
        image_pool = sorted((Path("media") / "products").glob("*.jpg"))
        if len(image_pool) < len(self.SLIDES):
            raise CommandError("Not enough local images found in media/products to seed hero slides.")

        created_total = 0
        skipped_total = 0

        for index, slide_data in enumerate(self.SLIDES):
            if HeroSlide.objects.filter(name=slide_data["name"]).exists():
                skipped_total += 1
                continue

            slide = HeroSlide.objects.create(
                name=slide_data["name"],
                eyebrow=slide_data["eyebrow"],
                title=slide_data["title"],
                title_highlight=slide_data["title_highlight"],
                description=slide_data["description"],
                primary_button_label=slide_data["primary_button_label"],
                primary_button_url=slide_data["primary_button_url"],
                secondary_button_label=slide_data["secondary_button_label"],
                secondary_button_url=slide_data["secondary_button_url"],
                content_alignment=slide_data["content_alignment"],
                sort_order=index,
                is_active=True,
            )

            image_path = image_pool[index]
            with image_path.open("rb") as image_file:
                filename = f"dummy-hero-slide-{index + 1:02d}{image_path.suffix.lower()}"
                slide.image.save(filename, File(image_file), save=True)

            created_total += 1
            self.stdout.write(self.style.SUCCESS(f'Created hero slide "{slide.name}"'))

        self.stdout.write(
            self.style.SUCCESS(
                f"Dummy hero slide seeding complete. Created {created_total} slides and skipped {skipped_total} existing slides."
            )
        )
