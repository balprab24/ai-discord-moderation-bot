"""Async concurrency and pacing controls for moderation work."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, TypeVar


T = TypeVar("T")


class RateLimiter:
    """Limit concurrent moderation tasks and optionally pace their start time."""

    def __init__(self, max_concurrent: int = 8, min_interval_seconds: float = 0.0):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval_seconds = min_interval_seconds
        self._pace_lock = asyncio.Lock()
        self._next_start_at = 0.0

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a sync or async callable under the configured limits."""

        async with self._semaphore:
            await self._pace()
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result  # type: ignore[return-value]
            return result

    async def run(self, awaitable: Awaitable[T]) -> T:
        """Run an awaitable under the same limiter."""

        async with self._semaphore:
            await self._pace()
            return await awaitable

    async def _pace(self) -> None:
        if self._min_interval_seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        async with self._pace_lock:
            now = loop.time()
            wait_seconds = self._next_start_at - now
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = loop.time()
            self._next_start_at = now + self._min_interval_seconds

