"""Typed, transport-independent envelopes for MoonJMAP's four JMAP methods.

This module intentionally does *not* implement a JMAP client or a generic RPC
dispatcher.  It only validates and serialises the fixed method shapes consumed
by the mail-view synchronisation core:

``Email/query``, ``Email/queryChanges``, ``Email/get`` and ``Email/changes``.

The public objects retain opaque state strings exactly as received.  A state is
never ordered, decoded, or compared to a state from another account/query.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from .errors import (
    InvalidJmapInput,
    JmapMethodError,
    ProtocolFailure,
    UnsupportedMethod,
    expect_array,
    expect_bool,
    expect_int,
    expect_object,
    expect_string,
)


CORE_URN = "urn:ietf:params:jmap:core"
MAIL_URN = "urn:ietf:params:jmap:mail"
DEFAULT_USING: tuple[str, str] = (CORE_URN, MAIL_URN)
EMAIL_PROPERTIES: tuple[str, ...] = (
    "id",
    "threadId",
    "mailboxIds",
    "keywords",
    "receivedAt",
    "subject",
    "from",
    "preview",
)
SUPPORTED_METHODS: frozenset[str] = frozenset(
    {"Email/query", "Email/queryChanges", "Email/get", "Email/changes"}
)


def _copy_json(value: Any) -> Any:
    """Copy JSON-shaped data without importing a general JSON package.

    The implementation is deliberately small and only used to detach values
    from caller-owned dictionaries/lists.  It leaves scalar values untouched.
    """

    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            # JSON object member names are strings.  Silently coercing an
            # integer (or another object) here would make a direct Python
            # construction serialize to a different wire object than the
            # caller supplied, which is particularly dangerous for method
            # arguments and Email properties.
            if not isinstance(key, str):
                raise InvalidJmapInput("JSON object keys must be strings")
            copied[key] = _copy_json(item)
        return copied
    if isinstance(value, list):
        return [_copy_json(v) for v in value]
    if isinstance(value, tuple):
        return [_copy_json(v) for v in value]
    return value


def _validate_account_id(account_id: str) -> str:
    if not isinstance(account_id, str) or not account_id:
        raise InvalidJmapInput("account_id must be a non-empty string")
    return account_id


def _validate_state(value: str, label: str) -> str:
    # State strings are opaque.  Empty is accepted because an application may
    # use it as an explicitly represented initial state in a fixture; no state
    # ordering or interpretation is performed here.
    if not isinstance(value, str):
        raise InvalidJmapInput(f"{label} must be a string")
    return value


def _validate_ids(ids: Sequence[str], label: str = "ids") -> tuple[str, ...]:
    if isinstance(ids, (str, bytes)) or not isinstance(ids, Sequence):
        raise InvalidJmapInput(f"{label} must be an array of strings")
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(ids):
        if not isinstance(value, str) or not value:
            raise InvalidJmapInput(f"{label}[{index}] must be a non-empty string")
        if value in seen:
            raise InvalidJmapInput(f"{label} contains duplicate id {value!r}")
        seen.add(value)
        result.append(value)
    return tuple(result)


def _validate_string_sequence(values: Sequence[str], label: str) -> tuple[str, ...]:
    """Validate a JSON string array used by a fixed wire field.

    Keeping this separate from ``_validate_ids`` matters for ``properties``
    and capability lists: those arrays may contain arbitrary (but non-empty)
    strings and should still reject a mapping, scalar, or bytes value instead
    of iterating over it as if it were a valid JSON array.
    """

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidJmapInput(f"{label} must be an array of strings")
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            raise InvalidJmapInput(f"{label}[{index}] must be a non-empty string")
        result.append(value)
    return tuple(result)


def _parse_ids(value: Any, path: str) -> tuple[str, ...]:
    values = expect_array(value, path=path)
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        item = expect_string(item, path=f"{path}[{index}]")
        if item in seen:
            raise ProtocolFailure("duplicate email id", path=f"{path}[{index}]")
        seen.add(item)
        result.append(item)
    return tuple(result)


def _validate_filter(filter_value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate MoonJMAP's two fixed filter projections.

    The protocol itself supports many filter forms.  Exporting a generic
    expression builder would widen this package into a JMAP client, so the
    public codec accepts only the two v0.1 projections and gives a useful
    Unsupported/invalid error to callers attempting anything else.
    """

    if not isinstance(filter_value, Mapping):
        raise InvalidJmapInput("filter must be an object")
    keys = set(filter_value)

    def validate_mailbox(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise InvalidJmapInput("filter.inMailbox must be a non-empty string")
        return value

    # Latest view: a single RFC FilterCondition.  An unread view is often
    # convenient to spell as ``{inMailbox, notKeyword}`` at the API boundary,
    # but that is not a legal JMAP wire object: combining conditions requires
    # a FilterOperator.  Normalize the convenience form to the exact RFC
    # representation before serialising it.
    if keys <= {"inMailbox", "notKeyword"}:
        if "inMailbox" not in filter_value:
            raise InvalidJmapInput("filter.inMailbox is required")
        mailbox = validate_mailbox(filter_value["inMailbox"])
        if "notKeyword" not in filter_value:
            return {"inMailbox": mailbox}
        if filter_value["notKeyword"] != "$seen":
            raise InvalidJmapInput("v0.1 only supports filter.notKeyword='$seen'")
        return {
            "operator": "AND",
            "conditions": [
                {"inMailbox": mailbox},
                {"notKeyword": "$seen"},
            ],
        }

    # Accept the canonical wire form on decode and re-emit it in a stable
    # order.  No other FilterOperator or arbitrary condition builder belongs
    # to this deliberately narrow adapter.
    if keys != {"operator", "conditions"} or filter_value.get("operator") != "AND":
        unsupported = sorted(map(str, keys - {"operator", "conditions"}))
        raise InvalidJmapInput(f"unsupported filter keys: {unsupported}")
    conditions = filter_value.get("conditions")
    if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)) or len(conditions) != 2:
        raise InvalidJmapInput("unread filter.conditions must contain exactly two conditions")
    mailbox: str | None = None
    saw_not_keyword = False
    for index, condition in enumerate(conditions):
        if not isinstance(condition, Mapping):
            raise InvalidJmapInput(f"filter.conditions[{index}] must be an object")
        condition_keys = set(condition)
        if condition_keys == {"inMailbox"}:
            if mailbox is not None:
                raise InvalidJmapInput("unread filter contains duplicate inMailbox conditions")
            mailbox = validate_mailbox(condition["inMailbox"])
        elif condition_keys == {"notKeyword"}:
            if saw_not_keyword or condition["notKeyword"] != "$seen":
                raise InvalidJmapInput("v0.1 only supports one notKeyword='$seen' condition")
            saw_not_keyword = True
        else:
            raise InvalidJmapInput("unread filter conditions must be inMailbox and notKeyword")
    if mailbox is None or not saw_not_keyword:
        raise InvalidJmapInput("unread filter requires inMailbox and notKeyword='$seen'")
    return {
        "operator": "AND",
        "conditions": [
            {"inMailbox": mailbox},
            {"notKeyword": "$seen"},
        ],
    }


