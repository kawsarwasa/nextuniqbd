from django.core.management.base import BaseCommand

from category.image_derivatives import (
    generate_product_image_derivative,
    product_image_optimized_name,
)
from category.models import ProductImage


class Command(BaseCommand):
    help = "Generate one optimized WebP derivative for each existing product image."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report missing optimized images without writing them.")
        parser.add_argument("--force", action="store_true", help="Regenerate optimized images that already exist.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        total = generated = planned = skipped = failed = 0

        for image in ProductImage.objects.exclude(image="").iterator():
            total += 1
            target_name = product_image_optimized_name(image.image.name)
            if not force and image.image.storage.exists(target_name):
                skipped += 1
                continue

            planned += 1
            if dry_run:
                self.stdout.write(f"Would generate: {target_name}")
                continue

            if generate_product_image_derivative(image.image, force=force):
                generated += 1
            else:
                failed += 1
                self.stderr.write(f"Skipped unreadable or animated image: {image.image.name}")

        if dry_run:
            self.stdout.write(
                f"Processed {total} product images; planned {planned} optimized derivatives; "
                f"skipped {skipped} already complete images."
            )
        else:
            self.stdout.write(
                f"Processed {total} product images; generated {generated} optimized derivatives; "
                f"skipped {skipped} already complete images; failed {failed}."
            )
