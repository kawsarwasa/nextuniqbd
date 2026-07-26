from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from sitepages.cache import invalidate_public_site_cache

from .models import Brand, Category, Product, ProductImage, ProductReview


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Brand)
@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=ProductImage)
@receiver([post_save, post_delete], sender=ProductReview)
def invalidate_category_cache(**kwargs):
    invalidate_public_site_cache()
