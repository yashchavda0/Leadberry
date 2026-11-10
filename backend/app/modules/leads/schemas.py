import math
from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, field_validator

from ...core.phone import normalize_phone
from ..identity.schemas import Input


class LeadInput(Input):
    name: str = Field(min_length=1, max_length=200)
    company: str = Field("", max_length=200)
    phone: str = Field("", max_length=40)
    email: EmailStr | None = None
    city: str = Field("", max_length=100)
    state: str = Field("", max_length=100)
    address: str = Field("", max_length=1000)
    product: str = Field("", max_length=200)
    enquiry: str = Field("", max_length=10000)
    source_provider: str = Field("manual", pattern=r"^[a-z0-9_-]{1,100}$")
    status_id: UUID | None = None
    assigned_membership_id: UUID | None = None
    team_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    custom_fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=50)
    next_follow_up_at: AwareDatetime | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        if any(not tag.strip() or len(tag.strip()) > 50 for tag in values):
            raise ValueError("Tags must contain 1–50 characters")
        return sorted(set(tag.strip() for tag in values))

    @field_validator("custom_fields")
    @classmethod
    def validate_fields(cls, fields: dict) -> dict:
        if any(
            not key.strip() or len(key) > 100
            or (isinstance(value, str) and len(value) > 1000)
            or (isinstance(value, float) and not math.isfinite(value))
            for key, value in fields.items()
        ):
            raise ValueError("Custom field names and values exceed supported limits")
        return fields


class LeadUpdate(LeadInput):
    row_version: int = Field(ge=1)


class LeadStatusChange(Input):
    status_id: UUID
    note: str = Field(min_length=1, max_length=2000)
    next_follow_up_at: AwareDatetime | None = None
    row_version: int = Field(ge=1)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A note is required for a status change")
        return value


class VersionInput(Input):
    row_version: int = Field(ge=1)


class TeamInput(Input):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    membership_ids: list[UUID] = Field(default_factory=list, max_length=200)
