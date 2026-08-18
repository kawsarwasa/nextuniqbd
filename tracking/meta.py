"""Meta Conversions API payload construction and transport."""

import hashlib
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


META_GRAPH_API_VERSION = "v22.0"
META_CAPI_TIMEOUT_SECONDS = 10


def is_browser_tracking_enabled():
    return bool(settings.META_TRACKING_ENABLED and settings.META_PIXEL_ID)


def is_capi_tracking_enabled():
    return bool(is_browser_tracking_enabled() and settings.META_CAPI_ACCESS_TOKEN)


def normalize_and_hash(value):
    normalized = " ".join(str(value or "").strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def normalize_phone(value):
    return "".join(character for character in str(value or "") if character.isdigit())


def request_attribution(request):
    return {
        "fbp": (request.COOKIES.get("_fbp") or "")[:255],
        "fbc": (request.COOKIES.get("_fbc") or "")[:255],
        "client_ip": request.META.get("REMOTE_ADDR") or "",
        "client_user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:2000],
        "event_source_url": request.build_absolute_uri()[:2048],
    }


def customer_data_from_request(request):
    attribution = request_attribution(request)
    user_data = {
        "fbp": attribution["fbp"],
        "fbc": attribution["fbc"],
        "client_ip_address": attribution["client_ip"],
        "client_user_agent": attribution["client_user_agent"],
    }
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        if user.email:
            user_data["em"] = [normalize_and_hash(user.email)]
        user_data["external_id"] = [normalize_and_hash(user.pk)]
    return {key: value for key, value in user_data.items() if value}


def customer_data_from_order(order):
    attribution = getattr(order, "meta_attribution", None)
    name_parts = (order.full_name or "").strip().split(maxsplit=1)
    user_data = {
        "em": [normalize_and_hash(order.email)] if order.email else [],
        "ph": [normalize_and_hash(normalize_phone(order.phone))] if order.phone else [],
        "fn": [normalize_and_hash(name_parts[0])] if name_parts else [],
        "ln": [normalize_and_hash(name_parts[1])] if len(name_parts) > 1 else [],
        "ct": [normalize_and_hash(order.district)] if order.district else [],
        "zp": [normalize_and_hash(order.postal_code)] if order.postal_code else [],
        "country": [normalize_and_hash("bd")],
        "fbp": attribution.fbp if attribution else "",
        "fbc": attribution.fbc if attribution else "",
        "client_ip_address": str(attribution.client_ip) if attribution and attribution.client_ip else "",
        "client_user_agent": attribution.client_user_agent if attribution else "",
    }
    if order.user_id:
        user_data["external_id"] = [normalize_and_hash(order.user_id)]
    return {key: value for key, value in user_data.items() if value}


def json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def post_capi_events(events):
    """Send a batch to the documented Graph API endpoint without logging PII or tokens."""
    endpoint = (
        f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/"
        f"{settings.META_PIXEL_ID}/events"
    )
    payload = {"data": events, "access_token": settings.META_CAPI_ACCESS_TOKEN}
    if settings.META_TEST_EVENT_CODE:
        payload["test_event_code"] = settings.META_TEST_EVENT_CODE

    request = Request(
        endpoint,
        data=json.dumps(payload, default=json_value).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=META_CAPI_TIMEOUT_SECONDS) as response:
            response_payload = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as error:
        raise RuntimeError(f"Meta CAPI returned HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Meta CAPI request failed.") from error

    if not response_payload.get("events_received"):
        raise RuntimeError("Meta CAPI did not acknowledge the event.")
    return response_payload
