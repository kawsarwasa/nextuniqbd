from django.core.cache import cache

from .models import CompanyProfile
from sitepages.cache import COMPANY_PROFILE_CACHE_KEY, PUBLIC_CACHE_TIMEOUT


def company_context(request):
    site_company = cache.get(COMPANY_PROFILE_CACHE_KEY)
    if site_company is None:
        site_company = CompanyProfile.get_active()
        cache.set(COMPANY_PROFILE_CACHE_KEY, site_company, PUBLIC_CACHE_TIMEOUT)
    return {
        "site_company": site_company,
        "default_company_name": "SBRevo",
    }
