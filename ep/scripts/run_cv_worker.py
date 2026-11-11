"""Run one explicitly queued CV job natively. Authenticate with EP_WORKER_TOKEN in env."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.config import Settings
from ep_engine.core.security import LocalAuthorization
from ep_engine.cv.service import CVService
from ep_engine.storage.local import LocalStorage
from ep_engine.storage.repository import Repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    args = parser.parse_args()
    settings = Settings.from_environment()
    authorization = LocalAuthorization.from_file(Path(os.environ["EP_LOCAL_GRANTS_FILE"]))
    grant = authorization.authenticate("Bearer " + os.environ.get("EP_WORKER_TOKEN", ""))
    service = CVService(
        settings.data_dir,
        Repository(settings.data_dir / "ep.sqlite3"),
        LocalStorage(settings.data_dir / "evidence"),
    )
    package = service.execute(args.run_id, grant)
    print(
        f"CV outcome: {package.outcome}; candidates: {len(package.candidates)}; "
        "human review required"
    )


if __name__ == "__main__":
    main()
