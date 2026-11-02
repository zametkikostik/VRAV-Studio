"""Fix 3: collab WS one-time tickets + expiry purge."""
from __future__ import annotations

import asyncio
import time

from app.api import ws_collab as ws


def setup_function():
    ws._tickets.clear()


def test_purge_expired_tickets_removes_only_expired():
    now = time.monotonic()
    ws._tickets["alive"] = ("u1", now + 100)
    ws._tickets["dead"] = ("u2", now - 1)
    n = ws.purge_expired_tickets(now=now)
    assert n == 1
    assert "alive" in ws._tickets
    assert "dead" not in ws._tickets


def test_consume_ticket_is_one_time():
    async def _run():
        tid, _ = await ws.issue_ticket("user-abc")
        first = await ws.consume_ticket(tid)
        second = await ws.consume_ticket(tid)
        assert first == "user-abc"
        assert second is None

    asyncio.run(_run())


def test_consume_expired_ticket_returns_none():
    async def _run():
        ws._tickets["t1"] = ("user-x", time.monotonic() - 5)
        assert await ws.consume_ticket("t1") is None
        assert "t1" not in ws._tickets  # popped

    asyncio.run(_run())


def test_issue_ticket_returns_ttl():
    async def _run():
        tid, expires_in = await ws.issue_ticket("u")
        assert isinstance(tid, str) and len(tid) >= 16
        assert expires_in == int(ws._TICKET_TTL_SEC)
        assert tid in ws._tickets

    asyncio.run(_run())


def test_cleanup_loop_and_helpers_exist():
    assert callable(ws.purge_expired_tickets)
    assert callable(ws._ticket_cleanup_loop)
    assert callable(ws.consume_ticket)
    assert callable(ws.issue_ticket)
