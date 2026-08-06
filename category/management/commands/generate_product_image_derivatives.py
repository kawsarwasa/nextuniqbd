from django.core.management.base import BaseCommand

from category.image_derivatives import generate_product_image_derivatives, product_image_variant_name
from category.models import ProductImage


class Command(BaseCommand):
    help = "Create non-destructive 400px card and 1000px detail WebP product-image derivatives."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Write missing derivatives; dry-run by default.")
        parser.add_argument("--force", action="store_true", help="Regenerate derivatives that already exist.")

    def handle(self, *args, **options):
        write = options["write"]
        force = options["force"]
        total = generated = planned = skipped = 0

        for image in ProductImage.objects.exclude(image="").iterator():
            total += 1
            expected = [product_image_variant_name(image.image.name, variant) for variant in ("card", "detail")]
            missing = [name for name in expected if not image.image.storage.exists(name)]
            if not force and not missing:
                skipped += 1
                continue
            planned += len(missing or expected)
            if write:
                result = generate_product_image_derivatives(image.image, force=force)
                generated += len(result)
            else:
                self.stdout.write(f"Would generate: {', '.join(missing or expected)}")

        if write:
            self.stdout.write(f"Processed {total} product images; wrote {generated} derivatives; skipped {skipped} already complete images.")
        else:
            self.stdout.write(f"Processed {total} product images; planned {planned} derivatives; skipped {skipped} already complete images.")
