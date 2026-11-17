"""Cap the requests in flight to the DB connections this process has.

Without it, the API froze under load (k6 `user_activity`, 100 events/s): FastAPI runs sync
endpoints *and* their response validation on the same 40-thread pool. Once 40 requests were
waiting for one of the 10 DB connections, the 10 requests holding a connection could not get a
thread to validate their response and commit, so nobody moved until the pool timeout (30 s).
Queuing the excess in the event loop is cheap and keeps every admitted request able to finish.
"""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


class ConcurrencyLimit:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.slots = asyncio.Semaphore(limit)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        async with self.slots:
            await self.app(scope, receive, send)
