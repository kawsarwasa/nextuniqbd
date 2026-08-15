"""Non-destructive optimized images for storefront product media."""

from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


PRODUCT_IMAGE_MAX_SIZE = (800, 800)
WEBP_QUALITY = 82
LEGACY_PRODUCT_IMAGE_VARIANTS = ("card", "detail")


def product_image_optimized_name(source_name):
    """Return the storage-relative name of a product image's optimized WebP."""
    source_path = PurePosixPath(source_name)
    return str(source_path.with_name(f"{source_path.stem}.optimized.webp"))


def product_image_legacy_derivative_name(source_name, variant):
    """Return a known legacy derivative name for targeted cleanup only."""
    if variant not in LEGACY_PRODUCT_IMAGE_VARIANTS:
        raise ValueError(f"Unknown legacy product image variant: {variant}")

    source_path = PurePosixPath(source_name)
    return str(source_path.with_name(f"{source_path.stem}.{variant}.webp"))


def product_image_optimized_url(image_field):
    """Use the optimized image when available, otherwise retain the original."""
    if not image_field or not image_field.name:
        return ""

    optimized_name = product_image_optimized_name(image_field.name)
    storage = image_field.storage
    if storage.exists(optimized_name):
        return storage.url(optimized_name)
    return image_field.url


def generate_product_image_derivative(image_field, *, force=False):
    """Create one size-limited WebP sidecar without changing the original upload.

    Unavailable, animated, and unreadable images are intentionally skipped so the
    storefront can use the original image as a safe fallback.
    """
    if not image_field or not image_field.name:
        return None

    storage = image_field.storage
    target_name = product_image_optimized_name(image_field.name)
    if storage.exists(target_name) and not force:
        return storage.url(target_name)

    try:
        with storage.open(image_field.name, "rb") as source_file:
            with Image.open(source_file) as opened:
                if getattr(opened, "is_animated", False):
                    return None

                source = ImageOps.exif_transpose(opened)
                try:
                    has_transparency = "A" in source.getbands() or "transparency" in source.info
                    target_mode = "RGBA" if has_transparency else "RGB"
                    if source.mode != target_mode:
                        normalized = source.convert(target_mode)
                        source.close()
                        source = normalized

                    derived = source.copy()
                    output = BytesIO()
                    try:
                        derived.thumbnail(PRODUCT_IMAGE_MAX_SIZE, Image.Resampling.LANCZOS)
                        derived.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
                        if force and storage.exists(target_name):
                            storage.delete(target_name)
                        storage.save(target_name, ContentFile(output.getvalue()))
                        return storage.url(target_name)
                    finally:
                        output.close()
                        derived.close()
                finally:
                    source.close()
    except (FileNotFoundError, OSError, UnidentifiedImageError, ValueError):
        return None


def generate_product_image_derivatives(image_field, *, force=False):
    """Compatibility wrapper for callers using the previous plural helper."""
    optimized_url = generate_product_image_derivative(image_field, force=force)
    return {"optimized": optimized_url} if optimized_url else {}
