import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ep_engine.config import EP_ROOT, Settings
from ep_engine.core.exceptions import EPError
from ep_engine.core.security import LocalAuthorization
from ep_engine.schemas.models import Box, Finding, InspectionCreate


def test_configuration_keeps_data_inside_ep(monkeypatch):
    with pytest.raises(ValidationError):
        Settings(data_dir=EP_ROOT.parent / "backend")
    with pytest.raises(ValidationError):
        Settings(data_dir=EP_ROOT)
    with pytest.raises(ValidationError):
        Settings(cors_origins=("*",))
    monkeypatch.setenv("EP_DATA_DIR", ".test-artifacts/environment")
    monkeypatch.setenv("EP_MAX_PIXELS", "400")
    monkeypatch.setenv("EP_CORS_ORIGINS", '["http://127.0.0.1:5173"]')
    configured = Settings.from_environment()
    assert configured.data_dir == EP_ROOT / ".test-artifacts/environment"
    assert configured.max_pixels == 400
    assert configured.cors_origins == ("http://127.0.0.1:5173",)


def test_local_grants_file_is_explicit_validated_and_not_logged(tmp_path):
    path = tmp_path / "grants.json"
    entry = {
        "token": "deterministic-test-token-123456789",
        "grant": {"subject": "lender", "rentals": {"rental-1": "lender"}},
    }
    path.write_text(json.dumps([entry]), encoding="utf-8")
    adapter = LocalAuthorization.from_file(path)
    assert adapter.authenticate(f"Bearer {entry['token']}").authorize("rental-1") == "lender"
    with pytest.raises(EPError):
        adapter.authenticate("Bearer wrong")
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")
    with pytest.raises(ValueError):
        LocalAuthorization.from_file(path)
    entry["token"] = "short"
    path.write_text(json.dumps([entry]), encoding="utf-8")
    with pytest.raises(ValidationError):
        LocalAuthorization.from_file(path)


def test_duplicate_selection_and_finding_grounding():
    key = uuid4()
    with pytest.raises(ValidationError):
        InspectionCreate(rental_id="rental-1", reference_ids=[key], return_ids=[key])
    with pytest.raises(ValidationError):
        Box(x1=0.7, x2=0.3, y1=0.2, y2=0.4)
    box = Box(x1=0.1, x2=0.3, y1=0.2, y2=0.4)
    finding = {
        "suspected_damage": "uncertain",
        "severity": "uncertain",
        "affected_region": "front",
        "reference_ids": [key],
        "return_ids": [uuid4()],
        "supporting_observations": ["Synthetic contract test only"],
        "localization": {key: box},
    }
    assert Finding(**finding).human_review_required
    finding["localization"] = {uuid4(): box}
    with pytest.raises(ValidationError):
        Finding(**finding)
