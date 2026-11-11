"""Request HTTPS headers only; never retrieve model bodies or disable TLS validation."""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "efficient_sam_vitt": (
        "https://raw.githubusercontent.com/yformer/EfficientSAM/"
        "d525f622e6f640acf5a0fc37c7ca1f243da5bde0/weights/efficient_sam_vitt.pt"
    ),
    "dinov2_vits14": (
        "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
    ),
}


def main():
    results = {}
    for name, url in SOURCES.items():
        try:
            # SOURCES contains only fixed official HTTPS URLs; no caller-supplied URL is accepted.
            request = Request(  # noqa: S310
                url, method="HEAD", headers={"User-Agent": "NeighborLend-EP-audit"}
            )
            with urlopen(request, timeout=25) as response:  # noqa: S310
                results[name] = {
                    "source": url,
                    "method": "HEAD",
                    "status": response.status,
                    "content_length": response.headers.get("Content-Length"),
                    "etag": response.headers.get("ETag"),
                    "final_url": response.url,
                }
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            results[name] = {
                "source": url,
                "method": "HEAD",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    target = ROOT / ".test-artifacts" / "phase-2-baseline" / "weight-headers.json"
    target.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
