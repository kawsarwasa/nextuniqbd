from django.conf import settings
from django.core.cache import cache


PUBLIC_CACHE_TIMEOUT = getattr(settings, "PUBLIC_CACHE_TIMEOUT", 300)
ACTIVE_CATEGORIES_CACHE_KEY = "sitepages:active-categories:v1"
COMPANY_PROFILE_CACHE_KEY = "company:active-profile:v1"
HERO_SLIDES_CACHE_KEY = "homepage:hero-slides:v1"
HOMEPAGE_CATEGORIES_CACHE_KEY = "homepage:categories:v1"
HOMEPAGE_BRANDS_CACHE_KEY = "homepage:brands:v1"
FOOTER_BRANDS_CACHE_KEY = "footer:brands:v2"
FOOTER_CATEGORIES_CACHE_KEY = "footer:categories:v1"
HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY = "homepage:latest-products:v1"


def get_public_cache_value(key, builder):
    value = cache.get(key)
    if value is None:
        value = builder()
        cache.set(key, value, PUBLIC_CACHE_TIMEOUT)
    return value


def invalidate_public_site_cache():
    cache.delete_many(
        [
            ACTIVE_CATEGORIES_CACHE_KEY,
            COMPANY_PROFILE_CACHE_KEY,
            HERO_SLIDES_CACHE_KEY,
            HOMEPAGE_CATEGORIES_CACHE_KEY,
            HOMEPAGE_BRANDS_CACHE_KEY,
            FOOTER_BRANDS_CACHE_KEY,
            FOOTER_CATEGORIES_CACHE_KEY,
            HOMEPAGE_LATEST_PRODUCTS_CACHE_KEY,
        ]
    )
