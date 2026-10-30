import asyncio
import os

from app.services.email import ConsoleEmailProvider, get_email_provider
from app.core.rate_limit import SlidingWindowLimiter, RedisSlidingWindowLimiter


def test_console_email():
    async def _run():
        p = ConsoleEmailProvider()
        await p.send(to="a@b.c", subject="t", text="hello")

    asyncio.run(_run())


def test_get_email_provider_default():
    os.environ.pop("EMAIL_PROVIDER", None)
    p = get_email_provider()
    assert isinstance(p, ConsoleEmailProvider)


def test_memory_limiter_async():
    async def _run():
        lim = SlidingWindowLimiter(2, 60)
        assert await lim.allow("k")
        assert await lim.allow("k")
        assert not await lim.allow("k")

    asyncio.run(_run())
