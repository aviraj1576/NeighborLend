"""The integrated frontend's literal API calls must resolve to real backend routes."""
import re
from pathlib import Path

import pytest

from app.main import app

FRONTEND = Path(__file__).resolve().parents[2] / "frontend/src"
SOURCES = [*FRONTEND.joinpath("pages").glob("*.jsx"), FRONTEND / "context/AuthContext.jsx",
           FRONTEND / "components/Navbar.jsx"]
CALLS = set()
for source in SOURCES:
    content = source.read_text(encoding="utf-8")
    for method, _, path in re.findall(r"api\.(get|post|patch|delete)\(\s*([`'\"])(.*?)\2", content, re.S):
        variants = [path]
        if "${action}" in path:
            actions = re.findall(r"runHandoverAction\(\s*['\"]([^'\"]+)['\"]", content)
            assert actions, "Dynamic handover action has no visible caller"
            variants = [path.replace("${action}", action) for action in actions]
        for variant in variants:
            variant = re.sub(r"\$\{[^}]+\}", "synthetic-id", variant.split("?", 1)[0])
            if variant.startswith("/"):
                CALLS.add((method.upper(), "/api" + variant))


def test_frontend_contract_inventory_is_not_empty():
    assert len(CALLS) >= 25


@pytest.mark.parametrize("method,path", sorted(CALLS))
def test_each_frontend_api_call_has_a_backend_handler(method, path):
    assert any(method in getattr(route, "methods", set())
               and getattr(route, "path_regex", re.compile("(?!)")).fullmatch(path)
               for route in app.routes), f"No backend handler for {method} {path}"
