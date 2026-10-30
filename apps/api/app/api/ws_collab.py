"""WebSocket collab rooms — in-memory fan-out (single API process).

For multi-replica production, back with Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("vrav.ws_collab")
router = APIRouter(tags=["collab-ws"])

_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


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


@router.websocket("/ws/collab/{room_id}")
async def collab_ws(websocket: WebSocket, room_id: str):
    await websocket.accept()
    await _join(room_id, websocket)
    await _broadcast(
        room_id,
        {"type": "presence", "event": "join", "room_id": room_id},
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
                "payload": data.get("payload"),
                "event_type": data.get("event_type"),
                "client_id": data.get("client_id"),
            }
            await _broadcast(room_id, out, exclude=None)
    except WebSocketDisconnect:
        pass
    finally:
        await _leave(room_id, websocket)
        await _broadcast(
            room_id,
            {"type": "presence", "event": "leave", "room_id": room_id},
        )
