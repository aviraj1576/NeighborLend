"""Explicit milestone-only path exclusion; no photograph or directory is opened here."""

import os

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError


def enforce_data_policy(path):
    if os.environ.get("EP_SYNTHETIC_ONLY") != "1":
        return
    candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
    for relative in ("test_images", ".test-artifacts/real-image-evaluation"):
        excluded = os.path.normcase(os.path.join(EP_ROOT, relative))
        if candidate == excluded or candidate.startswith(excluded + os.sep):
            raise EPError(403, "excluded_image_data", "Exploratory image data is excluded")
