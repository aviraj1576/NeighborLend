"""Numerical guards shared by retrieval and strict evidence serialization."""

import math

from ep_engine.core.exceptions import EPError


def bounded_cosine(value):
    value = float(value)
    if not math.isfinite(value):
        raise EPError(503, "invalid_embedding", "Nonfinite cosine similarity")
    return min(1.0, max(-1.0, value))


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite structured evidence")
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            finite_tree(item)
