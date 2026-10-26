"""Errors used by the small, transport independent JMAP codec.

The sync engine deliberately distinguishes malformed wire data from an error
returned by the server.  The former is a protocol failure and must never move a
checkpoint forward; the latter is a normal JMAP method response that the sync
engine can turn into a recovery plan (for example ``cannotCalculateChanges``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


# JMAP method-error names that affect the v0.1 recovery policy.  Servers may
# return extensions; the codec preserves unknown names rather than treating
# them as success.
RECOVERY_ERROR_TYPES = frozenset(
    {
        "cannotCalculateChanges",
        "tooManyChanges",
        "notFound",
        "stateMismatch",
        "invalidArguments",
        "invalidResultReference",
    }
)


class JmapError(ValueError):
    """Base class for deterministic input/wire errors."""


class InvalidJmapInput(JmapError):
    """The caller attempted to construct an invalid fixed-subset request."""


class ProtocolFailure(JmapError):
    """A response cannot be safely interpreted as a JMAP method response."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class UnsupportedMethod(JmapError):
    """A method outside MoonJMAP's deliberately narrow four-method subset."""


class StaleResponse(JmapError):
    """A response belongs to an old request generation or another view."""


@dataclass(frozen=True)
class JmapMethodError:
    """A typed view of a JMAP ``error`` method response.

    ``details`` and ``raw`` are intentionally retained.  JMAP servers add
    method-specific members to error arguments, and dropping them makes it
    impossible for a caller to diagnose or implement a recovery policy.  The
    codec never interprets an unknown error type as success.
    """

    type: str
    description: str | None = None
    details: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type:
            raise InvalidJmapInput("JMAP error type must be a non-empty string")
        if self.description is not None and not isinstance(self.description, str):
            raise InvalidJmapInput("JMAP error description must be a string or null")
        if self.details is not None and not isinstance(self.details, Mapping):
            raise InvalidJmapInput("JMAP error details must be an object or null")
        if self.raw is not None and not isinstance(self.raw, Mapping):
            raise InvalidJmapInput("JMAP error raw arguments must be an object or null")

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> "JmapMethodError":
        if not isinstance(arguments, Mapping):
            raise ProtocolFailure("error arguments must be an object")
        raw = dict(arguments)
        typ = raw.get("type")
        if not isinstance(typ, str) or not typ:
            raise ProtocolFailure("error.type must be a non-empty string", path="arguments.type")
        description = raw.get("description")
        if "description" in raw and not isinstance(description, str):
            raise ProtocolFailure("error.description must be a string when present", path="arguments.description")
        # Keep all non-standard members as details.  The known fields are
        # omitted only from this convenience mapping; ``raw`` remains exact.
        details = {k: v for k, v in raw.items() if k not in {"type", "description"}}
        return cls(
            type=typ,
            description=description,
            details=details or None,
            raw=raw,
        )

    def to_arguments(self) -> dict[str, Any]:
        if self.raw is not None:
            # A copy protects the immutable response object from a caller's
            # later mutation while retaining every server field verbatim.
            return dict(self.raw)
        result: dict[str, Any] = {"type": self.type}
        if self.description is not None:
            result["description"] = self.description
        if self.details:
            result.update(self.details)
        return result


def expect_object(value: Any, *, path: str) -> Mapping[str, Any]:
    """Return a mapping or raise a consistently labelled protocol failure."""

    if not isinstance(value, Mapping):
        raise ProtocolFailure("expected an object", path=path)
    # JSON object member names are always strings.  ``json.loads`` already
    # guarantees this for text input, but callers may pass decoded Python
    # values directly; rejecting non-string keys keeps both entry paths
    # equivalent and avoids silently coercing malformed data.
    for key in value:
        if not isinstance(key, str):
            raise ProtocolFailure("object member names must be strings", path=path)
    return value


def expect_string(value: Any, *, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise ProtocolFailure(f"expected a {qualifier}string", path=path)
    return value


def expect_int(value: Any, *, path: str, minimum: int | None = None) -> int:
    # bool is an int subclass in Python but is never a JMAP integer.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolFailure("expected an integer", path=path)
    if minimum is not None and value < minimum:
        raise ProtocolFailure(f"expected an integer >= {minimum}", path=path)
    return value


def expect_bool(value: Any, *, path: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolFailure("expected a boolean", path=path)
    return value


def expect_array(value: Any, *, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProtocolFailure("expected an array", path=path)
    return value

