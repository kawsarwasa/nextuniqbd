from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from sitepages.cache import invalidate_public_site_cache

from .models import BlogCategory, BlogComment, BlogPost, BlogTag


@receiver([post_save, post_delete], sender=BlogCategory)
@receiver([post_save, post_delete], sender=BlogComment)
@receiver([post_save, post_delete], sender=BlogPost)
@receiver([post_save, post_delete], sender=BlogTag)
def invalidate_blog_cache(**kwargs):
    invalidate_public_site_cache()
