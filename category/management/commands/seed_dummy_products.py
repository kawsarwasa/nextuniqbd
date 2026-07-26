from io import BytesIO
from datetime import timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from category.models import Brand, Category, Product, ProductImage, ProductReview


PRODUCT_NAMES = [
    "Atlas Trail Backpack",
    "Nimbus Running Jacket",
    "Harbor Leather Wallet",
    "Aurora Desk Lamp",
    "Summit Steel Bottle",
    "Echo Wireless Earbuds",
    "Cedar Coffee Grinder",
    "Pulse Smart Band",
    "Drift Linen Shirt",
    "Terra Ceramic Planter",
    "Vertex Gaming Mouse",
    "Mosaic Throw Pillow",
    "Northwind Travel Mug",
    "Halo Skin Cleanser",
    "Orbit Charging Stand",
    "Lagoon Yoga Mat",
    "Forge Chef Knife",
    "Nova Bluetooth Speaker",
    "Sierra Denim Jacket",
    "Breeze Air Purifier",
    "Flare Sunglasses",
    "Canyon Duffel Bag",
    "Glow Vitamin Serum",
    "Ember Cast Iron Pan",
    "Voyage Laptop Sleeve",
    "Willow Scented Candle",
    "Ridge Hiking Boots",
    "Prism Water Bottle",
    "Aster Wrist Watch",
    "Solstice Floor Cushion",
]

REVIEW_TEMPLATES = [
    {
        "reviewer_name": "Jessica D.",
        "reviewer_email": "jessica@example.com",
        "title": "Super comfortable, exactly as described",
        "body": (
            "Great quality for the price. The finish feels premium and the product looked even better in person. "
            "Would buy again."
        ),
        "rating": 5,
        "verified_purchase": True,
        "helpful_yes": 12,
        "helpful_no": 1,
        "days_ago": 18,
    },
    {
        "reviewer_name": "Mike R.",
        "reviewer_email": "mike@example.com",
        "title": "Great value for the price",
        "body": (
            "Solid purchase overall. The materials are nice, delivery was smooth, and it performs well in daily use."
        ),
        "rating": 4,
        "verified_purchase": True,
        "helpful_yes": 8,
        "helpful_no": 0,
        "days_ago": 31,
    },
    {
        "reviewer_name": "Sarah L.",
        "reviewer_email": "sarah@example.com",
        "title": "Looks good and holds up well",
        "body": (
            "I mainly bought this for everyday use and it has been reliable so far. Clean finish, good fit, and no issues after repeat use."
        ),
        "rating": 5,
        "verified_purchase": False,
        "helpful_yes": 5,
        "helpful_no": 0,
        "days_ago": 44,
    },
    {
        "reviewer_name": "Omar K.",
        "reviewer_email": "omar@example.com",
        "title": "Nice product with one small tradeoff",
        "body": (
            "The overall experience is good and I would still recommend it. One minor detail could be improved, but nothing serious."
        ),
        "rating": 4,
        "verified_purchase": True,
        "helpful_yes": 4,
        "helpful_no": 1,
        "days_ago": 57,
    },
]

