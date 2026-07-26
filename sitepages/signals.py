import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Order, OrderStatusHistory, UserProfile
from .models import HeroSlide, HomepagePromoBanner
from .cache import invalidate_public_site_cache
from .permissions import ensure_default_roles


User = get_user_model()
SUPERUSER_EMAIL = "superuser@mail.com"
SUPERUSER_PASSWORD = "Admin@100%"


@receiver([post_save, post_delete], sender=HeroSlide)
@receiver([post_save, post_delete], sender=HomepagePromoBanner)
def invalidate_sitepages_public_cache(**kwargs):
    invalidate_public_site_cache()


@receiver(post_save, sender=User)
def ensure_dashboard_profile(sender, instance, created, raw=False, **kwargs):
    if raw:
        return

    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Order)
def create_initial_order_status_history(sender, instance, created, raw=False, **kwargs):
    """Record the actual initial status once, without inventing later milestones."""
    if raw:
        return

    if created:
        OrderStatusHistory.objects.create(
            order=instance,
            previous_status="",
            status=instance.status,
            changed_at=instance.created_at,
            changed_by=instance.user,
            note="Order created.",
            source=getattr(
                instance,
                "_initial_status_history_source",
                OrderStatusHistory.Source.SYSTEM,
            ),
        )
    elif (
        getattr(instance, "_status_changed_on_save", False)
        and not getattr(instance, "_skip_order_status_history_signal", False)
    ):
        OrderStatusHistory.objects.create(
            order=instance,
            previous_status=getattr(instance, "_previous_status_on_save", ""),
            status=instance.status,
            changed_at=timezone.now(),
            note="Status changed by a system process.",
            source=OrderStatusHistory.Source.SYSTEM,
        )


@receiver(post_migrate)
def seed_default_auth_records(sender, **kwargs):
    if getattr(sender, "name", "") != "sitepages":
        return
    if os.environ.get("REVO_SKIP_AUTH_SEED") == "1":
        return

    ensure_default_roles()

    username = SUPERUSER_EMAIL.lower()
    user = User.objects.filter(email__iexact=SUPERUSER_EMAIL).first()
    if user is None:
        user = User.objects.filter(username__iexact=username).first()

    if user is None:
        user = User.objects.create_user(
            username=username,
            email=SUPERUSER_EMAIL,
            password=SUPERUSER_PASSWORD,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            first_name="Super",
            last_name="User",
        )
    else:
        user.username = username
        user.email = SUPERUSER_EMAIL
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.first_name = user.first_name or "Super"
        user.last_name = user.last_name or "User"
        user.set_password(SUPERUSER_PASSWORD)
        user.save()

    UserProfile.objects.get_or_create(user=user)

    admin_group = Group.objects.filter(name="admins").first()
    if admin_group is not None:
        user.groups.add(admin_group)
