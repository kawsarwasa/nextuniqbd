from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from sitepages.cache import invalidate_public_site_cache

from .models import CompanyProfile


@receiver([post_save, post_delete], sender=CompanyProfile)
def invalidate_company_cache(**kwargs):
    invalidate_public_site_cache()
