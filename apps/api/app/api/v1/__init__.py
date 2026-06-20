from fastapi import APIRouter

from .dashboard import router as dashboard_router
from .issues import router as issues_router
from .pull_requests import router as prs_router
from .release import router as release_router
from .reports import router as reports_router
from .repositories import router as repos_router
from .webhooks import router as webhooks_router

router = APIRouter()
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(repos_router, prefix="/repositories", tags=["repositories"])
router.include_router(issues_router, prefix="/issues", tags=["issues"])
router.include_router(prs_router, prefix="/pull-requests", tags=["pull-requests"])
router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
router.include_router(reports_router, prefix="/reports", tags=["reports"])
router.include_router(release_router, prefix="/releases", tags=["releases"])
