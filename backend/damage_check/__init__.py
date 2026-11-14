"""damage_check: external-damage warning module for NeighborLend.

    from damage_check import DamageCheckService, create_router, Settings
    service = DamageCheckService(storage=MyStorage(), provider=provider_from_settings(settings))
    app.include_router(create_router(service, get_user_id), prefix="/api/damage-checks")
"""
from .config import Settings
from .exceptions import (Conflict, DamageCheckError, Forbidden, InvalidInput,
                         NotFound, ProviderError)
from .providers import GeminiProvider, MockProvider, VisionProvider, provider_from_settings
from .router import create_router
from .schemas import (CheckRecord, CheckView, DamageReport, Decision, Finding, ViewResult)
from .service import DamageCheckService, aggregate_overall
from .storage import LocalStorage, StorageBackend

__all__ = [
    "Settings", "DamageCheckService", "create_router", "aggregate_overall",
    "StorageBackend", "LocalStorage", "VisionProvider", "GeminiProvider", "MockProvider",
    "provider_from_settings", "CheckRecord", "CheckView", "DamageReport", "Decision",
    "Finding", "ViewResult", "DamageCheckError", "NotFound", "Forbidden", "Conflict",
    "InvalidInput", "ProviderError",
]
__version__ = "0.1.0"
