import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from ..identity.service import AccessError

IST = ZoneInfo("Asia/Kolkata")
ENDPOINT = "https://www.tradeindia.com/utils/my_inquiry.html"
PAGE_SIZE = 100
MAX_PAGES = 50
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
            name = text(record.get("sender_name"), 200) or text(record.get("sender_co"), 200) or "TradeIndia enquiry"
            generated = datetime.fromtimestamp(int(record["generated"]), timezone.utc)
            leads.append({"source_record_id": identity, "name": name, "company": text(record.get("sender_co"), 200),
                          "phone": text(record.get("sender_mobile"), 100), "email": "",
                          "city": text(record.get("sender_city"), 200), "state": text(record.get("sender_state"), 200),
                          "address": "", "product": text(record.get("product_name"), 500),
                          "enquiry": clean_message(record.get("message")) or text(record.get("subject"), 2000),
                          "source_time": generated.isoformat()})
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AccessError(502, "provider_payload_invalid") from None
    return leads


async def _get_page(client: httpx.AsyncClient, params: dict) -> list:
    try:
        async with client.stream("GET", ENDPOINT, params=params) as response:
            if response.status_code in (401, 403):
                raise AccessError(502, "provider_credentials_rejected")
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


async def fetch_leads(client: httpx.AsyncClient, config: dict, key: str, start: datetime, end: datetime) -> list[dict]:
    if start >= end or (end - start).total_seconds() > 7 * 86400:
        raise AccessError(422, "provider_window_invalid")
    base = {"userid": config["user_id"], "profile_id": config["profile_id"], "key": key,
            "from_date": start.astimezone(IST).date().isoformat(), "to_date": end.astimezone(IST).date().isoformat(),
            "limit": PAGE_SIZE}
    leads: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        records = normalize_response(await _get_page(client, {**base, "page_no": page}))
        leads.extend(records)
        if len(records) < PAGE_SIZE:
            return leads
    raise AccessError(502, "provider_payload_too_large")
