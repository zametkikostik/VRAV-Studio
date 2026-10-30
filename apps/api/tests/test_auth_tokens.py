import asyncio

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_token,
)


def test_access_and_refresh_types():
    access = create_access_token("user-1")
    refresh = create_refresh_token("user-1")
    assert decode_access_token(access) == "user-1"
    assert decode_access_token(refresh) is None
    payload = decode_token(refresh, expected_type="refresh")
    assert payload is not None
    assert payload["sub"] == "user-1"


def test_rate_limiter():
    from app.core.rate_limit import SlidingWindowLimiter

    async def _run():
        lim = SlidingWindowLimiter(max_calls=3, window_seconds=60)
        assert await lim.allow("a")
        assert await lim.allow("a")
        assert await lim.allow("a")
        assert not await lim.allow("a")

    asyncio.run(_run())
