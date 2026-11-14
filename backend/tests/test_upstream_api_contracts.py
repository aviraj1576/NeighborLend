"""The integrated frontend's literal API calls must resolve to real backend routes."""
import re
from pathlib import Path

import pytest

from app.main import app

FRONTEND = Path(__file__).resolve().parents[2] / "frontend/src"
SOURCES = sorted(path for path in FRONTEND.rglob("*")
                 if path.suffix in {".js", ".jsx"} and not path.name.endswith(".test.js"))


def expand_path(path, content):
    """Resolve literal ternary branches before stripping a URL query; never eval JS."""
    variants = [path]
    for expression in re.findall(r"\$\{([^}]+)\}", path):
        value = expression
        if re.fullmatch(r"\w+", expression):
            assignment = re.search(r"\bconst\s+" + re.escape(expression) + r"\s*=\s*([^;]+);", content)
            if assignment:
                value = assignment.group(1)
        branches = re.fullmatch(r"[^?]+\?\s*(['\"])(.*?)\1\s*:\s*(['\"])(.*?)\3\s*", value, re.S)
        replacements = [branches.group(2), branches.group(4)] if branches else ["synthetic-id"]
        variants = [variant.replace("${" + expression + "}", replacement)
                    for variant in variants for replacement in replacements]
    return [variant.split("?", 1)[0] for variant in variants]


CALLS = set()
for source in SOURCES:
    content = source.read_text(encoding="utf-8")
    calls = re.findall(r"api\.(get|post|put|patch|delete)\(\s*([`'\"])(.*?)\2", content, re.S)
    # These helpers dispatch POSTs through api.post(path, payload).
    calls += [("post", quote, path) for quote, path in re.findall(
        r"\b(?:action|legacyAction|onAction|authenticate)\(\s*([`'\"])(.*?)\1", content, re.S)]
    for method, _, path in calls:
        for variant in expand_path(path, content):
            if variant.startswith("/"):
                CALLS.add((method.upper(), "/api" + variant))


def test_frontend_contract_inventory_is_not_empty():
    assert len(CALLS) >= 25


@pytest.mark.parametrize("method,path", sorted(CALLS))
def test_each_frontend_api_call_has_a_backend_handler(method, path):
    assert any(method in getattr(route, "methods", set())
               and getattr(route, "path_regex", re.compile("(?!)")).fullmatch(path)
               for route in app.routes), f"No backend handler for {method} {path}"


def test_rating_ternary_is_not_mistaken_for_url_query():
    assert expand_path("/borrow-requests/${id}/rate-${forLender ? 'lender' : 'borrower'}?refresh=1", "") == [
        "/borrow-requests/synthetic-id/rate-lender", "/borrow-requests/synthetic-id/rate-borrower"]


def test_document_kind_expands_both_real_routes():
    assert expand_path("/payments/bookings/${encodeURIComponent(id)}/${kind}",
                       "const kind = refund ? 'refund-acknowledgment' : 'receipt';") == [
        "/payments/bookings/synthetic-id/refund-acknowledgment",
        "/payments/bookings/synthetic-id/receipt"]


def test_inventory_includes_component_and_helper_contracts():
    assert ("POST", "/api/payments/refunds/execute") in CALLS
    assert ("POST", "/api/disputes/settle") in CALLS
    assert ("POST", "/api/payments/bookings/synthetic-id/evidence") in CALLS
