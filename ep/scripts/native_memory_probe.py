"""Opt-in pytest instrumentation; record original preflight without changing its decision."""

import json
import os
from pathlib import Path

import psutil


def pytest_configure(config):
    target = os.environ.get("EP_NATIVE_MEMORY_LOG")
    if not target:
        return
    from ep_engine.cv import models

    original = models.preflight

    def measured(device):
        row = dict(
            device=device,
            available_ram_bytes=psutil.virtual_memory().available,
            rss_bytes=psutil.Process().memory_info().rss,
        )
        try:
            result = original(device)
            row["status"] = "passed"
            return result
        except Exception as exc:
            row["status"] = getattr(exc, "code", type(exc).__name__)
            raise
        finally:
            with Path(target).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")

    models.preflight = measured
