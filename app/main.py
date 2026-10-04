from fastapi import FastAPI, Depends
from fastapi import Request
from fastapi.responses import RedirectResponse
from time import perf_counter
from uuid import uuid4
import logging

from app.api.auth import router as auth_router, current_account
from app.config import settings

from app.api.watches import router as watches_router
from app.api.changes import router as changes_router
from app.api.profile import router as profile_router
from app.api.memory import router as memory_router
from app.api.actions import router as actions_router
from app.api.notifications import router as notifications_router
from app.api.digests import router as digests_router
from app.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Sentinel",
    description="Autonomous Personal Intelligence Agent",
    version="0.1.0",
)

app.include_router(auth_router)

app.include_router(watches_router, dependencies=[Depends(current_account)])
app.include_router(changes_router, dependencies=[Depends(current_account)])
app.include_router(profile_router, dependencies=[Depends(current_account)])
app.include_router(memory_router, dependencies=[Depends(current_account)])
app.include_router(actions_router, dependencies=[Depends(current_account)])
app.include_router(notifications_router, dependencies=[Depends(current_account)])
app.include_router(digests_router, dependencies=[Depends(current_account)])




@app.get("/control-center", include_in_schema=False)
def control_center():
    return RedirectResponse(settings.frontend_url)


@app.middleware("http")
async def log_request(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Request failed", extra={
            "event": "http_request", "request_id": request_id,
            "url": request.url.path,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
            "status": 500,
        })
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info("Request completed", extra={
        "event": "http_request", "request_id": request_id,
        "url": request.url.path,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "status": response.status_code,
    })
    return response

@app.get("/")
def root():
    return {
        "name": "Sentinel",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
