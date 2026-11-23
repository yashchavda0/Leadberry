from typing import Annotated
from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import text

from ...core.database import tenant_transaction

from .access import accept_invite
from .dependencies import User, identity, public_throttle, set_session
from .schemas import AcceptInvite, Login, ProfileInput
from .security import CSRF_COOKIE, SESSION_COOKIE
from .service import AccessError

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
async def login(body: Login, request: Request, response: Response):
    service = await public_throttle(
        request, "login", f"{body.organization_slug}:{body.email}"
    )
    return set_session(request, response, await service.login(body))


@router.post("/accept-invite")
async def accept_invitation(body: AcceptInvite, request: Request, response: Response):
    service = await public_throttle(request, "invite")
    return set_session(request, response, await accept_invite(service, body))


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
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
    async with tenant_transaction(
        request.app.state.database_engine, user.org_id
    ) as connection:
        member = (
            (
                await connection.execute(
                    text(
                        "SELECT landing_page,display_name FROM crm.organization_memberships WHERE org_id=:org AND id=:member"
                    ),
                    {"org": user.org_id, "member": user.member_id},
                )
            )
            .mappings()
            .one()
        )
    return {
        "organization_id": user.org_id,
        "membership_id": user.member_id,
        "user_id": user.user_id,
        "is_owner": user.is_owner,
        "permissions": sorted(user.permissions),
        "data_scope": user.data_scope,
        "landing_page": member["landing_page"],
        "display_name": member["display_name"],
    }


@router.get("/profile")
async def profile(request: Request, user: User):
    async with tenant_transaction(identity(request).engine, user.org_id) as connection:
        member = (
            (
                await connection.execute(
                    text(
                        "SELECT m.display_name,m.phone,m.job_title,m.date_of_birth,m.gender,m.address,m.city,m.state,u.email FROM crm.organization_memberships m "
                        "JOIN crm.app_users u ON u.id=m.user_id WHERE m.org_id=:org AND m.id=:member"
                    ),
                    {"org": user.org_id, "member": user.member_id},
                )
            )
            .mappings()
            .one()
        )
    return dict(member)


@router.put("/profile", status_code=204)
async def update_profile(body: ProfileInput, request: Request, user: User):
    async with tenant_transaction(identity(request).engine, user.org_id) as connection:
        result = await connection.execute(
            text(
                "UPDATE crm.organization_memberships SET display_name=:display_name,phone=:phone,"
                "job_title=:job_title,date_of_birth=:date_of_birth,gender=:gender,address=:address,city=:city,state=:state,"
                "updated_at=now() WHERE org_id=:org AND id=:member AND status='active'"
            ),
            {**body.model_dump(), "org": user.org_id, "member": user.member_id},
        )
        if result.rowcount != 1:
            raise AccessError(403, "permission_denied")
