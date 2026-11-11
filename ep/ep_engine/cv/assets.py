import hashlib
import json
import os
import ssl
from pathlib import Path, PurePosixPath
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import uuid4

from ep_engine.config import EP_ROOT
from ep_engine.core.exceptions import EPError

PLAN_PATH = EP_ROOT / "docs" / "phase-2-installation-plan.json"
PLAN_SHA256 = "97409ffe16f12908087a724bd1d4adca775247f222340f7b4aa0c64046d6533d"
MODEL_ROOT = EP_ROOT / ".runtime" / "models"


def read_plan(path: Path = PLAN_PATH) -> list[dict]:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PLAN_SHA256:
        raise EPError(409, "model_allowlist", "Approved model manifest changed")
    plan = json.loads(data)
    return plan["sources"] + plan["weights"]


def destination(item: dict) -> Path:
    name = item["relative_target"]
    prefix = ".runtime/models/"
    if not name.startswith(prefix) or "\\" in name:
        raise EPError(409, "model_destination", "Invalid model destination")
    relative = PurePosixPath(name[len(prefix) :])
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
        raise EPError(409, "model_destination", "Invalid model destination")
    target = MODEL_ROOT.joinpath(*relative.parts)
    if target.is_symlink() or not target.resolve().is_relative_to(MODEL_ROOT.resolve()):
        raise EPError(409, "model_destination", "Unsafe model destination")
    return target


def git_digest(data: bytes) -> str:
    # Git's object identity algorithm, not a password/signature algorithm.
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def validate_bytes(item: dict, data: bytes) -> str:
    if len(data) != item["expected_bytes"]:
        raise EPError(409, "model_integrity", "Unexpected model asset size")
    if item.get("git_blob_sha1") and git_digest(data) != item["git_blob_sha1"]:
        raise EPError(409, "model_integrity", "Model Git object identity mismatch")
    return hashlib.sha256(data).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EPError(409, "model_allowlist", "Model redirects are not authorized")


def fetch_asset(item: dict, receipt: dict, opener=None) -> str:
    if item not in read_plan():
        raise EPError(409, "model_allowlist", "Unapproved model asset")
    target = destination(item)
    if target.exists():
        if target.stat().st_size != item["expected_bytes"]:
            raise EPError(409, "model_integrity", "Unexpected model asset size")
        digest = validate_bytes(item, target.read_bytes())
        if receipt.get(item["relative_target"]) != digest:
            raise EPError(
                409, "model_integrity", "Existing asset has no matching integrity receipt"
            )
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f"{uuid4()}.part"
    if opener is None:
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect()).open
    try:
        # Equality against the immutable approval manifest guarantees the fixed HTTPS URL.
        request = Request(item["url"], headers={"User-Agent": "NeighborLend-EP"})  # noqa: S310
        size = 0
        with opener(request, timeout=60) as source, temporary.open("xb") as output:
            while chunk := source.read(65536):
                size += len(chunk)
                if size > item["expected_bytes"]:
                    raise EPError(409, "model_integrity", "Model transfer exceeded approved size")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        digest = validate_bytes(item, temporary.read_bytes())
        os.replace(temporary, target)
        return digest
    finally:
        temporary.unlink(missing_ok=True)


def fetch_all():
    if MODEL_ROOT.is_symlink() or not MODEL_ROOT.resolve().is_relative_to(EP_ROOT):
        raise EPError(409, "model_destination", "Unsafe model root")
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    lock = MODEL_ROOT / "download.lock"
    # Exclusive local downloader; interrupted locks require explicit operator review.
    handle = lock.open("x")
    try:
        with handle:
            receipt_path = MODEL_ROOT / "integrity.json"
            receipt = (
                json.loads(receipt_path.read_text("utf-8"))
                if receipt_path.exists()
                else {
                    "manifest_sha256": PLAN_SHA256,
                    "files": {},
                }
            )
            if receipt.get("manifest_sha256") != PLAN_SHA256:
                raise EPError(409, "model_integrity", "Model receipt manifest mismatch")
            for item in read_plan():
                digest = fetch_asset(item, receipt["files"])
                receipt["files"][item["relative_target"]] = digest
                staging = MODEL_ROOT / "receipt.part"
                staging.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                os.replace(staging, receipt_path)
                print(
                    f"Verified {item['relative_target']} ({item['expected_bytes']} bytes)",
                    flush=True,
                )
    finally:
        lock.unlink(missing_ok=True)
    return verify_store()


def verify_store() -> dict:
    if MODEL_ROOT.is_symlink() or not MODEL_ROOT.resolve().is_relative_to(EP_ROOT):
        raise EPError(409, "model_destination", "Unsafe model root")
    path = MODEL_ROOT / "integrity.json"
    if not path.is_file():
        raise EPError(503, "models_unavailable", "Validated model assets are unavailable")
    receipt = json.loads(path.read_text("utf-8"))
    if receipt.get("manifest_sha256") != PLAN_SHA256:
        raise EPError(409, "model_integrity", "Model receipt manifest mismatch")
    expected = {"integrity.json"}
    for item in read_plan():
        target = destination(item)
        expected.add(target.relative_to(MODEL_ROOT).as_posix())
        if (
            not target.is_file()
            or target.stat().st_size != item["expected_bytes"]
            or validate_bytes(item, target.read_bytes())
            != receipt["files"].get(item["relative_target"])
        ):
            raise EPError(409, "model_integrity", "Model asset hash mismatch")
    for target in MODEL_ROOT.rglob("*"):
        if target.is_file() and target.relative_to(MODEL_ROOT).as_posix() not in expected:
            raise EPError(409, "model_integrity", "Unexpected file in approved model store")
    return receipt