def _validate_sort(sort: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if isinstance(sort, (str, bytes)) or not isinstance(sort, Sequence):
        raise InvalidJmapInput("sort must be an array")
    if len(sort) != 1:
        raise InvalidJmapInput("v0.1 requires exactly one receivedAt sort clause")
    clause = sort[0]
    if not isinstance(clause, Mapping):
        raise InvalidJmapInput("sort[0] must be an object")
    if set(clause) - {"property", "isAscending"}:
        raise InvalidJmapInput("sort[0] has unsupported fields")
    if clause.get("property") != "receivedAt" or clause.get("isAscending") is not False:
        raise InvalidJmapInput("v0.1 only supports receivedAt descending sort")
    return ({"property": "receivedAt", "isAscending": False},)


@dataclass(frozen=True)
class ResultReference:
    """The one result reference MoonJMAP emits: ``Email/query#/ids``.

    This is a constrained value object rather than a generic JSON Pointer or
    reference resolver.  It prevents accidental references across requests:
    the sync planner can only create a reference to a query call in the same
    methodCalls array.
    """

    result_of: str
    name: Literal["Email/query"] = "Email/query"
    path: Literal["/ids"] = "/ids"

    def __post_init__(self) -> None:
        if not isinstance(self.result_of, str) or not self.result_of:
            raise InvalidJmapInput("result_of must be a non-empty call id")
        if self.name != "Email/query":
            raise InvalidJmapInput("only Email/query result references are supported")
        if self.path != "/ids":
            raise InvalidJmapInput("only the /ids result path is supported")

    def to_wire(self) -> dict[str, str]:
        return {"resultOf": self.result_of, "name": self.name, "path": self.path}

    @classmethod
    def from_wire(cls, value: Any, *, path: str = "resultReference") -> "ResultReference":
        obj = expect_object(value, path=path)
        result_of = expect_string(obj.get("resultOf"), path=f"{path}.resultOf")
        name = expect_string(obj.get("name"), path=f"{path}.name")
        pointer = expect_string(obj.get("path"), path=f"{path}.path", allow_empty=True)
        if name != "Email/query":
            raise ProtocolFailure("unsupported result reference method", path=f"{path}.name")
        if pointer != "/ids":
            raise ProtocolFailure("unsupported result reference path", path=f"{path}.path")
        return cls(result_of=result_of)


IdsValue = Any


@dataclass(frozen=True)
class MethodCall:
    """One JMAP method call tuple ``[name, arguments, callId]``."""

    name: str
    arguments: Mapping[str, Any]
    call_id: str

    def __post_init__(self) -> None:
        if self.name not in SUPPORTED_METHODS:
            raise UnsupportedMethod(self.name)
        if not isinstance(self.arguments, Mapping):
            raise InvalidJmapInput("method arguments must be an object")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("call_id must be a non-empty string")

    def to_wire(self) -> list[Any]:
        return [self.name, _copy_json(dict(self.arguments)), self.call_id]

    @classmethod
    def from_wire(cls, value: Any, *, path: str = "methodCalls[]") -> "MethodCall":
        items = expect_array(value, path=path)
        if len(items) != 3:
            raise ProtocolFailure("method call must have exactly three elements", path=path)
        name = expect_string(items[0], path=f"{path}[0]")
        if name not in SUPPORTED_METHODS:
            raise UnsupportedMethod(name)
        args = expect_object(items[1], path=f"{path}[1]")
        call_id = expect_string(items[2], path=f"{path}[2]")
        try:
            copied_args = _copy_json(dict(args))
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path=f"{path}[1]") from exc
        return cls(name, copied_args, call_id)


