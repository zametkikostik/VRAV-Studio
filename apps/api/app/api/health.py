from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "vrav-api", "version": "0.2.2"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    result.scalar()
    return {"status": "ok", "database": "connected"}


@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    redis_status = "skipped"
    try:
        import os
        import redis

        url = os.getenv("REDIS_URL", "")
        if url:
            r = redis.from_url(url, socket_connect_timeout=1)
            r.ping()
            redis_status = "ok"
    except Exception as e:
        redis_status = f"error:{e.__class__.__name__}"
    status = "ok" if redis_status in ("ok", "skipped") else "degraded"
    return {"status": status, "database": "ok", "redis": redis_status}
