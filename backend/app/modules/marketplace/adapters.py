"""Provider adapter registry. Each provider is pulled through the same run contract."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, TypeAlias

import httpx

from ..identity.service import AccessError
from . import indiamart, tradeindia

NormalizedLead: TypeAlias = dict[str, Any]
FetchResult: TypeAlias = list[NormalizedLead] | tuple[list[NormalizedLead], int | None]
Fetch = Callable[
    [httpx.AsyncClient, dict[str, Any], dict[str, str], datetime, datetime, str, int],
    Awaitable[FetchResult],
]


async def _indiamart(client, config, credentials, start, end, kind, page):
    return await indiamart.fetch_leads(client, credentials["crm_key"], start, end)


async def _tradeindia(client, config, credentials, start, end, kind, page):
    if kind == "backfill":
        return await tradeindia.fetch_pages(
            client, config, credentials["api_key"], start, end, page
        )
    return await tradeindia.fetch_leads(
        client, config, credentials["api_key"], start, end
    )


REGISTRY: dict[str, Fetch] = {"indiamart": _indiamart, "tradeindia": _tradeindia}
_REQUIRED_LEAD_FIELDS = ("source_record_id", "name", "source_time")
_OPTIONAL_LEAD_FIELDS = (
    "company",
    "phone",
    "email",
    "city",
    "state",
    "address",
    "product",
    "enquiry",
    "campaign_id",
    "ad_id",
    "form_id",
    "description",
)


def validate_result(result: object) -> FetchResult:
    next_page: int | None = None
    leads: object = result
    if isinstance(result, tuple):
        if len(result) != 2 or not isinstance(result[1], (int, type(None))):
            raise AccessError(502, "provider_payload_invalid")
        leads, next_page = result
    if not isinstance(leads, list):
        raise AccessError(502, "provider_payload_invalid")

    normalized: list[NormalizedLead] = []
    for lead in leads:
        if not isinstance(lead, Mapping):
            raise AccessError(502, "provider_payload_invalid")
        item = dict(lead)
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in _REQUIRED_LEAD_FIELDS):
            raise AccessError(502, "provider_payload_invalid")
        try:
            source_time = datetime.fromisoformat(item["source_time"])
        except ValueError:
            raise AccessError(502, "provider_payload_invalid") from None
        if source_time.tzinfo is None:
            raise AccessError(502, "provider_payload_invalid")
        if any(field in item and item[field] is not None and not isinstance(item[field], str) for field in _OPTIONAL_LEAD_FIELDS):
            raise AccessError(502, "provider_payload_invalid")
        normalized.append(item)
    return (normalized, next_page) if isinstance(result, tuple) else normalized


async def fetch(
    code: str,
    client: httpx.AsyncClient,
    config: dict[str, Any],
    credentials: dict[str, str],
    start: datetime,
    end: datetime,
    kind: str,
    page: int,
) -> FetchResult:
    try:
        adapter = REGISTRY[code]
    except KeyError:
        raise AccessError(502, "provider_not_supported") from None
    return validate_result(
        await adapter(client, config, credentials, start, end, kind, page)
    )
