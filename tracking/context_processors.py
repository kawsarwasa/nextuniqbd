from django.conf import settings


def meta_tracking(request):
    """Expose only the public browser Pixel configuration to frontend templates."""
    return {
        "meta_pixel_enabled": bool(settings.META_TRACKING_ENABLED and settings.META_PIXEL_ID),
        "meta_pixel_id": settings.META_PIXEL_ID if settings.META_TRACKING_ENABLED else "",
    }
