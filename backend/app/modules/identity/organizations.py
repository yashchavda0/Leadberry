from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from ...core.database import tenant_transaction
from .dependencies import User, public_throttle, set_session
from .schemas import Onboard, OrganizationInput
from .service import audit, authorize_mutation

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/onboard", status_code=201)
async def onboard(body: Onboard, request: Request, response: Response):
    service = await public_throttle(request, "onboard")
    org, tokens = await service.onboard(body)
    return {**set_session(request, response, tokens), "organization_id": org}


PROFILE = (
    "logo_url",
    "website",
    "industry",
    "company_size",
    "business_email",
    "business_phone",
    "address",
    "city",
    "state",
    "postal_code",
    "country",
    "currency",
    "gstin",
)


@router.get("/me")
async def organization(request: Request, user: User):
    async with tenant_transaction(
        request.app.state.database_engine, user.org_id
    ) as connection:
        row = (
            (
                await connection.execute(
                    text(
                        f"SELECT id,slug,name,timezone,status,authz_version,{','.join(PROFILE)} FROM crm.organizations WHERE id=:org"
                    ),
                    {"org": user.org_id},
                )
            )
            .mappings()
            .one()
        )
        return dict(row)


@router.put("/me")
async def organization_update(body: OrganizationInput, request: Request, user: User):
    async with tenant_transaction(
        request.app.state.database_engine, user.org_id
    ) as connection:
        await authorize_mutation(connection, user, "settings.manage")
        assignments = ",".join(f"{column}=:{column}" for column in PROFILE)
        await connection.execute(
            text(
                f"UPDATE crm.organizations SET name=:name,timezone=:zone,{assignments},settings_version=settings_version+1,updated_at=now() WHERE id=:org"
            ),
            {
                "org": user.org_id,
                "name": body.name,
                "zone": body.timezone,
                **{column: getattr(body, column) for column in PROFILE},
            },
        )
        await audit(
            connection, user.org_id, user.member_id, "organization.updated", user.org_id
        )
        return {"status": "updated"}