@dataclass(frozen=True)
class JmapRequest:
    """A request object carrying only the Core + Mail capability URNs."""

    method_calls: tuple[MethodCall, ...]
    using: tuple[str, ...] = DEFAULT_USING

    def __post_init__(self) -> None:
        if isinstance(self.method_calls, (str, bytes)) or not isinstance(self.method_calls, Sequence):
            raise InvalidJmapInput("method_calls must be an array of MethodCall values")
        if not self.method_calls:
            raise InvalidJmapInput("method_calls cannot be empty")
        calls = tuple(self.method_calls)
        object.__setattr__(self, "method_calls", calls)
        ids: set[str] = set()
        calls_by_id: dict[str, MethodCall] = {}
        for call in calls:
            if not isinstance(call, MethodCall):
                raise InvalidJmapInput("method_calls must contain MethodCall values")
            if call.call_id in ids:
                raise InvalidJmapInput(f"duplicate call id {call.call_id!r}")
            ids.add(call.call_id)
            # Result references are deliberately scoped to this one ordered
            # methodCalls array.  A reference to a previous query is the only
            # legal form; in particular, it cannot survive a maxCalls=1 split
            # into a later request.
            if "#ids" in call.arguments:
                if call.name != "Email/get" or "ids" in call.arguments:
                    raise InvalidJmapInput("#ids is only valid on Email/get")
                try:
                    reference = ResultReference.from_wire(call.arguments["#ids"], path=f"{call.call_id}.#ids")
                except ProtocolFailure as exc:
                    raise InvalidJmapInput(str(exc)) from exc
                previous = calls_by_id.get(reference.result_of)
                if previous is None or previous.name != "Email/query":
                    raise InvalidJmapInput("#ids must reference a preceding Email/query in the same request")
            calls_by_id[call.call_id] = call
        using = _validate_string_sequence(self.using, "using")
        if len(using) != len(DEFAULT_USING) or set(using) != set(DEFAULT_USING):
            # The core's fixed scope is deliberate.  Extra capabilities may
            # change server semantics and must be modelled in a future version.
            raise InvalidJmapInput("MoonJMAP requests require Core and Mail URNs only")
        if len(set(using)) != len(using):
            raise InvalidJmapInput("using cannot contain duplicate capability URNs")
        object.__setattr__(self, "using", using)

    def to_wire(self) -> dict[str, Any]:
        return {"using": list(self.using), "methodCalls": [c.to_wire() for c in self.method_calls]}

    @classmethod
    def from_wire(cls, value: Any) -> "JmapRequest":
        obj = expect_object(value, path="request")
        using_raw = expect_array(obj.get("using"), path="request.using")
        using = tuple(expect_string(x, path=f"request.using[{i}]") for i, x in enumerate(using_raw))
        if len(using) != len(DEFAULT_USING) or set(using) != set(DEFAULT_USING):
            raise ProtocolFailure("request.using must contain Core and Mail URNs", path="request.using")
        calls_raw = expect_array(obj.get("methodCalls"), path="request.methodCalls")
        if not calls_raw:
            raise ProtocolFailure("methodCalls cannot be empty", path="request.methodCalls")
        calls = tuple(MethodCall.from_wire(x, path=f"request.methodCalls[{i}]") for i, x in enumerate(calls_raw))
        try:
            return cls(calls, using=using)
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path="request.methodCalls") from exc


