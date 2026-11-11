import hashlib
import hmac
import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ep_engine.core.exceptions import EPError

Role = Literal["lender", "borrower"]


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject: str = Field(min_length=1)
    rentals: dict[str, Role]

    def authorize(self, rental: str, stage: str | None = None) -> Role:
        role = self.rentals.get(rental)
        if role is None or (stage and role != {"before": "lender", "after": "borrower"}[stage]):
            raise EPError(403, "forbidden", "Not authorized for this rental or capture stage")
        return role


class Authorization(Protocol):
    """Future adapter must verify NeighborLend identity and current rental grants."""

    @property
    def configured(self) -> bool: ...

    def authenticate(self, header: str | None) -> Grant: ...


class LocalAuthorization:
    """Explicit local fixtures, never a production identity provider or token issuer."""

    def __init__(self, tokens: dict[str, Grant] | None = None):
        self._tokens = [
            (hashlib.sha256(token.encode()).digest(), grant)
            for token, grant in (tokens or {}).items()
        ]

    @property
    def configured(self) -> bool:
        return bool(self._tokens)

    def authenticate(self, header: str | None) -> Grant:
        if not self.configured:
            raise EPError(503, "auth_unconfigured", "Authorization adapter is not configured")
        if header and header.startswith("Bearer "):
            supplied = hashlib.sha256(header[7:].encode()).digest()
            for expected, grant in self._tokens:
                if hmac.compare_digest(supplied, expected):
                    return grant
        raise EPError(401, "unauthenticated", "Valid bearer credentials required")

    @classmethod
    def from_file(cls, path: Path):
        class Entry(BaseModel):
            model_config = ConfigDict(extra="forbid")
            token: SecretStr = Field(min_length=24)
            grant: Grant

        entries = [Entry.model_validate(item) for item in json.loads(path.read_text("utf-8"))]
        tokens = {entry.token.get_secret_value(): entry.grant for entry in entries}
        if len(tokens) != len(entries):
            raise ValueError("Duplicate local credentials")
        return cls(tokens)
