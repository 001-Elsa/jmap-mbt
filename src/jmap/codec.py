"""Strict JSON helpers for the fixed MoonJMAP wire subset.

The synchronisation core does not need a JSON implementation of its own.  This
module is a small adapter around Python's standard encoder so tests and a thin
diagnostic example can exercise the exact JMAP tuples without a transport.  A
caller using another JSON implementation may use the ``to_wire``/``from_wire``
methods directly.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import ProtocolFailure
from .methods import (
    JmapRequest,
    JmapResponse,
    MethodCall,
    MethodResponse,
    decode_request_call,
)


def dumps(value: Any, *, pretty: bool = False) -> str:
    """Encode a wire-shaped value deterministically.

    ``sort_keys`` is intentionally disabled: JMAP object member ordering has
    no semantic meaning, while preserving insertion order makes traces easier
    to compare against RFC examples.  NaN and Infinity are rejected because
    they are not JSON numbers.
    """

    if hasattr(value, "to_wire"):
        value = value.to_wire()
    kwargs: dict[str, Any] = {
        "ensure_ascii": False,
        "allow_nan": False,
        "separators": (",", ":") if not pretty else None,
    }
    if pretty:
        kwargs["indent"] = 2
    try:
        return json.dumps(value, **kwargs)
    except (TypeError, ValueError) as exc:
        raise ProtocolFailure(f"value is not JSON serialisable: {exc}") from exc


def loads(text: str) -> Any:
    if not isinstance(text, str):
        raise ProtocolFailure("JSON input must be text")
    try:
        # parse_constant prevents Python's permissive NaN/Infinity extension.
        return json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProtocolFailure(f"invalid JSON: {exc}") from exc


def encode_request(request: JmapRequest) -> str:
    return dumps(request)


def decode_request(text_or_value: str | Any) -> JmapRequest:
    value = loads(text_or_value) if isinstance(text_or_value, str) else text_or_value
    return JmapRequest.from_wire(value)


def encode_response(response: JmapResponse) -> str:
    return dumps(response)


def decode_response(text_or_value: str | Any) -> JmapResponse:
    value = loads(text_or_value) if isinstance(text_or_value, str) else text_or_value
    return JmapResponse.from_wire(value)


def encode_call(call: MethodCall) -> str:
    return dumps(call.to_wire())


def decode_call(text_or_value: str | Any) -> MethodCall:
    value = loads(text_or_value) if isinstance(text_or_value, str) else text_or_value
    return MethodCall.from_wire(value)


def encode_method_response(response: MethodResponse) -> str:
    return dumps(response.to_wire())


def decode_method_response(text_or_value: str | Any) -> MethodResponse:
    value = loads(text_or_value) if isinstance(text_or_value, str) else text_or_value
    return MethodResponse.from_wire(value)


def decode_typed_method_response(text_or_value: str | Any):
    """Decode one method tuple and then validate its method-specific shape."""

    return decode_method_response(text_or_value).decode_typed()


def decode_request_calls(request: JmapRequest):
    """Return typed finite-subset request values in their wire order."""

    return tuple(decode_request_call(call) for call in request.method_calls)