@dataclass(frozen=True)
class EmailQueryRequest:
    account_id: str
    filter: Mapping[str, Any]
    sort: Sequence[Mapping[str, Any]] = field(default_factory=lambda: ({"property": "receivedAt", "isAscending": False},))
    collapse_threads: bool = False
    position: int = 0
    limit: int | None = None
    calculate_total: bool = True
    call_id: str = "q1"

    METHOD: ClassVar[str] = "Email/query"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        object.__setattr__(self, "filter", _validate_filter(self.filter))
        object.__setattr__(self, "sort", _validate_sort(self.sort))
        if not isinstance(self.collapse_threads, bool) or self.collapse_threads:
            raise InvalidJmapInput("v0.1 requires collapse_threads=false")
        if not isinstance(self.position, int) or isinstance(self.position, bool) or self.position < 0:
            raise InvalidJmapInput("position must be an integer >= 0")
        if self.limit is not None and (not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit < 0):
            raise InvalidJmapInput("limit must be null or an integer >= 0")
        if not isinstance(self.calculate_total, bool):
            raise InvalidJmapInput("calculate_total must be a boolean")
        if not self.calculate_total:
            raise InvalidJmapInput("v0.1 requires calculate_total=true")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("call_id must be a non-empty string")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "accountId": self.account_id,
            "filter": _copy_json(dict(self.filter)),
            "sort": _copy_json(list(self.sort)),
            "collapseThreads": False,
            "position": self.position,
            "calculateTotal": self.calculate_total,
        }
        if self.limit is not None:
            result["limit"] = self.limit
        return result

    def to_call(self) -> MethodCall:
        return MethodCall(self.METHOD, self.to_arguments(), self.call_id)

    # The long spelling is convenient for callers that build a Plan and makes
    # the public boundary read like the planning document's ``method call``
    # terminology.  Keep ``to_call`` as a compact alias for examples.
    def to_method_call(self) -> MethodCall:
        return self.to_call()


@dataclass(frozen=True)
class EmailQueryChangesRequest:
    account_id: str
    filter: Mapping[str, Any]
    since_query_state: str
    sort: Sequence[Mapping[str, Any]] = field(default_factory=lambda: ({"property": "receivedAt", "isAscending": False},))
    collapse_threads: bool = False
    max_changes: int | None = None
    call_id: str = "qc1"

    METHOD: ClassVar[str] = "Email/queryChanges"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        object.__setattr__(self, "filter", _validate_filter(self.filter))
        object.__setattr__(self, "sort", _validate_sort(self.sort))
        _validate_state(self.since_query_state, "since_query_state")
        if not isinstance(self.collapse_threads, bool) or self.collapse_threads:
            raise InvalidJmapInput("v0.1 requires collapse_threads=false")
        if self.max_changes is not None and (not isinstance(self.max_changes, int) or isinstance(self.max_changes, bool) or self.max_changes < 0):
            raise InvalidJmapInput("max_changes must be null or an integer >= 0")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("call_id must be a non-empty string")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "accountId": self.account_id,
            "filter": _copy_json(dict(self.filter)),
            "sort": _copy_json(list(self.sort)),
            "collapseThreads": False,
            "sinceQueryState": self.since_query_state,
        }
        if self.max_changes is not None:
            result["maxChanges"] = self.max_changes
        return result

    def to_call(self) -> MethodCall:
        return MethodCall(self.METHOD, self.to_arguments(), self.call_id)

    def to_method_call(self) -> MethodCall:
        return self.to_call()


@dataclass(frozen=True)
class EmailGetRequest:
    account_id: str
    ids: IdsValue
    properties: Sequence[str] = EMAIL_PROPERTIES
    call_id: str = "g1"

    METHOD: ClassVar[str] = "Email/get"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        if isinstance(self.ids, ResultReference):
            pass
        else:
            object.__setattr__(self, "ids", _validate_ids(self.ids))
        props = _validate_string_sequence(self.properties, "properties")
        if len(set(props)) != len(props):
            raise InvalidJmapInput("properties contains duplicate names")
        object.__setattr__(self, "properties", props)
        if not props:
            raise InvalidJmapInput("properties cannot be empty")
        unsupported = set(props) - set(EMAIL_PROPERTIES)
        if unsupported:
            raise InvalidJmapInput(f"unsupported Email/get properties: {sorted(unsupported)}")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("call_id must be a non-empty string")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {"accountId": self.account_id, "properties": list(self.properties)}
        if isinstance(self.ids, ResultReference):
            result["#ids"] = self.ids.to_wire()
        else:
            result["ids"] = list(self.ids)
        return result

    def to_call(self) -> MethodCall:
        return MethodCall(self.METHOD, self.to_arguments(), self.call_id)

    def to_method_call(self) -> MethodCall:
        return self.to_call()


