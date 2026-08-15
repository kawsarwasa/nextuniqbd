from django.core.management.base import BaseCommand

from category.image_derivatives import (
    LEGACY_PRODUCT_IMAGE_VARIANTS,
    product_image_legacy_derivative_name,
)
from category.models import ProductImage


class Command(BaseCommand):
    help = "Remove only legacy .card.webp and .detail.webp product image derivatives."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Remove files; dry-run by default.")

    def handle(self, *args, **options):
        write = options["write"]
        total = removed = planned = 0

        for image in ProductImage.objects.exclude(image="").iterator():
            total += 1
            storage = image.image.storage
            for variant in LEGACY_PRODUCT_IMAGE_VARIANTS:
                legacy_name = product_image_legacy_derivative_name(image.image.name, variant)
                if not storage.exists(legacy_name):
                    continue

                planned += 1
                if write:
                    storage.delete(legacy_name)
                    removed += 1
                    self.stdout.write(f"Removed: {legacy_name}")
                else:
                    self.stdout.write(f"Would remove: {legacy_name}")

        if write:
            self.stdout.write(f"Processed {total} product images; removed {removed} legacy derivatives.")
        else:
            self.stdout.write(f"Processed {total} product images; planned removal of {planned} legacy derivatives.")
