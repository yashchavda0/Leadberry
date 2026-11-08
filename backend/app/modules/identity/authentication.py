from typing import Annotated
from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import text

from ...core.database import tenant_transaction

from .access import accept_invite
from .dependencies import User, identity, public_throttle, set_session
from .schemas import AcceptInvite, Login
from .security import CSRF_COOKIE, SESSION_COOKIE
from .service import AccessError

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
async def login(body: Login, request: Request, response: Response):
    service = await public_throttle(request, "login", f"{body.organization_slug}:{body.email}")
    return set_session(request, response, await service.login(body))


@router.post("/accept-invite")
async def accept_invitation(body: AcceptInvite, request: Request, response: Response):
    service = await public_throttle(request, "invite")
    return set_session(request, response, await accept_invite(service, body))


@router.post("/refresh")
async def refresh(
    request: Request, response: Response,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    service = await public_throttle(request, "refresh")
    token = request.cookies.get(SESSION_COOKIE)
    csrf = csrf_token
    if not token:
        raise AccessError(401, "authentication_required")
    if not csrf:
        raise AccessError(403, "csrf_required")
    return set_session(request, response, await service.refresh(token, csrf))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, user: User):
    await identity(request).logout(user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me")
async def me(request: Request, user: User):
    async with tenant_transaction(request.app.state.database_engine, user.org_id) as connection:
        landing_page = await connection.scalar(
            text("SELECT landing_page FROM crm.organization_memberships WHERE org_id=:org AND id=:member"),
            {"org": user.org_id, "member": user.member_id},
        )
    return {
        "organization_id": user.org_id, "membership_id": user.member_id,
        "user_id": user.user_id, "is_owner": user.is_owner,
        "permissions": sorted(user.permissions), "data_scope": user.data_scope,
        "landing_page": landing_page,
    }