@dataclass(frozen=True)
class EmailChangesRequest:
    account_id: str
    since_state: str
    max_changes: int | None = None
    call_id: str = "c1"

    METHOD: ClassVar[str] = "Email/changes"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        _validate_state(self.since_state, "since_state")
        if self.max_changes is not None and (not isinstance(self.max_changes, int) or isinstance(self.max_changes, bool) or self.max_changes < 0):
            raise InvalidJmapInput("max_changes must be null or an integer >= 0")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("call_id must be a non-empty string")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {"accountId": self.account_id, "sinceState": self.since_state}
        if self.max_changes is not None:
            result["maxChanges"] = self.max_changes
        return result

    def to_call(self) -> MethodCall:
        return MethodCall(self.METHOD, self.to_arguments(), self.call_id)

    def to_method_call(self) -> MethodCall:
        return self.to_call()


def _parse_common_request_account(args: Mapping[str, Any], path: str) -> str:
    return expect_string(args.get("accountId"), path=f"{path}.accountId")


def decode_request_call(call: MethodCall) -> EmailQueryRequest | EmailQueryChangesRequest | EmailGetRequest | EmailChangesRequest:
    """Decode one validated call to one of the four typed request objects."""

    args = call.arguments
    try:
        account = _parse_common_request_account(args, "arguments")
        if call.name == "Email/query":
            filter_value = expect_object(args.get("filter"), path="arguments.filter")
            sort = expect_array(args.get("sort"), path="arguments.sort")
            return EmailQueryRequest(
                account,
                filter_value,
                sort=sort,
                collapse_threads=args.get("collapseThreads", False),
                position=expect_int(args.get("position", 0), path="arguments.position", minimum=0),
                limit=None if "limit" not in args else expect_int(args["limit"], path="arguments.limit", minimum=0),
                calculate_total=expect_bool(args.get("calculateTotal", False), path="arguments.calculateTotal"),
                call_id=call.call_id,
            )
        if call.name == "Email/queryChanges":
            filter_value = expect_object(args.get("filter"), path="arguments.filter")
            sort = expect_array(args.get("sort"), path="arguments.sort")
            return EmailQueryChangesRequest(
                account,
                filter_value,
                since_query_state=expect_string(args.get("sinceQueryState"), path="arguments.sinceQueryState", allow_empty=True),
                sort=sort,
                collapse_threads=args.get("collapseThreads", False),
                max_changes=None if "maxChanges" not in args else expect_int(args["maxChanges"], path="arguments.maxChanges", minimum=0),
                call_id=call.call_id,
            )
        if call.name == "Email/get":
            if "ids" in args and "#ids" in args:
                raise ProtocolFailure("Email/get cannot contain both ids and #ids", path="arguments")
            if "#ids" in args:
                ids: IdsValue = ResultReference.from_wire(args["#ids"], path="arguments.#ids")
            elif "ids" in args:
                ids = _parse_ids(args["ids"], "arguments.ids")
            else:
                raise ProtocolFailure("Email/get requires ids or #ids", path="arguments")
            props_raw = expect_array(args.get("properties"), path="arguments.properties")
            props = tuple(expect_string(x, path=f"arguments.properties[{i}]") for i, x in enumerate(props_raw))
            return EmailGetRequest(account, ids, properties=props, call_id=call.call_id)
        if call.name == "Email/changes":
            return EmailChangesRequest(
                account,
                since_state=expect_string(args.get("sinceState"), path="arguments.sinceState", allow_empty=True),
                max_changes=None if "maxChanges" not in args else expect_int(args["maxChanges"], path="arguments.maxChanges", minimum=0),
                call_id=call.call_id,
            )
    except InvalidJmapInput as exc:
        raise ProtocolFailure(str(exc), path="arguments") from exc
    raise UnsupportedMethod(call.name)


@dataclass(frozen=True)
class QueryAdded:
    id: str
    index: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise InvalidJmapInput("added.id must be a non-empty string")
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise InvalidJmapInput("added.index must be an integer >= 0")

    def to_wire(self) -> dict[str, Any]:
        return {"id": self.id, "index": self.index}


@dataclass(frozen=True)
class EmailObject:
    """A projected Email object, retaining unknown server properties."""

    id: str
    properties: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise InvalidJmapInput("Email object id must be a non-empty string")
        if not isinstance(self.properties, Mapping):
            raise InvalidJmapInput("Email object properties must be an object")
        if "id" in self.properties and self.properties["id"] != self.id:
            raise InvalidJmapInput("Email object id disagrees with properties.id")
        object.__setattr__(self, "properties", _copy_json(dict(self.properties)))

    def to_wire(self) -> dict[str, Any]:
        result = dict(self.properties)
        result["id"] = self.id
        return result

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.properties[key]


def _parse_query_added(value: Any, *, path: str) -> QueryAdded:
    obj = expect_object(value, path=path)
    ident = expect_string(obj.get("id"), path=f"{path}.id")
    index = expect_int(obj.get("index"), path=f"{path}.index", minimum=0)
    try:
        return QueryAdded(ident, index)
    except InvalidJmapInput as exc:
        raise ProtocolFailure(str(exc), path=path) from exc


