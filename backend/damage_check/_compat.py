"""Small helpers so the package works with both Pydantic v1 and v2."""
import json
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T")


def dump_json(model: Any) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()


def parse_json(cls: Type[T], text: str) -> T:
    if hasattr(cls, "model_validate_json"):
        return cls.model_validate_json(text)  # type: ignore[attr-defined]
    return cls.parse_raw(text)  # type: ignore[attr-defined]


def to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())
