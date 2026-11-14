"""Wiring for the vendored damage_check module: service factory + auth wrapper."""
import logging
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends

from damage_check import (
    DamageCheckService, ProviderError, Settings as DamageSettings, provider_from_settings,
)

from app.config import BASE_DIR
from app.models import User
from app.services.auth import get_current_user
from app.services.damage_storage import HostDamageStorage

log = logging.getLogger(__name__)


class UnavailableProvider:
    """Used when the configured AI provider cannot start (for example no API key).

    The app still boots. Every comparison fails, and the module records a failed
    view as 'needs_review', never as 'clear'.
    """
    name = "unavailable"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def compare(self, **_kwargs):
        raise ProviderError(self.reason)


@lru_cache(maxsize=1)
def get_damage_service() -> DamageCheckService:
    # The module reads DAMAGE_* straight from os.environ, but the root .env is
    # only parsed by pydantic-settings, so export it here (real env vars win).
    load_dotenv(BASE_DIR / ".env", override=False)
    settings = DamageSettings.from_env()
    try:
        provider = provider_from_settings(settings)
    except ProviderError as exc:
        log.warning("Damage check AI provider unavailable: %s", exc)
        provider = UnavailableProvider(str(exc))
    return DamageCheckService(HostDamageStorage(), provider, settings)


def damage_user_id(user: User = Depends(get_current_user)) -> str:
    return str(user.id)
