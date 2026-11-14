import json
import re
from typing import List, Optional, Protocol

from ..schemas import FINDING_TYPES, LOCATIONS, Finding, ViewResult


class VisionProvider(Protocol):
    """Anything that can compare one before/after pair for one view."""

    name: str

    async def compare(
        self,
        *,
        view: str,
        item_class: Optional[str],
        before: bytes,
        before_mime: str,
        after: bytes,
        after_mime: str,
    ) -> ViewResult: ...


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_view_result(view: str, raw_text: str) -> ViewResult:
    """Turn model output into a ViewResult. Never raises: unreadable output
    becomes an error result, which the report treats as 'needs review'."""
    data = _extract_json(raw_text)
    if data is None:
        return ViewResult(view=view, comparable=False, error="Model returned unreadable output.")

    confidence = str(data.get("confidence", "low")).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    findings: List[Finding] = []
    raw_findings = data.get("findings")
    if isinstance(raw_findings, list):
        for item in raw_findings[:10]:
            if not isinstance(item, dict):
                continue
            ftype = str(item.get("type", "other")).lower()
            loc = str(item.get("location", "unknown")).lower()
            findings.append(
                Finding(
                    type=ftype if ftype in FINDING_TYPES else "other",
                    description=str(item.get("description", ""))[:300],
                    location=loc if loc in LOCATIONS else "unknown",
                )
            )

    damage = bool(data.get("damage_detected", False))
    return ViewResult(
        view=view,
        comparable=bool(data.get("comparable", True)),
        damage_detected=damage,
        confidence=confidence,  # type: ignore[arg-type]
        findings=findings,
        note=str(data.get("note", ""))[:300],
    )
