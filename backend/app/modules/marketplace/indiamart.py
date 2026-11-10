from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

import httpx

from ...core.phone import normalize_phone
from ..identity.service import AccessError

IST = ZoneInfo("Asia/Kolkata")
ENDPOINT = "https://mapi.indiamart.com/wservce/crm/crmListing/v2/"
MAX_RECORDS = 10000
RELEASE_TIME = re.compile(r"(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")


class HistoryNotReady(AccessError):
    """IndiaMART releases leads older than a new key only 24 hours after the key was generated."""

    def __init__(self, until: datetime | None) -> None:
        super().__init__(409, "provider_history_not_ready")
        self.until = until


def release_time(message: str) -> datetime | None:
    match = RELEASE_TIME.search(message)
    if not match:
        return None
    try:
        generated = datetime.strptime(match.group(1), "%d-%m-%Y %H:%M:%S")
    except ValueError:
        return None
    return generated.replace(tzinfo=IST) + timedelta(hours=24)


def normalize_response(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        raise AccessError(502, "provider_response_rejected")
    code = str(payload.get("CODE"))
    message = payload.get("MESSAGE") if isinstance(payload.get("MESSAGE"), str) else ""
    if code == "204":
        # IndiaMART answers 204 both for "no leads" and for history that a new key cannot see yet.
        if "available after" in message.lower():
            raise HistoryNotReady(release_time(message))
        return []
    if code != "200" or payload.get("STATUS") != "SUCCESS":
        if code == "400" and "365" in message:
            raise AccessError(409, "provider_history_expired")
        raise AccessError(
            502,
            {
                "401": "provider_credentials_rejected",
                "403": "provider_credentials_rejected",
                "429": "provider_rate_limited",
                "500": "provider_unavailable",
                "503": "provider_unavailable",
            }.get(code, "provider_response_rejected"),
        )
    records = payload.get("RESPONSE")
    if payload.get("TOTAL_RECORDS") in (0, "0") and records in (None, [], ""):
        return []
    if isinstance(records, list) and len(records) > MAX_RECORDS:
        raise AccessError(502, "provider_payload_too_large")
    if not isinstance(records, list):
        raise AccessError(502, "provider_payload_invalid")
    leads = []
    try:
        if int(payload["TOTAL_RECORDS"]) != len(records):
            raise ValueError("Incomplete response")
        for record in records:
            identity = str(record["UNIQUE_QUERY_ID"]).strip()
            timestamp = datetime.strptime(
                record["QUERY_TIME"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=IST)
            if not identity or len(identity) > 200:
                raise ValueError("Missing record identity")

            def value(key: str) -> str:
                item = record.get(key) or ""
                if not isinstance(item, str) or len(item) > 16000:
                    raise ValueError("Invalid field")
                return item.strip()

            name = (
                value("SENDER_NAME") or value("SENDER_COMPANY") or "IndiaMART enquiry"
            )
            if len(name) > 200:
                raise ValueError("Name too long")
            leads.append(
                {
                    "source_record_id": identity,
                    "name": name,
                    "company": value("SENDER_COMPANY"),
                    "phone": normalize_phone(value("SENDER_MOBILE") or value("SENDER_MOBILE_ALT")),
                    "email": value("SENDER_EMAIL"),
                    "city": value("SENDER_CITY"),
                    "state": value("SENDER_STATE"),
                    "address": value("SENDER_ADDRESS"),
                    "product": value("QUERY_PRODUCT_NAME"),
                    "enquiry": value("QUERY_MESSAGE"),
                    "source_time": timestamp.isoformat(),
                }
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AccessError(502, "provider_payload_invalid") from None
    return leads


async def fetch_leads(
    client: httpx.AsyncClient, key: str, start: datetime, end: datetime
) -> list[dict]:
    if start >= end or (end - start).total_seconds() > 7 * 86400:
        raise AccessError(422, "provider_window_invalid")
    params = {
        "glusr_crm_key": key,
        "start_time": start.astimezone(IST).strftime("%d-%b-%Y%H:%M:%S"),
        "end_time": end.astimezone(IST).strftime("%d-%b-%Y%H:%M:%S"),
    }
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
            import json

            return normalize_response(json.loads(b"".join(chunks)))
    except httpx.HTTPError:
        raise AccessError(502, "provider_unavailable") from None
    except ValueError:
        raise AccessError(502, "provider_payload_invalid") from None
