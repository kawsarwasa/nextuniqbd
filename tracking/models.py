from django.conf import settings
from django.db import models


class MetaOrderAttribution(models.Model):
    """The shopper browser data needed after a COD order is later confirmed."""

    order = models.OneToOneField(
        "sitepages.Order",
        on_delete=models.CASCADE,
        related_name="meta_attribution",
    )
    fbp = models.CharField(max_length=255, blank=True)
    fbc = models.CharField(max_length=255, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    client_user_agent = models.TextField(blank=True)
    event_source_url = models.CharField(max_length=2048, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Meta Order Attribution"
        verbose_name_plural = "Meta Order Attributions"


class MetaEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    event_id = models.CharField(max_length=128, unique=True)
    event_name = models.CharField(max_length=64, db_index=True)
    event_time = models.DateTimeField()
    event_source_url = models.CharField(max_length=2048, blank=True)
    action_source = models.CharField(max_length=32, default="website")
    custom_data = models.JSONField(default=dict)
    user_data = models.JSONField(default=dict)
    order = models.ForeignKey(
        "sitepages.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meta_events",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_name", "created_at"]),
        ]
        verbose_name = "Meta Event"
        verbose_name_plural = "Meta Events"
