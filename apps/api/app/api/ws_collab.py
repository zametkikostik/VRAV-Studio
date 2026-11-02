"""WebSocket collab rooms — auth required before accept.

Prefer: POST /collab/ticket then ?ticket=<one-time>
Legacy: ?token=<access JWT>
room_id is treated as project_id (UUID). User must be org member of that project.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.deps import CurrentUser

logger = logging.getLogger("vrav.ws_collab")
router = APIRouter(tags=["collab-ws"])

_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()

# ticket_id -> (user_id, expires_at_monotonic)
_tickets: dict[str, tuple[str, float]] = {}
_tickets_lock = asyncio.Lock()
_TICKET_TTL_SEC = 60.0
_cleanup_task: asyncio.Task | None = None


def purge_expired_tickets(now: float | None = None) -> int:
    """Remove expired tickets. Returns count removed. Safe to call sync from tests."""
    ts = time.monotonic() if now is None else now
    expired = [k for k, (_, exp) in list(_tickets.items()) if exp < ts]
    for k in expired:
        _tickets.pop(k, None)
    return len(expired)


async def _ticket_cleanup_loop() -> None:
    """Background loop: drop expired one-time tickets every 60s."""
    while True:
        await asyncio.sleep(60)
        async with _tickets_lock:
            n = purge_expired_tickets()
        if n:
            logger.info("cleaned %s expired collab WS tickets", n)


def _ensure_cleanup_task() -> None:
    global _cleanup_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = loop.create_task(_ticket_cleanup_loop())


async def consume_ticket(ticket: str) -> str | None:
    """One-time consume. Returns user_id or None if missing/expired/already used."""
    async with _tickets_lock:
        entry = _tickets.pop(ticket, None)
        if entry is None:
            return None
        user_id, exp = entry
        if time.monotonic() > exp:
            return None
        return user_id


async def issue_ticket(user_id: str) -> tuple[str, int]:
    """Create a short-lived one-time ticket. Returns (ticket_id, expires_in_sec)."""
    _ensure_cleanup_task()
    tid = secrets.token_urlsafe(24)
    async with _tickets_lock:
        purge_expired_tickets()
        _tickets[tid] = (user_id, time.monotonic() + _TICKET_TTL_SEC)
    return tid, int(_TICKET_TTL_SEC)


async def _join(room_id: str, ws: WebSocket) -> None:
    async with _lock:
        _rooms[room_id].add(ws)


async def _leave(room_id: str, ws: WebSocket) -> None:
    async with _lock:
        _rooms[room_id].discard(ws)
        if not _rooms[room_id]:
            _rooms.pop(room_id, None)


async def _broadcast(room_id: str, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
    payload = json.dumps(message, ensure_ascii=False)
    async with _lock:
        peers = list(_rooms.get(room_id, set()))
    dead: list[WebSocket] = []
    for peer in peers:
        if peer is exclude:
            continue
        try:
            await peer.send_text(payload)
        except Exception:
            dead.append(peer)
    for d in dead:
        await _leave(room_id, d)


async def _authorize_room(websocket: WebSocket, room_id: str) -> str | None:
    from app.core.security import decode_access_token
    from app.db.session import AsyncSessionLocal
    from app.models.organization import OrganizationMember
    from app.models.project import Project

    ticket = websocket.query_params.get("ticket")
    if ticket:
        user_id = await consume_ticket(ticket)
        if user_id is None:
            return None
    else:
        token = websocket.query_params.get("token")
        if not token:
            auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
            if auth and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        user_id = decode_access_token(token)
        if not user_id:
            return None
    try:
        project_uuid = uuid.UUID(room_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project).where(Project.id == project_uuid, Project.deleted_at.is_(None))
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None
            mem = await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == project.organization_id,
                    OrganizationMember.user_id == user_uuid,
                )
            )
            if mem.scalar_one_or_none() is None:
                return None
        return user_id
    except Exception as e:
        logger.warning("ws auth failed: %s", type(e).__name__)
        return None


@router.websocket("/ws/collab/{room_id}")
async def collab_ws(websocket: WebSocket, room_id: str):
    user_id = await _authorize_room(websocket, room_id)
    if user_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await _join(room_id, websocket)
    await _broadcast(
        room_id,
        {"type": "presence", "event": "join", "room_id": room_id, "user_id": user_id},
        exclude=websocket,
    )
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "invalid json"}))
                continue
            msg_type = data.get("type") or "event"
            out = {
                "type": msg_type,
                "room_id": room_id,
                "user_id": user_id,
                "payload": data.get("payload", data),
            }
            await _broadcast(room_id, out, exclude=None)
    except WebSocketDisconnect:
        pass
    finally:
        await _leave(room_id, websocket)
        await _broadcast(
            room_id,
            {"type": "presence", "event": "leave", "room_id": room_id, "user_id": user_id},
        )


@router.post("/collab/ticket")
async def create_collab_ticket(user: CurrentUser):
    """Issue a short-lived one-time ticket for WebSocket connect (avoid JWT in query)."""
    tid, expires_in = await issue_ticket(str(user.id))
    return {"ticket": tid, "expires_in": expires_in}