def _parse_query_removed(value: Any, *, path: str) -> str:
    # RFC 8621 represents removed query IDs as a string array.  Keeping this
    # parser separate from ``added`` is important: the latter carries an
    # insertion index while a removal does not.  A previous draft accepted
    # ``{"id": ...}`` here and silently diverged from real servers.
    return expect_string(value, path=path)


def _assert_unique(values: Sequence[str], *, path: str) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            raise ProtocolFailure("duplicate id", path=f"{path}[{index}]")
        seen.add(value)


@dataclass(frozen=True)
class EmailQueryResponse:
    account_id: str
    query_state: str
    ids: tuple[str, ...]
    position: int
    total: int
    can_calculate_changes: bool | None = None

    METHOD: ClassVar[str] = "Email/query"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        _validate_state(self.query_state, "query_state")
        object.__setattr__(self, "ids", _validate_ids(self.ids))
        if not isinstance(self.position, int) or isinstance(self.position, bool) or self.position < 0:
            raise InvalidJmapInput("position must be an integer >= 0")
        if not isinstance(self.total, int) or isinstance(self.total, bool) or self.total < 0:
            raise InvalidJmapInput("total must be an integer >= 0")
        if self.position + len(self.ids) > self.total:
            raise InvalidJmapInput("query page extends beyond total")
        if self.can_calculate_changes is not None and not isinstance(self.can_calculate_changes, bool):
            raise InvalidJmapInput("can_calculate_changes must be a boolean or null")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "accountId": self.account_id,
            "queryState": self.query_state,
            "ids": list(self.ids),
            "position": self.position,
            "total": self.total,
        }
        if self.can_calculate_changes is not None:
            result["canCalculateChanges"] = self.can_calculate_changes
        return result

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> "EmailQueryResponse":
        obj = expect_object(arguments, path="arguments")
        ids = _parse_ids(obj.get("ids"), "arguments.ids")
        position = expect_int(obj.get("position"), path="arguments.position", minimum=0)
        total = expect_int(obj.get("total"), path="arguments.total", minimum=0)
        if "canCalculateChanges" in obj:
            can = expect_bool(obj["canCalculateChanges"], path="arguments.canCalculateChanges")
        else:
            can = None
        try:
            return cls(
                account_id=expect_string(obj.get("accountId"), path="arguments.accountId"),
                query_state=expect_string(obj.get("queryState"), path="arguments.queryState", allow_empty=True),
                ids=ids,
                position=position,
                total=total,
                can_calculate_changes=can,
            )
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path="arguments") from exc


@dataclass(frozen=True)
class EmailQueryChangesResponse:
    """A query delta; unlike Email/changes it is not a paginated changes feed.

    JMAP reports ``tooManyChanges`` as a method error instead of exposing a
    ``hasMoreChanges`` field here.  Keeping that distinction prevents callers
    from treating a query delta as a second token-paginated stream.
    """

    account_id: str
    old_query_state: str
    new_query_state: str
    removed: tuple[str, ...]
    added: tuple[QueryAdded, ...]
    # RFC 8620 §5.6 makes ``total`` conditional: it is present only when
    # the request included ``calculateTotal: true``.  Real servers such as
    # Stalwart omit it for the normal delta request, so the wire model must
    # preserve that distinction instead of treating a compliant response as
    # a protocol failure.
    total: int | None = None

    METHOD: ClassVar[str] = "Email/queryChanges"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        _validate_state(self.old_query_state, "old_query_state")
        _validate_state(self.new_query_state, "new_query_state")
        object.__setattr__(self, "removed", _validate_ids(self.removed, "removed"))
        if isinstance(self.added, (str, bytes)) or not isinstance(self.added, Sequence):
            raise InvalidJmapInput("added must be an array of QueryAdded values")
        object.__setattr__(self, "added", tuple(self.added))
        seen_added: set[str] = set()
        for item in self.added:
            if not isinstance(item, QueryAdded):
                raise InvalidJmapInput("added must contain QueryAdded values")
            if item.id in seen_added:
                raise InvalidJmapInput(f"added contains duplicate id {item.id!r}")
            seen_added.add(item.id)
        if self.total is not None and (
            not isinstance(self.total, int) or isinstance(self.total, bool) or self.total < 0
        ):
            raise InvalidJmapInput("total must be an integer >= 0 or null")
        for item in self.added:
            if self.total is not None and (self.total == 0 or item.index >= self.total):
                raise InvalidJmapInput("added index is out of bounds")

    def to_arguments(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "accountId": self.account_id,
            "oldQueryState": self.old_query_state,
            "newQueryState": self.new_query_state,
            "removed": list(self.removed),
            "added": [x.to_wire() for x in self.added],
        }
        if self.total is not None:
            result["total"] = self.total
        return result

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> "EmailQueryChangesResponse":
        obj = expect_object(arguments, path="arguments")
        removed_raw = expect_array(obj.get("removed"), path="arguments.removed")
        removed = tuple(_parse_query_removed(x, path=f"arguments.removed[{i}]") for i, x in enumerate(removed_raw))
        _assert_unique(removed, path="arguments.removed")
        added_raw = expect_array(obj.get("added"), path="arguments.added")
        added = tuple(_parse_query_added(x, path=f"arguments.added[{i}]") for i, x in enumerate(added_raw))
        try:
            return cls(
                account_id=expect_string(obj.get("accountId"), path="arguments.accountId"),
                old_query_state=expect_string(obj.get("oldQueryState"), path="arguments.oldQueryState", allow_empty=True),
                new_query_state=expect_string(obj.get("newQueryState"), path="arguments.newQueryState", allow_empty=True),
                removed=removed,
                added=added,
                total=(
                    expect_int(obj["total"], path="arguments.total", minimum=0)
                    if "total" in obj
                    else None
                ),
            )
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path="arguments") from exc


