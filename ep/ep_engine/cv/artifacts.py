import hashlib
import io
import os
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from PIL import Image

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError
from ep_engine.cv.contracts import Artifact


class ArtifactWriter:
    def __init__(self, root: Path, source_ids):
        if root.is_symlink() or not root.resolve().is_relative_to(EP_ROOT):
            raise EPError(409, "artifact_path", "Invalid private artifact directory")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.sources = set(map(UUID, map(str, source_ids)))
        self.records = []
        self.total = 0

    def save(self, kind, array, source_ids):
        sources = list(map(UUID, map(str, source_ids)))
        if not sources or not set(sources).issubset(self.sources):
            raise EPError(409, "artifact_citation", "Invalid artifact evidence citation")
        if (
            array.dtype != np.uint8
            or array.ndim not in (2, 3)
            or max(array.shape[:2]) > 2048
            or min(array.shape[:2]) < 1
        ):
            raise EPError(413, "artifact_limit", "Invalid artifact dimensions or type")
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format="PNG")
        data = buffer.getvalue()
        if len(self.records) >= 150 or self.total + len(data) > 32_000_000:
            raise EPError(413, "artifact_limit", "Artifact resource budget exceeded")
        record = Artifact(
            id=uuid4(),
            kind=kind,
            source_ids=sources,
            sha256=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
            width=array.shape[1],
            height=array.shape[0],
        )
        path = self.root / f"{record.id}.png"
        try:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        self.records.append(record)
        self.total += len(data)
        return record.id
