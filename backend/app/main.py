import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.core.db import ping_db
from app.core.errors import DomainError, domain_error_handler
from app.modules.closing.router import router as closing_router
from app.modules.demo.router import router as demo_router
from app.modules.enrollment.router import router as user_router
from app.modules.review.router import router as review_router
from app.modules.review.router import user_router as review_user_router
from app.worker import celery_app  # noqa: F401  (the API enqueues tasks with this config)

app = FastAPI(
    title="Cierre · Servicio contable Wallbit",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
)

app.add_exception_handler(DomainError, domain_error_handler)
app.include_router(user_router)
app.include_router(demo_router)
app.include_router(review_router)
app.include_router(review_user_router)
app.include_router(closing_router)

REQUESTS = Counter("http_requests_total", "Requests HTTP", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Latencia de requests HTTP", ["method", "route"]
)


@app.middleware("http")
async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    ping_db()
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
