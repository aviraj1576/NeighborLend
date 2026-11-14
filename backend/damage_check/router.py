# NOTE: no `from __future__ import annotations` here; FastAPI needs real annotations.
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile

from .exceptions import Conflict, DamageCheckError, Forbidden, InvalidInput, NotFound
from .schemas import CheckView, CreateCheckRequest, DecisionRequest, PhotoAck
from .service import DamageCheckService


def _http(exc: DamageCheckError) -> HTTPException:
    code = 400
    if isinstance(exc, NotFound):
        code = 404
    elif isinstance(exc, Forbidden):
        code = 403
    elif isinstance(exc, Conflict):
        code = 409
    elif isinstance(exc, InvalidInput):
        code = 400
    return HTTPException(status_code=code, detail=str(exc))


def create_router(service: DamageCheckService, get_user_id: Callable) -> APIRouter:
    """Build the router.

    `get_user_id` is a FastAPI dependency (a callable, sync or async) that returns
    the current user's id. In the main app it is a 3-line wrapper around the
    existing current-user dependency. The module never touches auth itself.
    """
    router = APIRouter(tags=["damage-check"])

    @router.post("", response_model=CheckView, status_code=201)
    async def create_check(body: CreateCheckRequest, user_id=Depends(get_user_id)):
        try:
            return await service.create_check(
                user_id, body.request_id, body.lender_id, body.borrower_id, body.item_class)
        except DamageCheckError as exc:
            raise _http(exc)

    @router.get("/{check_id}", response_model=CheckView)
    async def get_check(check_id: str, user_id=Depends(get_user_id)):
        try:
            return await service.get_check(user_id, check_id)
        except DamageCheckError as exc:
            raise _http(exc)

    @router.put("/{check_id}/photos/{phase}/{view}", response_model=PhotoAck)
    async def put_photo(check_id: str, phase: str, view: str,
                        file: UploadFile = File(...), user_id=Depends(get_user_id)):
        try:
            limit = service.settings.max_upload_bytes
            data = await file.read(limit + 1)
            size = await service.put_photo(user_id, check_id, phase, view, data)
            return PhotoAck(check_id=check_id, phase=phase, view=view, size_bytes=size)  # type: ignore[arg-type]
        except DamageCheckError as exc:
            raise _http(exc)

    @router.get("/{check_id}/photos/{phase}/{view}")
    async def get_photo(check_id: str, phase: str, view: str, user_id=Depends(get_user_id)):
        try:
            data, mime = await service.get_photo(user_id, check_id, phase, view)
        except DamageCheckError as exc:
            raise _http(exc)
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    @router.post("/{check_id}/analyze", response_model=CheckView, status_code=202)
    async def analyze(check_id: str, background: BackgroundTasks, user_id=Depends(get_user_id)):
        try:
            view, should_run = await service.start_analysis(user_id, check_id)
        except DamageCheckError as exc:
            raise _http(exc)
        if should_run:
            background.add_task(service.run_analysis, check_id)
        return view

    @router.post("/{check_id}/decision", response_model=CheckView)
    async def decide(check_id: str, body: DecisionRequest, user_id=Depends(get_user_id)):
        try:
            return await service.decide(user_id, check_id, body.decision, body.comment)
        except DamageCheckError as exc:
            raise _http(exc)

    return router
