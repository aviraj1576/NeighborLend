"""Explicit optional download from the upstream LoFTR author; never called by inference."""

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = "https://cmp.felk.cvut.cz/~mishkdmy/models/loftr_outdoor.ckpt"


def main():
    root = ROOT / ".runtime" / "v3-models"
    if root.is_symlink() or not root.resolve().is_relative_to(ROOT):
        raise ValueError("Unsafe optional model directory")
    root.mkdir(parents=True, exist_ok=True)
    target = root / "loftr_outdoor.ckpt"
    receipt = root / "loftr_outdoor.receipt.json"
    if target.exists() or receipt.exists():
        raise FileExistsError("Optional assets already exist; refusing to overwrite")
    temporary = root / "loftr_outdoor.part"
    digest, size = hashlib.sha256(), 0
    try:
        with urlopen(URL, timeout=30) as response, temporary.open("xb") as output:  # noqa: S310
            if response.geturl() != URL:
                raise ValueError("Unexpected checkpoint redirect")
            while chunk := response.read(65536):
                size += len(chunk)
                if size > 128_000_000:
                    raise ValueError("Checkpoint download exceeds memory budget")
                digest.update(chunk)
                output.write(chunk)
        os.replace(temporary, target)
        record = {
            "url": URL,
            "bytes": size,
            "sha256": digest.hexdigest(),
            "provenance": "upstream HTTPS; digest recorded on first download, not a signature",
        }
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record), flush=True)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
