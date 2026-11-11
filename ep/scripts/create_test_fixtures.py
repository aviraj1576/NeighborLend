"""Generate deterministic decoder samples. These are not AI ground-truth evidence."""

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "tests" / "fixtures"
    target.mkdir(exist_ok=True)
    manifest = {
        "purpose": "Synthetic decoder fixtures only; no damage or identity labels",
        "files": {},
    }
    for extension, fmt in (("png", "PNG"), ("jpg", "JPEG")):
        path = target / f"sample.{extension}"
        Image.new("RGB", (24, 16), "navy").save(path, format=fmt)
        manifest["files"][path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": 24,
            "height": 16,
            "content_type": "image/png" if fmt == "PNG" else "image/jpeg",
        }
    (target / "metadata.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
