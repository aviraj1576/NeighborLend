import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.config import get_settings
from app.database import engine, Base, migrate_schema, require_generic_schema_target_allowed
from app.routers import auth, listings, ai, uploads, borrow_requests, chat, notifications
from app.routers import payments, disputes

settings = get_settings()

if settings.app_env.lower() in {"production", "prod"}:
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
    if not (settings.supabase_url and settings.supabase_service_role_key):
        logging.getLogger(__name__).warning(
            "Supabase Storage is not configured; production uploads will use ephemeral local storage."
        )

# Pre-load YOLO model at startup to avoid first-request latency
def _preload_model():
    try:
        from ultralytics import YOLO
        from app.config import get_settings
        from app.services.ml_service import _model_loaded as _, _model as __  # trigger import
        import app.services.ml_service as ml_service
        model_path = get_settings().ai_model_path_abs
        model = YOLO(str(model_path))
        # Warm-up inference with a dummy image
        import numpy as np
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy, verbose=False)
        # Set the global model in ml_service
        ml_service._model = model
        ml_service._model_loaded = True
        logging.getLogger(__name__).info("YOLOv8 model pre-loaded and warmed up")
    except Exception as exc:
        logging.getLogger(__name__).warning(f"YOLOv8 pre-load skipped: {exc}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - preload model
    from app.services.razorpay_service import configured_provider
    configured_provider(settings)
    if settings.auto_migrate:
        require_generic_schema_target_allowed(engine)
        Base.metadata.create_all(bind=engine)
        migrate_schema()
    os.makedirs(settings.upload_dir_abs, exist_ok=True)
    if settings.app_env.lower() != "test":
        _preload_model()
    yield
    # Shutdown (if needed)

app = FastAPI(title="NeighborLend API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def restrict_local_deployment(request: Request, call_next):
    # A local flag is enforced at the transport boundary, not merely documented.
    # Never trust forwarded headers to turn a public request into a local one.
    if settings.deployment_exposure == "local" and settings.app_env.lower() not in {"prod", "production"}:
        hosts = {"127.0.0.1", "::1", "localhost"}
        if settings.app_env == "test":
            hosts.update({"testclient", "testserver"})
        if (not request.client or request.client.host not in hosts
                or request.url.hostname not in hosts
                or any(name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host"))):
            return JSONResponse({"detail": "Local deployment accepts direct loopback requests only"}, status_code=403)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir_abs, check_dir=False), name="uploads")

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(borrow_requests.router, prefix="/api/borrow-requests", tags=["Borrow Requests"])
app.include_router(chat.router, prefix="/api", tags=["Chat & Negotiation"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(uploads.router, prefix="/api", tags=["Uploads"])
app.include_router(payments.router, prefix="/api/payments", tags=["Test payments"])
app.include_router(disputes.router, prefix="/api/disputes", tags=["Disputes"])

@app.get("/api/health")
def health():
    # Include the configured database in readiness so Compose does not start
    # the frontend while PostgreSQL is unreachable.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
