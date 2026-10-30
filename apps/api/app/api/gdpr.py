from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession
from app.services.gdpr import anonymize_user, export_user_data, purge_soft_deleted
from app.core.config import get_settings

router = APIRouter(prefix="/gdpr", tags=["gdpr"])


@router.get("/export")
async def export_my_data(user: CurrentUser, db: DbSession):
    data = await export_user_data(db, user.id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="vrav-export-{user.id}.json"'},
    )


@router.post("/delete")
async def delete_my_account(user: CurrentUser, db: DbSession):
    try:
        result = await anonymize_user(db, user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "anonymized", **result}


@router.post("/admin/purge")
async def admin_purge(user: CurrentUser, db: DbSession):
    settings = get_settings()
    if settings.environment == "production":
        raise HTTPException(status_code=403, detail="Use ops tooling / internal role")
    n = await purge_soft_deleted(db, retention_days=settings.gdpr_retention_days)
    return {"purged": n}
