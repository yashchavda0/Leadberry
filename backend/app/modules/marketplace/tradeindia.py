import html
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from ..identity.service import AccessError

IST = ZoneInfo("Asia/Kolkata")
ENDPOINT = "https://www.tradeindia.com/utils/my_inquiry.html"
PAGE_SIZE = 100
# TradeIndia allows 5 requests per 5 minutes per key; one run never exceeds that.
MAX_PAGES = 5
TAG = re.compile(r"<[^>]*>")


def text(value, limit: int = 16000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid field")
    return value.strip()


def clean_message(value) -> str:
    return " ".join(html.unescape(TAG.sub(" ", text(value))).split())


def normalize_response(payload) -> list[dict]:
    if not isinstance(payload, list) or len(payload) > PAGE_SIZE:
        raise AccessError(502, "provider_payload_invalid")
    leads = []
    try:
        for record in payload:
            if record.get("rfi_id") is None:
                raise ValueError("Missing record identity")
            identity = text(str(record["rfi_id"]), 200)
            if not identity:
                raise ValueError("Missing record identity")
            name = (
                text(record.get("sender_name"), 200)
                or text(record.get("sender_co"), 200)
                or "TradeIndia enquiry"
            )
            generated = datetime.fromtimestamp(int(record["generated"]), timezone.utc)
            leads.append(
                {
                    "source_record_id": identity,
                    "name": name,
                    "company": text(record.get("sender_co"), 200),
                    "phone": text(record.get("sender_mobile"), 100),
                    "email": "",
                    "city": text(record.get("sender_city"), 200),
                    "state": text(record.get("sender_state"), 200),
                    "address": "",
                    "product": text(record.get("product_name"), 500),
                    "enquiry": clean_message(record.get("message"))
                    or text(record.get("subject"), 2000),
                    "source_time": generated.isoformat(),
                }
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AccessError(502, "provider_payload_invalid") from None
    return leads


async def _get_page(client: httpx.AsyncClient, params: dict) -> list:
    try:
        async with client.stream("GET", ENDPOINT, params=params) as response:
            if response.status_code in (401, 403):
                # TradeIndia reports quota exhaustion as 403 with a "Rate limit exceed" message.
                body = (
                    (await response.aread())[:2048].decode("utf-8", "replace").lower()
                )
                raise AccessError(
                    502,
                    (
                        "provider_rate_limited"
                        if "rate limit" in body
                        else "provider_credentials_rejected"
                    ),
                )
            if response.status_code == 429:
                raise AccessError(502, "provider_rate_limited")
            if response.status_code != 200:
                raise AccessError(502, "provider_unavailable")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise AccessError(502, "provider_payload_too_large")
                chunks.append(chunk)
    except httpx.HTTPError:
        raise AccessError(502, "provider_unavailable") from None
    try:
        return json.loads(b"".join(chunks))
    except ValueError:
        raise AccessError(502, "provider_payload_invalid") from None


async def fetch_pages(
    client: httpx.AsyncClient,
    config: dict,
    key: str,
    start: datetime,
    end: datetime,
    first_page: int = 1,
) -> tuple[list[dict], int | None]:
    """Returns the leads and the page to continue from in the next slot, if the window has more."""
    first_day = start.astimezone(IST).date()
    last_day = (end - timedelta(microseconds=1)).astimezone(IST).date()
    # TradeIndia rejects ranges longer than one day with HTTP 400.
    if start >= end or first_day != last_day:
        raise AccessError(422, "provider_window_invalid")
    base = {
        "userid": config["user_id"],
        "profile_id": config["profile_id"],
        "key": key,
        "from_date": first_day.isoformat(),
        "to_date": last_day.isoformat(),
        "limit": PAGE_SIZE,
    }
    leads: list[dict] = []
    for page in range(first_page, first_page + MAX_PAGES):
        records = normalize_response(await _get_page(client, {**base, "page_no": page}))
        leads.extend(records)
        if len(records) < PAGE_SIZE:
            return leads, None
    return leads, first_page + MAX_PAGES


async def fetch_leads(
    client: httpx.AsyncClient, config: dict, key: str, start: datetime, end: datetime
) -> list[dict]:
    leads, more = await fetch_pages(client, config, key, start, end)
    if more:
        raise AccessError(502, "provider_payload_too_large")
    return leads
