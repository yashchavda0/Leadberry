from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

Scope = Literal["own", "team", "all"]
LandingPage = Literal["/", "/leads", "/users", "/settings", "/marketplace", "/account"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Credentials(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class Login(Credentials):
    organization_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")


class Onboard(Login):
    organization_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA timezone") from None
        return value


class RoleInput(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    data_scope: Scope = "own"
    permissions: list[str] = Field(default_factory=list, max_length=100)
    is_active: bool = True
    reports_to_role_id: UUID | None = None


class OrganizationInput(Input):
    name: str = Field(min_length=1, max_length=200)
    timezone: str
    logo_url: str | None = Field(None, max_length=500)
    website: str | None = Field(None, max_length=300)
    industry: str | None = Field(None, max_length=100)
    company_size: Literal["1-10", "11-50", "51-200", "201-500", "500+"] | None = None
    business_email: EmailStr | None = None
    business_phone: str | None = Field(None, pattern=r"^[+0-9 ()-]{6,20}$")
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, pattern=r"^[A-Za-z0-9 -]{3,12}$")
    country: str = Field("IN", pattern=r"^[A-Z]{2}$")
    currency: str = Field("INR", pattern=r"^[A-Z]{3}$")
    gstin: str | None = Field(
        None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    )

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("logo_url", "website")
    @classmethod
    def https_only(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Use a secure https:// address")
        return value

    @field_validator("business_email")
    @classmethod
    def lower_email(cls, value):
        return str(value).lower() if value else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return Onboard.validate_timezone(value)


class InviteInput(Input):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role_ids: list[UUID] = Field(default_factory=list, max_length=20)
    visibility_override: Scope | None = None
    landing_page: LandingPage | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class AcceptInvite(Input):
    invitation_token: SecretStr = Field(min_length=100, max_length=250)
    password: SecretStr = Field(min_length=12, max_length=128)


class ProfileInput(Input):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=40)
    job_title: str | None = Field(None, max_length=120)


class MembershipUpdate(Input):
    status: Literal["active", "disabled"]
    role_ids: list[UUID] = Field(default_factory=list, max_length=20)
    visibility_override: Scope | None = None
    is_owner: bool | None = None
    permission_overrides: dict[str, bool] = Field(default_factory=dict, max_length=100)
    landing_page: LandingPage | None = None
    display_name: str | None = Field(None, min_length=1, max_length=200)
