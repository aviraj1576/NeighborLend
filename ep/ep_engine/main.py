import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from ep_engine.config import Settings
from ep_engine.core.exceptions import EPError
from ep_engine.core.security import Authorization, Grant, LocalAuthorization
from ep_engine.schemas.models import (
    ErrorResponse,
    Evidence,
    Health,
    Inspection,
    InspectionCreate,
    Ready,
    RentalID,
    Stage,
)
from ep_engine.services.evidence import EvidenceService
from ep_engine.services.inspections import InspectionService
from ep_engine.storage.local import LocalStorage
from ep_engine.storage.repository import Repository


def error_response(status, code, message, request_id):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


class RequestBoundary:
    """Bound raw request bodies including chunked transfer before JSON parsing."""

    def __init__(self, app, limit):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def wrapped_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] += [
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        try:
            chunks = []
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                total += len(body)
                if total > self.limit:
                    raise EPError(413, "body_limit", "Request exceeds byte limit")
                chunks.append(body)
                if not message.get("more_body", False):
                    break
            content = b"".join(chunks)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": content, "more_body": False}
                return await receive()

            await self.app(scope, replay, wrapped_send)
        except Exception as exc:
            if started:
                raise
            if isinstance(exc, EPError):
                response = error_response(exc.status, exc.code, exc.message, request_id)
            else:
                response = error_response(
                    500, "internal_error", "Internal service error", request_id
                )
            await response(scope, receive, wrapped_send)


def principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ],
) -> Grant:
    return request.app.state.authorization.authenticate(request.headers.get("authorization"))


def evidence_service(request: Request) -> EvidenceService:
    return request.app.state.evidence


def inspection_service(request: Request) -> InspectionService:
    return request.app.state.inspections


def create_app(settings: Settings | None = None, authorization: Authorization | None = None):
    settings = settings or Settings.from_environment()
    if authorization is None:
        grant_file = os.environ.get("EP_LOCAL_GRANTS_FILE")
        authorization = (
            LocalAuthorization.from_file(Path(grant_file)) if grant_file else LocalAuthorization()
        )

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        app.state.repository = Repository(settings.data_dir / "ep.sqlite3")
        app.state.repository.initialize()
        app.state.storage = LocalStorage(settings.data_dir / "evidence")
        app.state.repository.recover(app.state.storage)
        app.state.evidence = EvidenceService(settings, app.state.repository, app.state.storage)
        app.state.inspections = InspectionService(app.state.repository, app.state.storage)
        from ep_engine.cv.service import CVService

        app.state.cv = CVService(settings.data_dir, app.state.repository, app.state.storage)
        from ep_engine.assessment.service import AssessmentService

        app.state.assessments = AssessmentService(settings.data_dir, app.state.cv)
        yield

    app = FastAPI(
        title="NeighborLend EP",
        version="1.0",
        lifespan=lifespan,
        responses={
            code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 415, 422, 500, 503)
        },
    )
    app.state.authorization = authorization
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(RequestBoundary, limit=settings.max_upload_bytes)

    @app.exception_handler(EPError)
    async def domain_error(request, exc):
        return error_response(exc.status, exc.code, exc.message, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(
            422, "invalid_request", "Request validation failed", request.state.request_id
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(
            exc.status_code, "http_error", "HTTP request failed", request.state.request_id
        )

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def dependency_error(request, exc):
        return error_response(
            503,
            "dependency_unavailable",
            "Storage or database unavailable",
            request.state.request_id,
        )

    @app.get("/health", response_model=Health)
    def health():
        return Health()

    @app.get("/ready", response_model=Ready)
    def ready(request: Request):
        if not authorization.configured:
            raise EPError(503, "auth_unconfigured", "Authorization adapter is not configured")
        request.app.state.repository.check()
        request.app.state.storage.check()
        return Ready()

    @app.post(
        "/v1/evidence",
        response_model=Evidence,
        status_code=201,
        responses={200: {"model": Evidence, "description": "Existing scoped duplicate"}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    mime: {"schema": {"type": "string", "format": "binary"}}
                    for mime in ("image/jpeg", "image/png")
                },
            }
        },
    )
    async def upload_evidence(
        request: Request,
        response: Response,
        rental_id: RentalID,
        stage: Stage,
        grant: Annotated[Grant, Depends(principal)],
        service: Annotated[EvidenceService, Depends(evidence_service)],
        viewpoint: Annotated[str | None, Query(max_length=80)] = None,
        capture_timestamp: datetime | None = None,
    ):
        grant.authorize(rental_id, stage)
        # Offload Pillow/SQLite/filesystem work; no inference runs in HTTP handlers.
        from starlette.concurrency import run_in_threadpool

        result, created = await run_in_threadpool(
            service.ingest,
            await request.body(),
            request.headers.get("content-type"),
            rental_id,
            stage,
            grant,
            viewpoint,
            capture_timestamp,
        )
        response.status_code = 201 if created else 200
        return result

    @app.get("/v1/evidence/{evidence_id}", response_model=Evidence)
    def get_evidence(
        evidence_id: UUID,
        grant: Annotated[Grant, Depends(principal)],
        service: Annotated[EvidenceService, Depends(evidence_service)],
    ):
        return service.read(evidence_id, grant)

    @app.get("/v1/evidence/{evidence_id}/content", response_class=Response)
    def get_content(
        evidence_id: UUID,
        grant: Annotated[Grant, Depends(principal)],
        service: Annotated[EvidenceService, Depends(evidence_service)],
    ):
        data, mime = service.content(evidence_id, grant)
        return Response(data, media_type=mime, headers={"Content-Disposition": "attachment"})

    @app.post("/v1/inspections", response_model=Inspection, status_code=201)
    def create_inspection(
        body: InspectionCreate,
        grant: Annotated[Grant, Depends(principal)],
        service: Annotated[InspectionService, Depends(inspection_service)],
    ):
        return service.create(body, grant)

    @app.get("/v1/inspections/{inspection_id}", response_model=Inspection)
    def get_inspection(
        inspection_id: UUID,
        grant: Annotated[Grant, Depends(principal)],
        service: Annotated[InspectionService, Depends(inspection_service)],
    ):
        return service.read(inspection_id, grant)

    from ep_engine.cv.api import router

    app.include_router(router(principal))
    from ep_engine.assessment.api import router as assessment_router

    app.include_router(assessment_router(principal))
    return app
