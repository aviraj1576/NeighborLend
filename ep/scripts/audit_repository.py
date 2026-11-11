"""Read-only syntax audit; never import the existing app or touch its database."""

import ast
import json
from pathlib import Path

EP_ROOT = Path(__file__).resolve().parents[1]


def main():
    results = []
    for path in sorted((EP_ROOT.parent / "backend" / "app").rglob("*.py")):
        try:
            ast.parse(path.read_text("utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            results.append(
                {
                    "file": path.relative_to(EP_ROOT.parent).as_posix(),
                    "line": exc.lineno,
                    "error": exc.msg,
                }
            )
    (EP_ROOT / "docs" / "existing-syntax-audit.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
