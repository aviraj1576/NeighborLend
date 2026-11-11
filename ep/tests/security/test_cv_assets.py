import hashlib
import io
import json

import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.cv import assets


def test_approved_manifest_and_destinations(tmp_path, monkeypatch):
    plan = assets.read_plan()
    assert len(plan) == 26
    assert sum(item["expected_bytes"] for item in plan) == 129383449
    monkeypatch.setattr(assets, "MODEL_ROOT", tmp_path)
    assert assets.destination(plan[0]).is_relative_to(tmp_path)
    for path in ("../backend/file", ".runtime/models/../../escape", "C:/escape"):
        with pytest.raises(EPError):
            assets.destination({**plan[0], "relative_target": path})
    modified = tmp_path / "modified.json"
    modified.write_text("{}", encoding="utf-8")
    with pytest.raises(EPError):
        assets.read_plan(modified)


def test_size_and_git_integrity_reject_corruption():
    data = b"deterministic source"
    item = {"expected_bytes": len(data), "git_blob_sha1": assets.git_digest(data)}
    assert assets.validate_bytes(item, data) == hashlib.sha256(data).hexdigest()
    for invalid in (data[:-1], b"x" * len(data)):
        with pytest.raises(EPError):
            assets.validate_bytes(item, invalid)


def test_download_is_allowlisted_bounded_and_cleans_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "MODEL_ROOT", tmp_path)
    item = assets.read_plan()[0]

    def fake_open(request, timeout):
        assert request.full_url == item["url"]
        return io.BytesIO(b"x" * (item["expected_bytes"] + 1))

    with pytest.raises(EPError):
        assets.fetch_asset(item, {}, fake_open)
    assert not list(tmp_path.rglob("*.part"))
    assert not assets.destination(item).exists()
    with pytest.raises(EPError):
        assets.fetch_asset({**item, "url": "https://evil.example/model"}, {}, fake_open)


def test_receipt_prevents_adopting_or_loading_unverified_files(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "MODEL_ROOT", tmp_path)
    item = assets.read_plan()[-1]
    target = assets.destination(item)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"untrusted")
    # Reject wrong-size local assets before allocating their contents.
    monkeypatch.setattr(assets, "read_plan", lambda: [item])
    monkeypatch.setattr(
        type(target), "read_bytes", lambda self: pytest.fail("Unbounded asset read")
    )
    with pytest.raises(EPError):
        assets.fetch_asset(item, {})
    with pytest.raises(EPError):
        assets.verify_store()


def test_download_receipt_restart_and_unexpected_files(tmp_path, monkeypatch):
    data = b"offline test source, not executable model code"
    item = {
        "relative_target": ".runtime/models/source/sample.txt",
        "url": "https://example.invalid/approved-test-only",
        "expected_bytes": len(data),
        "git_blob_sha1": assets.git_digest(data),
    }
    monkeypatch.setattr(assets, "MODEL_ROOT", tmp_path)
    monkeypatch.setattr(assets, "read_plan", lambda: [item])
    monkeypatch.setattr(
        assets,
        "build_opener",
        lambda *args: type("Opener", (), {"open": lambda *a, **k: io.BytesIO(data)})(),
    )
    receipt = assets.fetch_all()
    assert receipt["files"][item["relative_target"]] == hashlib.sha256(data).hexdigest()
    assert assets.fetch_all() == receipt  # Verified restart does not require a transfer.
    (tmp_path / "unexpected.bin").write_bytes(b"extra")
    with pytest.raises(EPError):
        assets.verify_store()
    assert not (tmp_path / "download.lock").exists()
    with pytest.raises(EPError):
        assets.NoRedirect().redirect_request(None, None, 302, None, {}, "https://other.invalid")
    (tmp_path / "integrity.json").write_text(json.dumps({"manifest_sha256": "forged", "files": {}}))
    with pytest.raises(EPError):
        assets.verify_store()
