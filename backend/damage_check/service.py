import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Tuple

from . import images
from .config import Settings
from .exceptions import Conflict, Forbidden, InvalidInput, NotFound
from .providers.base import VisionProvider
from .schemas import (
    PHASES, VIEWS, CheckRecord, CheckView, DamageReport, Decision, ViewResult, utcnow,
)
from .storage import StorageBackend

log = logging.getLogger("damage_check")


def aggregate_overall(results: List[ViewResult]) -> str:
    """clear / possible_damage / needs_review. Errors never count as 'clear'."""
    for r in results:
        if r.comparable and r.damage_detected and r.confidence in ("medium", "high"):
            return "possible_damage"
    for r in results:
        if r.error or not r.comparable or r.damage_detected:
            return "needs_review"
    return "clear"


class DamageCheckService:
    def __init__(self, storage: StorageBackend, provider: VisionProvider,
                 settings: Optional[Settings] = None) -> None:
        self.storage = storage
        self.provider = provider
        self.settings = settings or Settings.from_env()

    # ---------- helpers ----------
    @staticmethod
    async def _io(fn, *args):
        return await asyncio.to_thread(fn, *args)

    async def _load(self, check_id: str) -> CheckRecord:
        rec = await self._io(self.storage.load_check, check_id)
        if rec is None:
            raise NotFound("Check not found.")
        return rec

    @staticmethod
    def _require_participant(rec: CheckRecord, user_id: str) -> None:
        if user_id not in (rec.lender_id, rec.borrower_id):
            raise Forbidden("You are not part of this check.")

    async def _view(self, rec: CheckRecord) -> CheckView:
        before = await self._io(self.storage.list_photos, rec.id, "before")
        after = await self._io(self.storage.list_photos, rec.id, "after")
        return CheckView(
            id=rec.id, request_id=rec.request_id, lender_id=rec.lender_id,
            borrower_id=rec.borrower_id, item_class=rec.item_class, status=rec.status,
            created_at=rec.created_at, updated_at=rec.updated_at,
            before_views=before, after_views=after,
            missing_before=[v for v in VIEWS if v not in before],
            missing_after=[v for v in VIEWS if v not in after],
            report=rec.report, decision=rec.decision, error=rec.error,
        )

    async def _save(self, rec: CheckRecord) -> None:
        rec.updated_at = utcnow()
        await self._io(self.storage.save_check, rec)

    # ---------- public API ----------
    async def create_check(self, user_id, request_id, lender_id, borrower_id,
                           item_class: Optional[str] = None) -> CheckView:
        user_id, lender_id, borrower_id = str(user_id), str(lender_id), str(borrower_id)
        if user_id not in (lender_id, borrower_id):
            raise Forbidden("Only the lender or borrower can start a check.")
        rec = CheckRecord(
            id=uuid.uuid4().hex,
            request_id=str(request_id) if request_id is not None else None,
            lender_id=lender_id, borrower_id=borrower_id,
            item_class=(item_class or "").strip() or None,
        )
        await self._save(rec)
        return await self._view(rec)

    async def get_check(self, user_id, check_id: str) -> CheckView:
        rec = await self._load(check_id)
        self._require_participant(rec, str(user_id))
        return await self._view(rec)

    async def put_photo(self, user_id, check_id: str, phase: str, view: str, data: bytes) -> int:
        user_id = str(user_id)
        if phase not in PHASES or view not in VIEWS:
            raise InvalidInput("Unknown phase or view.")
        rec = await self._load(check_id)
        self._require_participant(rec, user_id)
        expected = rec.lender_id if phase == "before" else rec.borrower_id
        if user_id != expected:
            raise Forbidden("Before photos come from the lender, after photos from the borrower.")
        if rec.status != "collecting":
            raise Conflict("This check is already being analysed.")
        mime = images.validate_upload(data, self.settings.max_upload_bytes)
        await self._io(self.storage.save_photo, rec.id, phase, view, data, mime)
        return len(data)

    async def get_photo(self, user_id, check_id: str, phase: str, view: str) -> Tuple[bytes, str]:
        if phase not in PHASES or view not in VIEWS:
            raise InvalidInput("Unknown phase or view.")
        rec = await self._load(check_id)
        self._require_participant(rec, str(user_id))
        found = await self._io(self.storage.load_photo, rec.id, phase, view)
        if found is None:
            raise NotFound("Photo not found.")
        return found

    async def start_analysis(self, user_id, check_id: str) -> Tuple[CheckView, bool]:
        """Validate and mark the check as processing. Returns (view, should_run)."""
        rec = await self._load(check_id)
        self._require_participant(rec, str(user_id))
        if rec.status in ("processing", "done"):
            return await self._view(rec), False
        before = await self._io(self.storage.list_photos, rec.id, "before")
        after = await self._io(self.storage.list_photos, rec.id, "after")
        if self.settings.require_all_views:
            miss_b = [v for v in VIEWS if v not in before]
            miss_a = [v for v in VIEWS if v not in after]
            if miss_b or miss_a:
                raise Conflict("Missing photos. before: %s; after: %s." % (miss_b or "none", miss_a or "none"))
        elif not set(before) & set(after):
            raise Conflict("Need at least one view with both a before and an after photo.")
        rec.status, rec.error = "processing", None
        await self._save(rec)
        return await self._view(rec), True

    async def run_analysis(self, check_id: str) -> None:
        """Runs in the background. Never raises; failures are recorded on the check."""
        try:
            rec = await self._load(check_id)
        except NotFound:
            return
        if rec.status != "processing":
            return
        try:
            before = set(await self._io(self.storage.list_photos, rec.id, "before"))
            after = set(await self._io(self.storage.list_photos, rec.id, "after"))
            views = [v for v in VIEWS if v in before and v in after]
            sem = asyncio.Semaphore(self.settings.max_concurrency)

            async def one(view: str) -> ViewResult:
                async with sem:
                    return await self._compare_view(rec, view)

            results = await asyncio.gather(*(one(v) for v in views))
            rec.report = DamageReport(
                overall=aggregate_overall(list(results)),  # type: ignore[arg-type]
                views=list(results), model=getattr(self.provider, "name", ""),
            )
            rec.status = "done"
        except Exception as exc:  # recorded, not raised: this runs in a background task
            log.exception("damage check %s failed", check_id)
            rec.status, rec.error = "failed", "Analysis failed (%s)." % type(exc).__name__
        await self._save(rec)

    async def _compare_view(self, rec: CheckRecord, view: str) -> ViewResult:
        try:
            b = await self._io(self.storage.load_photo, rec.id, "before", view)
            a = await self._io(self.storage.load_photo, rec.id, "after", view)
            if b is None or a is None:
                return ViewResult(view=view, comparable=False, error="Photo missing.")
            side = self.settings.max_image_side
            b_bytes, b_mime = await self._io(images.prepare_for_model, b[0], b[1], side)
            a_bytes, a_mime = await self._io(images.prepare_for_model, a[0], a[1], side)
            budget = self.settings.request_timeout * (self.settings.max_retries + 1) + 10
            return await asyncio.wait_for(
                self.provider.compare(
                    view=view, item_class=rec.item_class, before=b_bytes, before_mime=b_mime,
                    after=a_bytes, after_mime=a_mime,
                ),
                timeout=budget,
            )
        except Exception as exc:
            log.warning("view %s failed: %s: %s", view, type(exc).__name__, str(exc)[:200])
            return ViewResult(view=view, comparable=False,
                              error="%s: %s" % (type(exc).__name__, str(exc)[:200]))

    async def decide(self, user_id, check_id: str, decision: str, comment: Optional[str]) -> CheckView:
        user_id = str(user_id)
        rec = await self._load(check_id)
        self._require_participant(rec, user_id)
        if user_id != rec.lender_id:
            raise Forbidden("Only the lender can confirm or dismiss.")
        if rec.status != "done":
            raise Conflict("The analysis is not finished yet.")
        rec.decision = Decision(decision=decision, comment=comment, decided_by=user_id)  # type: ignore[arg-type]
        await self._save(rec)
        return await self._view(rec)
