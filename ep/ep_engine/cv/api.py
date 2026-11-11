from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from ep_engine.core.security import Grant
from ep_engine.cv.contracts import CVPackage, RunRequest
from ep_engine.cv.store import RunRecord


def router(principal):
    routes = APIRouter()

    @routes.post(
        "/v1/inspections/{inspection_id}/cv-runs", response_model=RunRecord, status_code=202
    )
    def create(
        inspection_id: UUID,
        body: RunRequest,
        request: Request,
        grant: Annotated[Grant, Depends(principal)],
    ):
        return request.app.state.cv.create(inspection_id, body, grant)

    @routes.get("/v1/cv-runs/{run_id}", response_model=RunRecord)
    def get(run_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.cv.get(run_id, grant)[0]

    @routes.post("/v1/cv-runs/{run_id}/cancel", response_model=RunRecord)
    def cancel(run_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.cv.cancel(run_id, grant)

    @routes.get("/v1/cv-runs/{run_id}/result", response_model=CVPackage)
    def result(run_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.cv.result(run_id, grant)

    @routes.get("/v1/cv-runs/{run_id}/artifacts/{artifact_id}")
    def artifact(
        run_id: UUID,
        artifact_id: UUID,
        request: Request,
        grant: Annotated[Grant, Depends(principal)],
    ):
        return Response(
            request.app.state.cv.artifact(run_id, artifact_id, grant),
            media_type="image/png",
            headers={"Content-Disposition": "attachment"},
        )

    return routes
