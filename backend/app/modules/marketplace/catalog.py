from ..identity.service import AccessError


def field(key: str, label: str, secret: bool = False, required: bool = True) -> dict:
    return {"key": key, "label": label, "secret": secret, "required": required}


INTERVALS = [300, 600, 900, 1200, 1800, 3600]


def schedule(
    window_unit: str,
    window_days: int,
    history_days: int,
    empty_stop_windows: int | None,
) -> dict:
    return {
        "min_interval_seconds": 300,
        "slot_guard_seconds": 15,
        "cooldown_seconds": 900,
        "allowed_intervals": INTERVALS,
        "default_interval_seconds": 900,
        "max_window_seconds": window_days * 86400,
        "window_unit": window_unit,
        "history_days": history_days,
        "empty_stop_windows": empty_stop_windows,
    }


PROVIDERS = [
    {
        "code": "indiamart",
        "name": "IndiaMART",
        "category": "marketplace",
        "method": "CRM key / Pull API",
        "setup": True,
        "adapter": True,
        "multiple_accounts": True,
        **schedule("second", 7, 365, None),
        "fields": [field("crm_key", "API key", True)],
        "documentation_url": "https://help.indiamart.com/knowledge-base/lms-crm-integration-v2/",
        "note": "Requires IndiaMART LMS API entitlement. One request per key every five minutes; IndiaMART recommends syncing every 10-15 minutes. Up to 365 days of past leads can be imported in 7-day windows.",
    },
    {
        "code": "tradeindia",
        "name": "TradeIndia",
        "category": "marketplace",
        "method": "Inquiry API (User ID, profile ID and API key)",
        "setup": True,
        "adapter": True,
        "multiple_accounts": None,
        # Verified 2026-11-08: ranges over one day return HTTP 400; a 190-day-old day still returned inquiries.
        **schedule("day", 1, 365, 30),
        "fields": [
            field("user_id", "User ID"),
            field("profile_id", "Profile ID"),
            field("api_key", "API key", True),
        ],
        "documentation_url": "https://www.tradeindia.com/utils/my_inquiry.html",
        "note": "Pulls inquiries one calendar day per request on the chosen interval. TradeIndia allows 5 requests per 5 minutes and blocks the key for 15 minutes when exceeded, so avoid using the same key elsewhere. Past inquiries (up to 365 days) are imported one day per request.",
    },
    {
        "code": "facebook",
        "name": "Meta Lead Ads",
        "category": "social",
        "method": "OAuth / Leadgen webhooks",
        "setup": False,
        "adapter": False,
        "multiple_accounts": True,
        "fields": [],
        "documentation_url": "https://developers.facebook.com/docs/marketing-api/guides/lead-ads/retrieving/",
        "note": "Requires an approved Meta app, Page permissions and a public HTTPS callback.",
    },
    {
        "code": "shopify",
        "name": "Shopify",
        "category": "commerce",
        "method": "Store OAuth / Signed webhooks",
        "setup": False,
        "adapter": False,
        "multiple_accounts": True,
        "fields": [],
        "documentation_url": "https://shopify.dev/docs/apps/build/authentication-authorization",
        "note": "Customers and orders will be separate leads. App registration and data permissions are required.",
    },
    {
        "code": "google_forms",
        "name": "Google Forms",
        "category": "form",
        "method": "Authorized Apps Script bridge",
        "setup": False,
        "adapter": False,
        "multiple_accounts": True,
        "fields": [],
        "documentation_url": "https://developers.google.com/apps-script/guides/triggers/installable",
        "note": "Requires a per-form authenticated bridge and stable submission identity.",
    },
    {
        "code": "website_api",
        "name": "Website / API",
        "category": "api",
        "method": "Scoped machine-key intake",
        "setup": False,
        "adapter": False,
        "multiple_accounts": True,
        "fields": [],
        "documentation_url": None,
        "note": "Scoped intake and revocation tests must pass before keys can be issued.",
    },
    {
        "code": "custom_forms",
        "name": "Custom forms",
        "category": "form",
        "method": "Authenticated form intake",
        "setup": False,
        "adapter": False,
        "multiple_accounts": True,
        "fields": [],
        "documentation_url": None,
        "note": "Server-side validation, abuse protection and consent rules are required.",
    },
    *[
        {
            "code": code,
            "name": name,
            "category": "telephony" if code == "ivr" else "marketplace",
            "method": method,
            "setup": False,
            "adapter": False,
            "multiple_accounts": None,
            "fields": [],
            "documentation_url": (
                "https://www.cronberry.com/integration.html"
                if code in ("justdial", "ivr")
                else None
            ),
            "note": "Provider authentication, payloads and account constraints need verification.",
        }
        for code, name, method in [
            ("justdial", "JustDial", "Provider-configured lead posting"),
            ("sulekha", "Sulekha", "Contract pending"),
            ("99acres", "99acres", "Contract pending"),
            ("magicbricks", "MagicBricks", "Contract pending"),
            ("ivr", "IVR / MyTelly", "Vendor-specific call events"),
        ]
    ],
]


def provider(code: str) -> dict:
    for item in PROVIDERS:
        if item["code"] == code:
            return item
    raise AccessError(404, "provider_not_found")


def validate_configuration(
    code: str,
    config: dict[str, str],
    credentials: dict[str, str],
    replacing: bool = False,
) -> None:
    item = provider(code)
    if not item["setup"]:
        raise AccessError(409, "provider_setup_unavailable")
    public = {value["key"] for value in item["fields"] if not value["secret"]}
    secrets = {value["key"] for value in item["fields"] if value["secret"]}
    legacy = {"mobile"} if code == "indiamart" else set()
    if set(config) - legacy != public or not all(
        value.strip() for key, value in config.items() if key not in legacy
    ):
        raise AccessError(422, "invalid_provider_configuration")
    if (not replacing and set(credentials) != secrets) or not set(
        credentials
    ) <= secrets:
        raise AccessError(422, "invalid_provider_credentials")
    if credentials and (
        set(credentials) != secrets
        or not all(value.strip() for value in credentials.values())
    ):
        raise AccessError(422, "invalid_provider_credentials")
