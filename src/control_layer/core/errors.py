"""Domain exceptions."""

from __future__ import annotations

__all__ = [
    "AuthError",
    "ControlLayerError",
    "FeedError",
    "InputError",
    "PolicyError",
    "SignatureLimitError",
    "UpstreamError",
]


class ControlLayerError(Exception):
    """Base class for all control layer errors."""


class PolicyError(ControlLayerError):
    """Policy failed validation. `errors` holds human-readable 'field.path: reason' lines."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("invalid policy: " + "; ".join(errors))


class UpstreamError(ControlLayerError):
    """The model upstream or a guard model failed (transport, timeout, HTTP status, payload)."""


class AuthError(ControlLayerError):
    """Missing or unknown agent key."""


class InputError(ControlLayerError):
    """Request is malformed or uses unsupported features."""


class FeedError(ControlLayerError):
    """Signature feed failed validation or its rules' own tests; `errors` as 'path: reason'."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("invalid signature feed: " + "; ".join(errors))


class SignatureLimitError(ControlLayerError):
    """A text exceeds the signature scan limits; the control's on_error decides (fail closed)."""