class Command(BaseCommand):
    help = "Create or refresh 30 dummy dashboard products with real downloaded images."
    IMAGE_COUNT_PER_PRODUCT = 4
    IMAGE_SIZE = (1200, 1200)

    def handle(self, *args, **options):
        categories = list(Category.objects.order_by("id"))
        brands = list(Brand.objects.order_by("id"))
        self.image_cache = {}

        if not categories:
            raise CommandError("No categories found. Create categories before seeding products.")

        if not brands:
            raise CommandError("No brands found. Create brands before seeding products.")

        created = 0
        updated = 0

        with transaction.atomic():
            for index, product_name in enumerate(PRODUCT_NAMES, start=1):
                category = categories[(index - 1) % len(categories)]
                brand = brands[(index - 1) % len(brands)]
                regular_price = 65 + (index * 7)
                current_price = regular_price - (8 + (index % 5) * 3)
                status = self._build_status(index)
                availability = "In Stock" if index % 5 else "Out of Stock"

                product, was_created = Product.objects.update_or_create(
                    name=product_name,
                    defaults={
                        "category": category,
                        "brand": brand,
                        "name": product_name,
                        "regular_price": regular_price,
                        "current_price": current_price,
                        "status": status,
                        "availability": availability,
                        "short_description": (
                            f"{product_name} is a demo catalog item for the {category.name} range by {brand.name}."
                        ),
                        "full_description": self._build_full_description(
                            product_name=product_name,
                            category_name=category.name,
                            brand_name=brand.name,
                            current_price=current_price,
                            regular_price=regular_price,
                        ),
                    },
                )

                product.images.all().delete()
                for image_index in range(1, self.IMAGE_COUNT_PER_PRODUCT + 1):
                    image_file = self._build_image(
                        index=index,
                        image_index=image_index,
                    )
                    ProductImage.objects.create(
                        product=product,
                        image=image_file,
                        sort_order=image_index - 1,
                    )

                product.reviews.all().delete()
                for review_index, review_template in enumerate(REVIEW_TEMPLATES, start=1):
                    ProductReview.objects.create(
                        product=product,
                        reviewer_name=review_template["reviewer_name"],
                        reviewer_email=review_template["reviewer_email"],
                        title=review_template["title"],
                        body=review_template["body"],
                        rating=review_template["rating"],
                        verified_purchase=review_template["verified_purchase"],
                        helpful_yes=review_template["helpful_yes"] + ((index + review_index) % 3),
                        helpful_no=review_template["helpful_no"] + ((index + review_index) % 2),
                        review_date=(timezone.now() - timedelta(days=review_template["days_ago"] + index)).date(),
                    )

                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded 30 dummy products with real images. "
                f"created={created} updated={updated} "
                f"images_per_product={self.IMAGE_COUNT_PER_PRODUCT} "
                f"reviews_per_product={len(REVIEW_TEMPLATES)}"
            )
        )

    @staticmethod
    def _build_status(index: int) -> str:
        statuses = [
            Product.Status.PUBLISHED,
            Product.Status.PUBLISHED,
            Product.Status.DRAFT,
            Product.Status.INACTIVE,
        ]
        return statuses[(index - 1) % len(statuses)]

    @staticmethod
    def _build_full_description(
        *,
        product_name: str,
        category_name: str,
        brand_name: str,
        current_price: int,
        regular_price: int,
    ) -> str:
        return (
            f"<p><strong>{product_name}</strong> is seeded dummy data for dashboard testing.</p>"
            f"<p>Category: {category_name}. Brand: {brand_name}. Current price: ${current_price}. "
            f"Regular price: ${regular_price}.</p>"
            "<ul>"
            "<li>Used for list, detail, and image preview checks.</li>"
            "<li>Safe to delete and reseed at any time.</li>"
            "<li>Includes four real product photos stored locally in media/products.</li>"
            "</ul>"
        )

    def _build_image(
        self,
        *,
        index: int,
        image_index: int,
    ) -> ContentFile:
        image_url = f"https://picsum.photos/seed/revo-product-{index:03d}-{image_index}/1200/1200.jpg"
        image_bytes = self._get_remote_image_bytes(image_url)

        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                normalized = ImageOps.fit(
                    ImageOps.exif_transpose(source_image).convert("RGB"),
                    self.IMAGE_SIZE,
                    method=Image.Resampling.LANCZOS,
                )

                buffer = BytesIO()
                try:
                    normalized.save(buffer, format="JPEG", quality=90, optimize=True)
                    return ContentFile(
                        buffer.getvalue(),
                        name=f"dummy-product-{index:03d}-{image_index}.jpg",
                    )
                finally:
                    buffer.close()
                    normalized.close()
        except (UnidentifiedImageError, OSError) as exc:
            raise CommandError(f"Failed to process remote image for product {index}, image {image_index}.") from exc

    def _get_remote_image_bytes(self, image_url: str) -> bytes:
        cached = self.image_cache.get(image_url)
        if cached is not None:
            return cached

        request = Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                image_bytes = response.read()
        except URLError as exc:
            raise CommandError(f"Failed to download remote image: {image_url}") from exc

        self.image_cache[image_url] = image_bytes
        return image_bytes
