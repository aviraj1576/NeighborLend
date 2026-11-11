from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ep_engine.assessment.contracts import AssessmentOptions, AssessmentReport
from ep_engine.assessment.store import AssessmentJob
from ep_engine.core.security import Grant


def router(principal):
    routes = APIRouter()

    @routes.post("/v1/cv-runs/{run_id}/assessments", response_model=AssessmentJob, status_code=202)
    def create(
        run_id: UUID,
        body: AssessmentOptions,
        request: Request,
        grant: Annotated[Grant, Depends(principal)],
    ):
        return request.app.state.assessments.create(run_id, body, grant)

    @routes.get("/v1/assessments/{assessment_id}", response_model=AssessmentJob)
    def get(assessment_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.assessments.get(assessment_id, grant)[0]

    @routes.post("/v1/assessments/{assessment_id}/cancel", response_model=AssessmentJob)
    def cancel(assessment_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.assessments.cancel(assessment_id, grant)

    @routes.get("/v1/assessments/{assessment_id}/result", response_model=AssessmentReport)
    def result(assessment_id: UUID, request: Request, grant: Annotated[Grant, Depends(principal)]):
        return request.app.state.assessments.result(assessment_id, grant)

    return routes
