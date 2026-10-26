// | MoonJMAP's transport-independent wire values.
// |
// | The Python implementation in this repository is used by the fixture runner
// | when a MoonBit compiler is unavailable.  This package mirrors its public
// | boundary so a MoonBit caller can construct the same fixed JMAP tuples and
// | hand them to an existing JSON/HTTP library.

///| The only methods exported by MoonJMAP v0.1.
pub(all) enum MethodName {
  EmailQuery
  EmailQueryChanges
  EmailGet
  EmailChanges
} derive(Eq, Debug)
pub extend MethodName with Eq::{not_equal, equal}
pub extend MethodName with @moonbitlang/core/debug.Debug::{to_repr}

///| Return the wire method name, without introducing a generic RPC dispatcher.
pub fn MethodName::wire_name(self : Self) -> String {
  match self {
    EmailQuery => "Email/query"
    EmailQueryChanges => "Email/queryChanges"
    EmailGet => "Email/get"
    EmailChanges => "Email/changes"
  }
}

///| Failure classes exposed by the wire boundary.  A sync caller can map
///| `StaleResponse` to a dropped response without advancing a checkpoint.
pub(all) enum DecodeFailure {
  InvalidInput(String)
  Unsupported(String)
  ProtocolFailure(String)
  StaleResponse(String)
} derive(Eq, Debug)
pub extend DecodeFailure with Eq::{not_equal, equal}
pub extend DecodeFailure with @moonbitlang/core/debug.Debug::{to_repr}

///| The sole supported result reference: an in-batch Email/query `/ids` value.
pub(all) struct ResultReference {
  result_of : String
} derive(Eq, Debug)
pub extend ResultReference with Eq::{not_equal, equal}
pub extend ResultReference with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn ResultReference::new(result_of : String) -> ResultReference? {
  if result_of.is_empty() {
    None
  } else {
    Some({ result_of, })
  }
}

///|
pub fn ResultReference::to_json(self : Self) -> Json {
  {
    "resultOf": Json::string(self.result_of),
    "name": Json::string("Email/query"),
    "path": Json::string("/ids"),
  }
}

///| A JMAP method call tuple.  `arguments` is a fixed-method object built by a
///| higher-level request type; this package deliberately does not parse generic
///| JSON pointers or dispatch arbitrary RPC methods.
pub(all) struct MethodCall {
  method_name : MethodName
  arguments : Json
  call_id : String
} derive(Debug)
pub extend MethodCall with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn MethodCall::new(method_name : MethodName, arguments : Json, call_id : String) -> MethodCall? {
  if call_id.is_empty() {
    None
  } else {
    Some({ method_name, arguments, call_id })
  }
}

///|
pub fn MethodCall::to_json(self : Self) -> Json {
  Json::array([
    Json::string(self.method_name.wire_name()),
    self.arguments,
    Json::string(self.call_id),
  ])
}

///| Fixed request envelope.  `using` is intentionally not configurable: the
///| v0.1 core only speaks JMAP Core + Mail.
pub(all) struct Request {
  method_calls : Array[MethodCall]
} derive(Debug)
pub extend Request with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn Request::new(method_calls : Array[MethodCall]) -> Request? {
  if method_calls.is_empty() {
    None
  } else {
    Some({ method_calls, })
  }
}

///|
pub fn Request::to_json(self : Self) -> Json {
  {
    "using": Json::array([
      Json::string("urn:ietf:params:jmap:core"),
      Json::string("urn:ietf:params:jmap:mail"),
    ]),
    "methodCalls": Json::array(self.method_calls.map(fn(call) { call.to_json() })),
  }
}

///| A server-side JMAP method error.  Unknown fields are retained in the raw
///| object by the Python codec; MoonBit callers can keep the same object here.
pub(all) struct MethodError {
  type_ : String
  arguments : Json
} derive(Debug)
pub extend MethodError with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn MethodError::new(type_ : String, arguments : Json) -> MethodError? {
  if type_.is_empty() {
    None
  } else {
    Some({ type_, arguments })
  }
}

///| Raw response tuple.  The method name is kept so the synchronisation layer
///| can correlate call IDs and validate the expected response kind before it
///| advances either state token.
pub(all) struct MethodResponse {
  name : String
  arguments : Json
  call_id : String
} derive(Debug)
pub extend MethodResponse with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn MethodResponse::new(name : String, arguments : Json, call_id : String) -> MethodResponse? {
  if call_id.is_empty() || !supported_response_name(name) {
    None
  } else {
    Some({ name, arguments, call_id })
  }
}

/// A response after a fixed-method wire adapter has decoded its accountId.
///
/// This is intentionally a metadata envelope rather than a generic JSON
/// decoder.  The adapter is responsible for decoding the four method-specific
/// argument objects; this type records the identity facts that the sync core
/// must check before accepting a response.  `can_calculate_changes` is only
/// meaningful for `Email/query`, where RFC 8621 makes it an optional member.
pub(all) struct TypedMethodResponse {
  method_name : MethodName
  account_id : String
  arguments : Json
  call_id : String
  can_calculate_changes : Bool?
} derive(Debug)
pub extend TypedMethodResponse with @moonbitlang/core/debug.Debug::{to_repr}

pub fn TypedMethodResponse::new(
  method_name : MethodName,
  account_id : String,
  arguments : Json,
  call_id : String,
  can_calculate_changes : Bool?,
) -> TypedMethodResponse? {
  if account_id.is_empty() || call_id.is_empty() {
    None
  } else if method_name != EmailQuery && can_calculate_changes is Some(_) {
    None
  } else {
    Some({
      method_name,
      account_id,
      arguments,
      call_id,
      can_calculate_changes,
    })
  }
}

/// Convert the typed metadata envelope back to the raw JMAP tuple.  The
/// accountId and optional capability remain in `arguments`; this conversion
/// does not synthesize or mutate JSON fields because this package deliberately
/// avoids a generic JSON object builder.
pub fn TypedMethodResponse::to_method_response(self : Self) -> MethodResponse? {
  MethodResponse::new(self.method_name.wire_name(), self.arguments, self.call_id)
}

pub fn TypedMethodResponse::account_matches(
  self : Self,
  expected_account_id : String,
) -> Bool {
  !expected_account_id.is_empty() && self.account_id == expected_account_id
}

fn supported_response_name(name : String) -> Bool {
  name == "error" || name == "Email/query" || name == "Email/queryChanges" ||
    name == "Email/get" || name == "Email/changes"
}

///| Fixed response envelope.  JMAP method responses are ordered tuples and may
///| contain multiple rows for one logical request; callers must not collapse
///| them into a call-id dictionary.
pub(all) struct Response {
  method_responses : Array[MethodResponse]
} derive(Debug)
pub extend Response with @moonbitlang/core/debug.Debug::{to_repr}

///|
pub fn Response::new(method_responses : Array[MethodResponse]) -> Response? {
  if method_responses.is_empty() {
    None
  } else {
    Some({ method_responses, })
  }
}

///|
pub fn Response::to_json(self : Self) -> Json {
  {
    "methodResponses": Json::array(self.method_responses.map(fn(row) {
      Json::array([
        Json::string(row.name),
        row.arguments,
        Json::string(row.call_id),
      ])
    })),
  }
}

