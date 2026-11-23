import asyncio
import base64
import hashlib
import hmac
import secrets
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SESSION_COOKIE = "crm_session"
CSRF_COOKIE = "crm_csrf"
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def opaque_token(org_id: UUID, entity_id: UUID) -> str:
    return f"{org_id}.{entity_id}.{secrets.token_urlsafe(32)}"


def invitation_token(org_id: UUID, invite_id: UUID, key: bytes) -> str:
    signature = hmac.digest(
        key, b"crm-invitation:v1:" + org_id.bytes + invite_id.bytes, "sha256"
    )
    secret = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{org_id}.{invite_id}.{secret}"


def parse_token(value: str) -> tuple[UUID, UUID]:
    parts = value.split(".")
    if len(parts) != 3 or len(parts[2]) != 43:
        raise ValueError("Invalid token")
    return UUID(parts[0]), UUID(parts[1])


class PasswordService:
    def __init__(self) -> None:
        self.capacity = asyncio.Semaphore(4)

    async def hash(self, password: str) -> str:
        async with self.capacity:
            return await asyncio.to_thread(hasher.hash, password)

    async def verify(self, password: str, stored_hash: str | None) -> bool:
        def verify() -> bool:
            try:
                return (
                    hasher.verify(stored_hash or DUMMY_HASH, password)
                    and stored_hash is not None
                )
            except VerifyMismatchError:
                return False
            except (InvalidHashError, VerificationError):
                # Corrupt stored credentials are an operational error, not a valid login.
                raise RuntimeError("Stored password hash is invalid") from None

        async with self.capacity:
            return await asyncio.to_thread(verify)
