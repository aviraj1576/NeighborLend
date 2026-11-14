class DamageCheckError(Exception):
    """Base class. The router maps subclasses to HTTP status codes."""


class NotFound(DamageCheckError):
    pass


class Forbidden(DamageCheckError):
    pass


class Conflict(DamageCheckError):
    pass


class InvalidInput(DamageCheckError):
    pass


class ProviderError(DamageCheckError):
    """The vision model call failed (network, quota, blocked response, ...)."""
