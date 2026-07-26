from posixpath import join as posix_join
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from category.models import Category


CATEGORY_KEYWORDS = {
    "fashion": "fashion clothes",
    "kitchen": "kitchen cookware",
    "computer": "computer laptop workspace",
    "bags": "bags backpack handbag",
    "watches": "watches wrist watch",
    "smartphone": "smartphone mobile phone",
    "health-beauty": "health beauty skincare",
    "sport-clothing": "sports clothing activewear",
    "jewelry": "jewelry accessories",
    "accessories": "fashion accessories sunglasses",
}


class Command(BaseCommand):
    help = "Update category images with category-related replacements and remove previous files."

    IMAGE_WIDTH = 1200
    IMAGE_HEIGHT = 1200

    def handle(self, *args, **options):
        categories = list(Category.objects.filter(is_active=True).order_by("sort_order", "name", "id"))
        if not categories:
            raise CommandError("No active categories found.")

        updated = 0
        cleanup_targets = []

        with transaction.atomic():
            for index, category in enumerate(categories, start=1):
                keyword = CATEGORY_KEYWORDS.get(category.slug) or category.name.lower()
                image_url = (
                    f"https://loremflickr.com/{self.IMAGE_WIDTH}/{self.IMAGE_HEIGHT}/"
                    f"{quote_plus(keyword)}?lock={index}"
                )
                image_bytes = self._download_image(image_url)
                file_name = f"{slugify(category.name) or 'category'}.jpg"
                raw_storage_name = posix_join("categories", file_name)

                category.image = ContentFile(image_bytes, name=file_name)
                category.save()
                cleanup_targets.append((category.image.storage, raw_storage_name, category.image.name))
                if category.image.name != raw_storage_name:
                    storage = category.image.storage
                    if storage.exists(raw_storage_name):
                        storage.delete(raw_storage_name)
                updated += 1

                self.stdout.write(f"Updated image for {category.name}")

        for storage, raw_storage_name, current_storage_name in cleanup_targets:
            if current_storage_name != raw_storage_name and storage.exists(raw_storage_name):
                storage.delete(raw_storage_name)

        self._delete_unused_category_files()

        self.stdout.write(
            self.style.SUCCESS(
                f"Category images refreshed successfully. updated={updated}"
            )
        )

    @staticmethod
    def _download_image(image_url: str) -> bytes:
        request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as exc:
            raise CommandError(f"Could not download category image from {image_url}") from exc

    @staticmethod
    def _delete_unused_category_files():
        categories_dir = Path("media/categories")
        if not categories_dir.exists():
            return

        used_names = {
            Path(image_name).name
            for image_name in Category.objects.exclude(image="").values_list("image", flat=True)
            if image_name
        }

        for file_path in categories_dir.iterdir():
            if file_path.is_file() and file_path.name not in used_names:
                file_path.unlink()
