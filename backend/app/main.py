import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.config import get_settings
from app.database import engine, Base, migrate_schema
from app.routers import auth, listings, ai, uploads, borrow_requests, chat, notifications, lend_damage

settings = get_settings()

if settings.app_env.lower() in {"production", "prod"}:
    if (
        len(settings.jwt_secret) < 32
        or settings.jwt_secret == "neighborlend-super-secret-key-2026-prototype"
    ):
        raise RuntimeError("Production requires a new JWT_SECRET with at least 32 characters.")
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

# Create tables at import time for test compatibility (also runs in lifespan for production)
Base.metadata.create_all(bind=engine)
migrate_schema()
os.makedirs(settings.upload_dir_abs, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - preload model
    _preload_model()
    yield
    # Shutdown (if needed)

app = FastAPI(title="NeighborLend API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir_abs), name="uploads")

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(listings.router, prefix="/api/listings", tags=["Listings"])
app.include_router(borrow_requests.router, prefix="/api/borrow-requests", tags=["Borrow Requests"])
app.include_router(chat.router, prefix="/api", tags=["Chat & Negotiation"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(uploads.router, prefix="/api", tags=["Uploads"])
app.include_router(lend_damage.router, prefix="/api", tags=["Lend Damage"])

from damage_check import create_router as create_damage_router
from app.services.damage_integration import get_damage_service, damage_user_id
app.include_router(
    create_damage_router(get_damage_service(), damage_user_id),
    prefix="/api/damage-checks",
    tags=["Damage Check"],
)

@app.get("/api/health")
def health():
    # Include the configured database in readiness so Compose does not start
    # the frontend while PostgreSQL is unreachable.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
