"""Admin API router for the consilium chat facade.

The router is deliberately pure over ``request.app.state``: every handler reads a
callable off ``app.state`` and returns its result. Real implementations (which call
the council/consilium reuse functions) are injected by the wiring task; here the
router only consumes the injected callables, so it is hermetically testable with
fakes.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def admin_router() -> APIRouter:
    """Build the admin ``APIRouter`` (status / keys / proxy)."""
    router = APIRouter()

    @router.get("/api/status")
    async def status(request: Request):
        return request.app.state.status_provider()

    @router.get("/api/models")
    async def models(request: Request):
        service = getattr(request.app.state, "service", None)
        return service.list_models() if service is not None else []

    @router.post("/api/keys")
    async def save_keys(request: Request):
        body = await request.json()
        return request.app.state.save_keys(body)

    @router.post("/api/proxy/start")
    async def proxy_start(request: Request):
        result = request.app.state.proxy_start()
        if not result or (isinstance(result, dict) and result.get("ok") is False):
            content = result if isinstance(result, dict) else {"ok": False}
            return JSONResponse(status_code=503, content=content)
        return result

    @router.post("/api/proxy/stop")
    async def proxy_stop(request: Request):
        return request.app.state.proxy_stop()

    return router
