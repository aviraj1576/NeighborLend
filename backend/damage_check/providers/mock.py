"""Offline provider for development and tests. No network, no key needed."""
from typing import Callable, Dict, Optional

from ..schemas import ViewResult


class MockProvider:
    name = "mock"

    def __init__(self, script: Optional[Dict[str, ViewResult]] = None,
                 hook: Optional[Callable[[str], None]] = None) -> None:
        self.script = script or {}
        self.hook = hook

    async def compare(self, *, view, item_class, before, before_mime, after, after_mime) -> ViewResult:
        if self.hook:
            self.hook(view)
        if view in self.script:
            return self.script[view]
        if before == after:
            return ViewResult(view=view, comparable=True, damage_detected=False,
                              confidence="high", note="Photos are identical (mock).")
        return ViewResult(view=view, comparable=True, damage_detected=True, confidence="low",
                          note="Photos differ (mock); a real model would describe what changed.")
