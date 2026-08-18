from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracking.meta import is_capi_tracking_enabled, post_capi_events
from tracking.models import MetaEvent


class Command(BaseCommand):
    help = "Send pending and retryable Meta Conversions API events."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not is_capi_tracking_enabled():
            self.stdout.write("Meta CAPI is disabled or not configured; no events sent.")
            return

        event_ids = list(
            MetaEvent.objects.filter(status__in=[MetaEvent.Status.PENDING, MetaEvent.Status.FAILED])
            .order_by("created_at", "id")
            .values_list("id", flat=True)[: max(options["limit"], 0)]
        )
        sent_count = 0
        failed_count = 0
        for event_id in event_ids:
            with transaction.atomic():
                event = MetaEvent.objects.select_for_update().get(pk=event_id)
                if event.status == MetaEvent.Status.SENT:
                    continue
                payload = {
                    "event_name": event.event_name,
                    "event_time": int(event.event_time.timestamp()),
                    "event_id": event.event_id,
                    "event_source_url": event.event_source_url,
                    "action_source": event.action_source,
                    "custom_data": event.custom_data,
                    "user_data": event.user_data,
                }
                try:
                    post_capi_events([payload])
                except Exception:
                    event.status = MetaEvent.Status.FAILED
                    event.attempt_count += 1
                    # Keep queue diagnostics safe: upstream responses can contain
                    # request details that should not be stored or logged.
                    event.last_error = "Meta CAPI delivery failed."
                    event.save(update_fields=["status", "attempt_count", "last_error"])
                    failed_count += 1
                else:
                    event.status = MetaEvent.Status.SENT
                    event.attempt_count += 1
                    event.last_error = ""
                    event.sent_at = timezone.now()
                    event.save(update_fields=["status", "attempt_count", "last_error", "sent_at"])
                    sent_count += 1

        self.stdout.write(f"Meta events sent: {sent_count}; failed: {failed_count}.")
