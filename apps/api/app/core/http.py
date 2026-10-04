"""Bound incoming bodies and add browser ingest CORS without opening admin CORS."""

from starlette.responses import JSONResponse


class RequestGuard:
    def __init__(self, app, max_bytes=1_048_576):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ingest = scope["path"] in ("/api/v1/ingest", "/api/v1/ingest/events", "/api/v1/ingest/ping")
        cors = [
            (b"access-control-allow-origin", b"*"),
            (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
            (b"access-control-allow-headers", b"Content-Type, X-Write-Key"),
            (b"access-control-max-age", b"600"),
        ]

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                existing = message.get("headers", [])
                if ingest:
                    existing = [(k, v) for k, v in existing if not k.startswith(b"access-control-")]
                    existing += cors
                message["headers"] = (
                    existing
                    + [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                    if scope["path"].startswith("/api/")
                    else existing
                )
            await send(message)

        if ingest and scope["method"] == "OPTIONS":
            return await JSONResponse({"ok": True})(scope, receive, guarded_send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                return await JSONResponse(
                    {"detail": "Request body exceeds 1 MiB"}, status_code=413
                )(scope, receive, guarded_send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, guarded_send)