@dataclass(frozen=True)
class EmailGetResponse:
    account_id: str
    state: str
    list: tuple[EmailObject, ...]
    not_found: tuple[str, ...] = ()

    METHOD: ClassVar[str] = "Email/get"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        _validate_state(self.state, "state")
        if isinstance(self.list, (str, bytes)) or not isinstance(self.list, Sequence):
            raise InvalidJmapInput("list must be an array of EmailObject values")
        objects = tuple(self.list)
        seen: set[str] = set()
        for item in objects:
            if not isinstance(item, EmailObject):
                raise InvalidJmapInput("list must contain EmailObject values")
            if item.id in seen:
                raise InvalidJmapInput(f"list contains duplicate id {item.id!r}")
            seen.add(item.id)
        object.__setattr__(self, "list", objects)
        nf = _validate_ids(self.not_found, "not_found")
        if seen.intersection(nf):
            raise InvalidJmapInput("an id cannot occur in both list and not_found")
        object.__setattr__(self, "not_found", nf)

    def to_arguments(self) -> dict[str, Any]:
        return {
            "accountId": self.account_id,
            "state": self.state,
            "list": [x.to_wire() for x in self.list],
            "notFound": list(self.not_found),
        }

    def by_id(self) -> dict[str, EmailObject]:
        """Return the response objects keyed by ID, independent of wire order."""

        return {item.id: item for item in self.list}

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> "EmailGetResponse":
        obj = expect_object(arguments, path="arguments")
        rows = expect_array(obj.get("list"), path="arguments.list")
        objects: list[EmailObject] = []
        for index, value in enumerate(rows):
            item = expect_object(value, path=f"arguments.list[{index}]")
            ident = expect_string(item.get("id"), path=f"arguments.list[{index}].id")
            try:
                objects.append(EmailObject(ident, item))
            except InvalidJmapInput as exc:
                raise ProtocolFailure(str(exc), path=f"arguments.list[{index}]") from exc
        # RFC 8620 §5.1 makes ``notFound`` a required response member.  An
        # empty array is the valid value when every requested id exists (or
        # the request had no ids); an omitted member is a malformed response,
        # not an equivalent shorthand.
        nf_raw = expect_array(obj.get("notFound"), path="arguments.notFound")
        nf = tuple(expect_string(x, path=f"arguments.notFound[{i}]") for i, x in enumerate(nf_raw))
        _assert_unique(nf, path="arguments.notFound")
        try:
            return cls(
                account_id=expect_string(obj.get("accountId"), path="arguments.accountId"),
                state=expect_string(obj.get("state"), path="arguments.state", allow_empty=True),
                list=tuple(objects),
                not_found=nf,
            )
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path="arguments") from exc


