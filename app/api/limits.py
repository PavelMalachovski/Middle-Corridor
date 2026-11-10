"""Лимит размера тела запроса для API аккаунтов (ASGI-middleware)."""

from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

BODY_LIMIT = 64 * 1024
LIMITED_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/my",
    "/api/v1/orgs",
    "/api/v1/admin",
)


class BodyLimitMiddleware:
    """Больше `limit` байт — 413: по Content-Length сразу, потоковое тело — по факту.

    Тело ограниченных путей читается целиком (не больше лимита) и отдаётся приложению
    заново — так лимит соблюдается, даже если клиент не прислал Content-Length.
    """

    def __init__(
        self, app: ASGIApp, limit: int = BODY_LIMIT, prefixes: Iterable[str] = LIMITED_PREFIXES
    ) -> None:
        self.app = app
        self.limit = limit
        self.prefixes = tuple(prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefixes):
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            try:
                too_big = int(length) > self.limit
            except ValueError:
                await JSONResponse({"detail": "bad_request"}, status_code=400)(scope, receive, send)
                return
            if too_big:
                await self._reject(scope, receive, send)
                return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await self._reject(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"detail": "too_large"}, status_code=413)(scope, receive, send)
