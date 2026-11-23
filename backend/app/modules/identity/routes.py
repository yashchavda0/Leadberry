from fastapi import APIRouter

from .authentication import router as authentication_router
from .memberships import router as memberships_router
from .organizations import router as organizations_router
from .platform import router as platform_router
from .role_routes import router as roles_router

router = APIRouter(prefix="/api/v1")
router.include_router(authentication_router)
router.include_router(organizations_router)
router.include_router(roles_router)
router.include_router(memberships_router)
router.include_router(platform_router)