@dataclass(frozen=True)
class EmailChangesResponse:
    account_id: str
    old_state: str
    new_state: str
    has_more_changes: bool
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    destroyed: tuple[str, ...] = ()

    METHOD: ClassVar[str] = "Email/changes"

    def __post_init__(self) -> None:
        _validate_account_id(self.account_id)
        _validate_state(self.old_state, "old_state")
        _validate_state(self.new_state, "new_state")
        if not isinstance(self.has_more_changes, bool):
            raise InvalidJmapInput("has_more_changes must be a boolean")
        object.__setattr__(self, "created", _validate_ids(self.created, "created"))
        object.__setattr__(self, "updated", _validate_ids(self.updated, "updated"))
        object.__setattr__(self, "destroyed", _validate_ids(self.destroyed, "destroyed"))

    def to_arguments(self) -> dict[str, Any]:
        return {
            "accountId": self.account_id,
            "oldState": self.old_state,
            "newState": self.new_state,
            "hasMoreChanges": self.has_more_changes,
            "created": list(self.created),
            "updated": list(self.updated),
            "destroyed": list(self.destroyed),
        }

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> "EmailChangesResponse":
        obj = expect_object(arguments, path="arguments")
        # RFC 8620 §5.2 defines all three change sets as required ``Id[]``
        # response members.  Missing and empty are distinct: only the latter
        # means that this page contains no changes of that kind.
        created = _parse_ids(obj.get("created"), "arguments.created")
        updated = _parse_ids(obj.get("updated"), "arguments.updated")
        destroyed = _parse_ids(obj.get("destroyed"), "arguments.destroyed")
        try:
            return cls(
                account_id=expect_string(obj.get("accountId"), path="arguments.accountId"),
                old_state=expect_string(obj.get("oldState"), path="arguments.oldState", allow_empty=True),
                new_state=expect_string(obj.get("newState"), path="arguments.newState", allow_empty=True),
                has_more_changes=expect_bool(obj.get("hasMoreChanges"), path="arguments.hasMoreChanges"),
                created=created,
                updated=updated,
                destroyed=destroyed,
            )
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path="arguments") from exc


TypedResponse = Any


@dataclass(frozen=True)
class MethodResponse:
    """A raw response tuple, or a typed error response."""

    name: str
    arguments: Mapping[str, Any] | JmapMethodError
    call_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise InvalidJmapInput("response name must be a non-empty string")
        if self.name != "error" and self.name not in SUPPORTED_METHODS:
            raise UnsupportedMethod(self.name)
        if not isinstance(self.arguments, (Mapping, JmapMethodError)):
            raise InvalidJmapInput("response arguments must be an object or JmapMethodError")
        if not isinstance(self.call_id, str) or not self.call_id:
            raise InvalidJmapInput("response call_id must be a non-empty string")

    @property
    def is_error(self) -> bool:
        return self.name == "error"

    def to_wire(self) -> list[Any]:
        args: Any = self.arguments.to_arguments() if isinstance(self.arguments, JmapMethodError) else _copy_json(dict(self.arguments))
        return [self.name, args, self.call_id]

    @classmethod
    def from_wire(cls, value: Any, *, path: str = "methodResponses[]") -> "MethodResponse":
        items = expect_array(value, path=path)
        if len(items) != 3:
            raise ProtocolFailure("method response must have exactly three elements", path=path)
        name = expect_string(items[0], path=f"{path}[0]")
        if name != "error" and name not in SUPPORTED_METHODS:
            raise UnsupportedMethod(name)
        args = expect_object(items[1], path=f"{path}[1]")
        call_id = expect_string(items[2], path=f"{path}[2]")
        if name == "error":
            return cls(name, JmapMethodError.from_arguments(args), call_id)
        try:
            copied_args = _copy_json(dict(args))
        except InvalidJmapInput as exc:
            raise ProtocolFailure(str(exc), path=f"{path}[1]") from exc
        return cls(name, copied_args, call_id)

    def decode_typed(self) -> TypedResponse | JmapMethodError:
        if self.is_error:
            assert isinstance(self.arguments, JmapMethodError)
            return self.arguments
        assert isinstance(self.arguments, Mapping)
        if self.name == "Email/query":
            return EmailQueryResponse.from_arguments(self.arguments)
        if self.name == "Email/queryChanges":
            return EmailQueryChangesResponse.from_arguments(self.arguments)
        if self.name == "Email/get":
            return EmailGetResponse.from_arguments(self.arguments)
        if self.name == "Email/changes":
            return EmailChangesResponse.from_arguments(self.arguments)
        raise UnsupportedMethod(self.name)


@dataclass(frozen=True)
class JmapResponse:
    method_responses: tuple[MethodResponse, ...]

    def __post_init__(self) -> None:
        if isinstance(self.method_responses, (str, bytes)) or not isinstance(self.method_responses, Sequence):
            raise InvalidJmapInput("method_responses must be an array of MethodResponse values")
        if not self.method_responses:
            raise InvalidJmapInput("method_responses cannot be empty")
        responses = tuple(self.method_responses)
        if any(not isinstance(response, MethodResponse) for response in responses):
            raise InvalidJmapInput("method_responses must contain MethodResponse values")
        object.__setattr__(self, "method_responses", responses)

    def to_wire(self) -> dict[str, Any]:
        return {"methodResponses": [x.to_wire() for x in self.method_responses]}

    @classmethod
    def from_wire(cls, value: Any) -> "JmapResponse":
        obj = expect_object(value, path="response")
        rows = expect_array(obj.get("methodResponses"), path="response.methodResponses")
        if not rows:
            raise ProtocolFailure("methodResponses cannot be empty", path="response.methodResponses")
        return cls(tuple(MethodResponse.from_wire(x, path=f"response.methodResponses[{i}]") for i, x in enumerate(rows)))

