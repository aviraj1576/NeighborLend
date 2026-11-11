"""Measured small DINO batches and bounded exact-content segmentation reuse."""

import hashlib
from collections import OrderedDict

import numpy as np

from ep_engine.core.exceptions import EPError
from ep_engine.cv.models import check_embedding
from ep_engine.v3.pipeline import CachedModels


class InspectionModels(CachedModels):
    def __init__(self, config):
        super().__init__(config)
        self.mask_cache = OrderedDict()
        self.mask_cache_hits = 0

    def segment(self, rgb, box):
        digest = hashlib.sha256(rgb.tobytes()).hexdigest()
        key = (digest, rgb.shape, rgb.dtype.str, tuple(box))
        if key in self.mask_cache:
            self.mask_cache_hits += 1
            self.mask_cache.move_to_end(key)
            return self.mask_cache[key].copy()
        mask = super().segment(rgb, box)
        self.mask_cache[key] = mask.copy()
        while len(self.mask_cache) > 12:
            self.mask_cache.popitem(last=False)
        return mask

    def _embedding_views(self, array, model):
        if self.device != "cuda":
            return super()._embedding_views(array, model)
        batch = np.stack([np.rot90(array, r).copy().transpose(2, 0, 1) for r in range(4)])
        tensor = self.torch.from_numpy(batch).to(self.device)
        result = self._forward(model, tensor)
        if tuple(result.shape) != (4, 384):
            raise EPError(503, "invalid_embedding", "Invalid batched DINO output")
        return check_embedding(
            np.mean([check_embedding(row) for row in result.cpu().numpy()], axis=0)
        )

    def metrics(self):
        return {
            **super().metrics(),
            "segmentation_cache_hits": self.mask_cache_hits,
            "embedding_rotation_batch": 4 if self.device == "cuda" else 1,
        }
