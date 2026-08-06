"""Non-destructive image derivatives for storefront product media."""

from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


PRODUCT_IMAGE_VARIANTS = {
    "card": (400, 400),
    "detail": (1000, 1000),
}
WEBP_QUALITY = 82


def product_image_variant_name(source_name, variant):
    """Return the storage-relative name of a product-image WebP derivative."""
    if variant not in PRODUCT_IMAGE_VARIANTS:
        raise ValueError(f"Unknown product image variant: {variant}")

    source_path = PurePosixPath(source_name)
    return str(source_path.with_name(f"{source_path.stem}.{variant}.webp"))


def product_image_variant_url(image_field, variant):
    """Use an existing derivative when available, otherwise retain the original."""
    if not image_field or not image_field.name:
        return ""

    derivative_name = product_image_variant_name(image_field.name, variant)
    storage = image_field.storage
    if storage.exists(derivative_name):
        return storage.url(derivative_name)
    return image_field.url


def generate_product_image_derivatives(image_field, *, force=False):
    """Create size-limited WebP sidecars without modifying the uploaded original.

    The helper deliberately skips unavailable, animated, and unreadable files. That
    makes old database rows and remote-storage failures fall back safely to the
    original image URL.
    """
    if not image_field or not image_field.name:
        return {}

    storage = image_field.storage
    try:
        with storage.open(image_field.name, "rb") as source_file:
            with Image.open(source_file) as opened:
                if getattr(opened, "is_animated", False):
                    return {}
                source = ImageOps.exif_transpose(opened)
                try:
                    if source.mode not in {"RGB", "RGBA"}:
                        normalized = source.convert("RGBA" if "A" in source.getbands() else "RGB")
                        source.close()
                        source = normalized

                    generated = {}
                    for variant, max_size in PRODUCT_IMAGE_VARIANTS.items():
                        target_name = product_image_variant_name(image_field.name, variant)
                        if storage.exists(target_name) and not force:
                            generated[variant] = storage.url(target_name)
                            continue

                        # Storage backends usually avoid overwriting an existing
                        # name.  Explicitly replace only the derivative when
                        # --force is requested; uploaded originals stay intact.
                        if force and storage.exists(target_name):
                            storage.delete(target_name)

                        derived = source.copy()
                        derived.thumbnail(max_size, Image.Resampling.LANCZOS)
                        output = BytesIO()
                        try:
                            derived.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
                            storage.save(target_name, ContentFile(output.getvalue()))
                            generated[variant] = storage.url(target_name)
                        finally:
                            output.close()
                            derived.close()
                    return generated
                finally:
                    source.close()
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return {}
