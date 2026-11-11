import json
from pathlib import Path

from fastapi.testclient import TestClient

from ep_engine.config import EP_ROOT
from ep_engine.main import create_app


def test_explicit_environment_configuration_starts_only_local_state(tmp_path, monkeypatch):
    path = tmp_path / "grants.json"
    path.write_text(
        json.dumps(
            [
                {
                    "token": "deterministic-test-token-123456789",
                    "grant": {"subject": "lender", "rentals": {"rental-1": "lender"}},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EP_DATA_DIR", str(tmp_path / "environment-runtime"))
    monkeypatch.setenv("EP_LOCAL_GRANTS_FILE", str(path))
    with TestClient(create_app()) as client:
        assert client.get("/ready").status_code == 200
        repository = client.app.state.repository
        assert repository.path.resolve().is_relative_to(EP_ROOT / ".test-artifacts")
        assert repository.path.name == "ep.sqlite3"
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/v1/evidence"]["post"]["security"] == [{"HTTPBearer": []}]


def test_committed_sample_images_match_manifest(settings):
    from ep_engine.services.images import decode_image

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    metadata = json.loads((fixtures / "metadata.json").read_text("utf-8"))
    for filename, expected in metadata["files"].items():
        result = decode_image(
            (fixtures / filename).read_bytes(), expected["content_type"], settings
        )
        assert result.sha256 == expected["sha256"]
        assert result.width == expected["width"]
        assert result.height == expected["height"]
