///|
/// MoonJMAP's stateful core.  The package is deliberately transport agnostic:
/// a caller turns `Request` into a JMAP call and feeds the decoded response
/// back to `accept_response`.
pub(all) struct AccountScope {
  service_identity : String
  account_id : String
} derive(Eq)

///|
pub extend AccountScope with Eq::{not_equal, equal}

///|
pub(all) struct QueryKey {
  account : AccountScope
  view : @email.ViewSpec
  collapse_threads : Bool
} derive(Eq)

///|
pub extend QueryKey with Eq::{not_equal, equal}

///|
pub fn QueryKey::canonical(self : QueryKey) -> String {
  self.account.service_identity +
  "|" +
  self.account.account_id +
  "|" +
  self.view.name() +
  "|" +
  self.view.filter_spec().canonical() +
  "|" +
  self.view.sort_spec().canonical() +
  "|collapse=" +
  self.collapse_threads.to_string()
}

///|
pub(all) struct Limits {
  prefix_limit : Int32
  max_rounds : Int32
  max_bytes : Int32
  max_objects_per_get : Int32
  /// Cumulative number of Email/changes entries accepted in one generation.
  /// A rounds or byte budget alone cannot bound a server-paginated change set.
  max_changes : Int32
} derive(Eq)

///|
pub extend Limits with Eq::{not_equal, equal}

///|
/// A caller-owned projection of the server capabilities needed by this
/// bounded, read-only view. It contains no session URL, credentials,
/// transport handle, or generic capability map.
pub(all) struct CapabilityProjection {
  supports_filter : Bool
  supports_sort : Bool
  supports_query_changes : Bool
  supports_email_changes : Bool
  supports_result_reference : Bool
  max_objects_per_get : Int32
  max_calls_in_request : Int32
} derive(Eq)

///|
pub extend CapabilityProjection with Eq::{not_equal, equal}

///|
pub fn default_capabilities() -> CapabilityProjection {
  {
    supports_filter: true,
    supports_sort: true,
    supports_query_changes: true,
    supports_email_changes: true,
    // The planner emits one call per plan and explicit IDs, so it does not
    // depend on ResultReference support.
    supports_result_reference: false,
    max_objects_per_get: 50,
    max_calls_in_request: 1,
  }
}

///|
fn capability_error(capabilities : CapabilityProjection) -> String? {
  if capabilities.max_objects_per_get <= 0 ||
    capabilities.max_calls_in_request <= 0 {
    Some("capability limits must be positive")
  } else if !capabilities.supports_filter || !capabilities.supports_sort {
    Some("fixed_query_projection_not_supported")
  } else if !capabilities.supports_query_changes {
    Some("Email/queryChanges is not supported")
  } else if !capabilities.supports_email_changes {
    Some("Email/changes is not supported")
  } else {
    None
  }
}

///|
pub fn default_limits() -> Limits {
  {
    prefix_limit: 50,
    max_rounds: 8,
    max_bytes: 4_000_000,
    max_objects_per_get: 50,
    max_changes: 500,
  }
}

///|
pub(all) enum Completeness {
  Ready
  Pending
  NeedsRefresh
  Unsupported
  ProtocolFailure
} derive(Eq)

///|
pub extend Completeness with Eq::{not_equal, equal}

///|
pub(all) enum RequestKind {
  Query
  QueryChanges
  Get
  Changes
} derive(Eq)

///|
pub extend RequestKind with Eq::{not_equal, equal}

///|
pub(all) struct RequestTicket {
  generation : Int32
  request_id : Int32
  account : AccountScope
  query : QueryKey
  kind : RequestKind
  expected_query_state : String?
  expected_email_state : String?
  requested_ids : Array[String]
  position : Int32
  limit : Int32
  /// Exact maxChanges for Email/changes, or zero for other methods.
  max_changes : Int32
} derive(Eq)

///|
pub extend RequestTicket with Eq::{not_equal, equal}

///|
pub(all) struct Request {
  ticket : RequestTicket
  kind : RequestKind
  ids : Array[String]
  position : Int32
  limit : Int32
  /// Wire-level maxChanges for Email/changes, or zero for other methods.
  max_changes : Int32
  /// Present only for Email/query and Email/queryChanges.  These are closed
  /// projections; callers must map them to RFC filter/sort JSON in an
  /// external JMAP adapter rather than sending canonical debug strings.
  filter : @email.FilterSpec?
  sort : @email.SortSpec?
  properties : Array[String]
} derive(Eq)

///|
pub extend Request with Eq::{not_equal, equal}

///|
pub(all) struct Plan {
  generation : Int32
  reason : String
  requests : Array[Request]
} derive(Eq)

///|
pub extend Plan with Eq::{not_equal, equal}

///|
pub(all) struct Added {
  id : String
  index : Int32
} derive(Eq)

///|
pub extend Added with Eq::{not_equal, equal}

///|
pub(all) struct QueryData {
  ids : Array[String]
  total : Int32
  state : String
  bytes : Int32
} derive(Eq)

///|
pub extend QueryData with Eq::{not_equal, equal}

///|
/// A wire-decoded Email/query result with the account identity retained.
///
/// `QueryData` predates the typed Python wire adapter and remains available
/// for fixture/replay callers.  New transport adapters should use this
/// envelope so an accountId cannot be silently detached from the response.
/// `can_calculate_changes` is the optional RFC `canCalculateChanges` member;
/// `Some(false)` is a valid server answer and makes this query use full query
/// rebuilds instead of queryChanges.
pub(all) struct QueryResponseEnvelope {
  account_id : String
  data : QueryData
  can_calculate_changes : Bool?
} derive(Eq)

///|
pub extend QueryResponseEnvelope with Eq::{not_equal, equal}

///|
pub fn QueryResponseEnvelope::new(
  account_id : String,
  data : QueryData,
  can_calculate_changes : Bool?,
) -> Result[QueryResponseEnvelope, String] {
  if account_id == "" {
    Err("response account_id must be non-empty")
  } else {
    Ok({ account_id, data, can_calculate_changes, })
  }
}

///|
pub(all) struct QueryChangesData {
  removed : Array[String]
  added : Array[Added]
  total : Int32
  old_state : String
  new_state : String
  bytes : Int32
} derive(Eq)

///|
pub extend QueryChangesData with Eq::{not_equal, equal}

///|
/// Account-bound form of Email/queryChanges.  Keeping `old_query_state` and
/// `new_query_state` in `QueryChangesData` lets the core apply the same strict
/// state checks as legacy fixtures while this envelope checks account scope.
pub(all) struct QueryChangesResponseEnvelope {
  account_id : String
  data : QueryChangesData
} derive(Eq)

///|
pub extend QueryChangesResponseEnvelope with Eq::{not_equal, equal}

///|
pub fn QueryChangesResponseEnvelope::new(
  account_id : String,
  data : QueryChangesData,
) -> Result[QueryChangesResponseEnvelope, String] {
  if account_id == "" {
    Err("response account_id must be non-empty")
  } else {
    Ok({ account_id, data, })
  }
}

///|
pub(all) struct GetData {
  list : Array[@email.EmailRecord]
  not_found : Array[String]
  state : String
  bytes : Int32
} derive(Eq)

///|
pub extend GetData with Eq::{not_equal, equal}

///|
/// Account-bound form of Email/get.  The response state is retained in the
/// nested legacy shape so adapters can migrate without rebuilding records.
pub(all) struct GetResponseEnvelope {
  account_id : String
  data : GetData
} derive(Eq)

///|
pub extend GetResponseEnvelope with Eq::{not_equal, equal}

///|
pub fn GetResponseEnvelope::new(
  account_id : String,
  data : GetData,
) -> Result[GetResponseEnvelope, String] {
  if account_id == "" {
    Err("response account_id must be non-empty")
  } else {
    Ok({ account_id, data, })
  }
}

///|
/// RFC 8621 Email/changes retains all three change sets. Created objects can
/// enter a query even if their IDs have never appeared in the cached prefix.
pub(all) struct EmailChangesData {
  created : Array[String]
  updated : Array[String]
  destroyed : Array[String]
  old_state : String
  new_state : String
  has_more_changes : Bool
  bytes : Int32
} derive(Eq)

///|
pub extend EmailChangesData with Eq::{not_equal, equal}

///|
/// Account-bound RFC-shaped form of Email/changes.
pub(all) struct EmailChangesResponseEnvelope {
  account_id : String
  data : EmailChangesData
} derive(Eq)

///|
pub extend EmailChangesResponseEnvelope with Eq::{not_equal, equal}

///|
pub fn EmailChangesResponseEnvelope::new(
  account_id : String,
  data : EmailChangesData,
) -> Result[EmailChangesResponseEnvelope, String] {
  if account_id == "" {
    Err("response account_id must be non-empty")
  } else {
    Ok({ account_id, data, })
  }
}

///|
pub(all) enum ResponseError {
  CannotCalculateChanges
  TooManyChanges
  NotFound
  Unsupported(String)
  Malformed(String)
} derive(Eq)

///|
pub extend ResponseError with Eq::{not_equal, equal}

///|
/// Account-bound server error.  JMAP method errors normally carry an
/// `accountId`; preserving it at the typed boundary prevents an error from a
/// second account being applied to this view.
pub(all) struct ErrorResponseEnvelope {
  account_id : String
  error : ResponseError
} derive(Eq)

///|
pub extend ErrorResponseEnvelope with Eq::{not_equal, equal}

///|
pub fn ErrorResponseEnvelope::new(
  account_id : String,
  error : ResponseError,
) -> Result[ErrorResponseEnvelope, String] {
  if account_id == "" {
    Err("response account_id must be non-empty")
  } else {
    Ok({ account_id, error, })
  }
}

///|
pub(all) enum ServerResponse {
  QueryResult(QueryData)
  QueryChangesResult(QueryChangesData)
  GetResult(GetData)
  EmailChangesResult(EmailChangesData)
  Error(ResponseError)
} derive(Eq)

///|
pub extend ServerResponse with Eq::{not_equal, equal}

///|
/// Typed wire response variants.  The original `ServerResponse` remains the
/// compatibility/replay boundary; this enum is the strict boundary produced
/// by an adapter that decoded accountId and canCalculateChanges.
pub(all) enum BoundServerResponse {
  QueryResult(QueryResponseEnvelope)
  QueryChangesResult(QueryChangesResponseEnvelope)
  GetResult(GetResponseEnvelope)
  EmailChangesResult(EmailChangesResponseEnvelope)
  Error(ErrorResponseEnvelope)
} derive(Eq)

///|
pub extend BoundServerResponse with Eq::{not_equal, equal}

///|
pub(all) struct Checkpoint {
  account : AccountScope
  query : QueryKey
  capabilities : CapabilityProjection
  generation : Int32
  next_request_id : Int32
  ordered_ids : Array[String]
  total : Int32
  objects : Array[@email.EmailRecord]
  email_state : String?
  query_state : String?
  completeness : Completeness
  pending_reason : String?
  pending_ids : Array[String]
  query_required : Bool
  email_required : Bool
  /// Whether the latest typed Email/query response advertised
  /// `canCalculateChanges=true` (or omitted the optional member).
  query_changes_allowed : Bool
  /// Number of Email/changes entries accepted in this generation.
  changes_seen : Int32
} derive(Eq)

///|
pub extend Checkpoint with Eq::{not_equal, equal}

///|
pub(all) struct EmailView {
  account : AccountScope
  query : QueryKey
  capabilities : CapabilityProjection
  limits : Limits
  mut ordered_ids : Array[String]
  mut total : Int32
  mut objects : Array[@email.EmailRecord]
  mut email_state : String?
  mut query_state : String?
  mut email_valid : Bool
  mut query_valid : Bool
  mut completeness : Completeness
  mut generation : Int32
  mut next_request_id : Int32
  mut rounds : Int32
  mut bytes_seen : Int32
  mut query_required : Bool
  mut email_required : Bool
  mut query_fill_required : Bool
  mut query_fill_position : Int32
  mut pending_get : Array[String]
  mut pending_reason : String?
  mut query_changes_allowed : Bool
  mut changes_seen : Int32
} derive(Eq)

///|
pub extend EmailView with Eq::{not_equal, equal}

///|
pub(all) enum OpenViewResult {
  Accepted(EmailView)
  Unsupported(String)
  InvalidInput(String)
} derive(Eq)

///|
pub extend OpenViewResult with Eq::{not_equal, equal}

///|
pub(all) struct ResumableProgress {
  checkpoint : Checkpoint
  pending_ids : Array[String]
  query_required : Bool
  email_required : Bool
} derive(Eq)

///|
pub extend ResumableProgress with Eq::{not_equal, equal}

///|
pub(all) struct RefreshStart {
  view : EmailView
  plan : Plan
} derive(Eq)

///|
pub extend RefreshStart with Eq::{not_equal, equal}

///|
pub(all) struct ContinueResult {
  view : EmailView
  plan : Plan
} derive(Eq)

///|
pub extend ContinueResult with Eq::{not_equal, equal}

///|
pub(all) struct CommitResult {
  view : EmailView
  checkpoint : Checkpoint
} derive(Eq)

///|
pub extend CommitResult with Eq::{not_equal, equal}

///|
pub(all) struct PendingResult {
  view : EmailView
  checkpoint : Checkpoint
  reason : String
} derive(Eq)

///|
pub extend PendingResult with Eq::{not_equal, equal}

///|
pub(all) struct NeedsRefreshResult {
  view : EmailView
  reason : String
  progress : ResumableProgress
} derive(Eq)

///|
pub extend NeedsRefreshResult with Eq::{not_equal, equal}

///|
pub(all) struct ReasonResult {
  view : EmailView
  reason : String
} derive(Eq)

///|
pub extend ReasonResult with Eq::{not_equal, equal}

///|
pub(all) enum Acceptance {
  Continue(ContinueResult)
  Commit(CommitResult)
  Pending(PendingResult)
  NeedsRefresh(NeedsRefreshResult)
  Unsupported(ReasonResult)
  ProtocolFailure(ReasonResult)
  Dropped(ReasonResult)
}

///|
/// Open an empty view. `email_baseline` should be the account's current
/// Email state when the caller already knows it. If it is absent, the first
/// successful `Email/get` response supplies a conservative baseline.
pub fn open_view(
  account : AccountScope,
  view_spec : @email.ViewSpec,
  limits : Limits,
  email_baseline : String?,
) -> EmailView {
  // Preserve the original convenience API for callers that have already
  // accepted the default capability projection.  The strict API below is
  // used when a caller has a real server capability record.
  build_view(
    account,
    view_spec,
    normalize_limits(limits),
    default_capabilities(),
    email_baseline,
  )
}

///|
/// Open a view after checking the caller's capability projection.  The core
/// never performs Session discovery; the caller supplies this small, explicit
/// projection and maps `Unsupported` to its own UI or retry policy.
pub fn open_view_with_capabilities(
  account : AccountScope,
  view_spec : @email.ViewSpec,
  capabilities : CapabilityProjection,
  limits : Limits,
  email_baseline : String?,
) -> OpenViewResult {
  if account.service_identity == "" || account.account_id == "" {
    return InvalidInput("account scope must be non-empty")
  }
  if !view_spec_valid(view_spec) {
    return InvalidInput("mailbox id must be non-empty")
  }
  if limits.prefix_limit <= 0 ||
    limits.max_rounds <= 0 ||
    limits.max_bytes <= 0 ||
    limits.max_objects_per_get <= 0 ||
    limits.max_changes <= 0 {
    return InvalidInput("limits must be positive")
  }
  match capability_error(capabilities) {
    Some(reason) => {
      if reason == "capability limits must be positive" {
        return InvalidInput(reason)
      }
      return Unsupported(reason)
    }
    None => ()
  }
  let effective_limits = {
    prefix_limit: limits.prefix_limit,
    max_rounds: limits.max_rounds,
    max_bytes: limits.max_bytes,
    max_objects_per_get: min_int(
      limits.max_objects_per_get,
      capabilities.max_objects_per_get,
    ),
    max_changes: limits.max_changes,
  }
  Accepted(
    build_view(
      account, view_spec, effective_limits, capabilities, email_baseline,
    ),
  )
}

///|
fn view_spec_valid(view_spec : @email.ViewSpec) -> Bool {
  match view_spec {
    @email.ViewSpec::Latest(mailbox_id) | @email.ViewSpec::Unread(mailbox_id) =>
      mailbox_id != ""
  }
}

///|
fn normalize_limits(limits : Limits) -> Limits {
  // The legacy convenience wrapper cannot return InvalidInput, so retain its
  // historical safe fallback. Strict callers should use
  // open_view_with_capabilities instead.
  {
    prefix_limit: if limits.prefix_limit > 0 {
      limits.prefix_limit
    } else {
      1
    },
    max_rounds: if limits.max_rounds > 0 {
      limits.max_rounds
    } else {
      1
    },
    max_bytes: if limits.max_bytes > 0 {
      limits.max_bytes
    } else {
      1
    },
    max_objects_per_get: if limits.max_objects_per_get > 0 {
      limits.max_objects_per_get
    } else {
      1
    },
    max_changes: if limits.max_changes > 0 {
      limits.max_changes
    } else {
      1
    },
  }
}

///|
fn build_view(
  account : AccountScope,
  view_spec : @email.ViewSpec,
  safe_limits : Limits,
  capabilities : CapabilityProjection,
  email_baseline : String?,
) -> EmailView {
  let query = { account, view: view_spec, collapse_threads: false, }
  let email_valid = email_baseline is Some(_)
  {
    account,
    query,
    capabilities,
    limits: safe_limits,
    ordered_ids: [],
    total: 0,
    objects: [],
    email_state: email_baseline,
    query_state: None,
    email_valid,
    query_valid: false,
    completeness: Pending,
    generation: 0,
    next_request_id: 1,
    rounds: 0,
    bytes_seen: 0,
    query_required: true,
    email_required: email_valid,
    query_fill_required: false,
    query_fill_position: 0,
    pending_get: [],
    pending_reason: None,
    query_changes_allowed: true,
    changes_seen: 0,
  }
}

///|
pub fn checkpoint(view : EmailView) -> Checkpoint {
  let query_required = view.query_required || view.query_fill_required
  {
    account: view.account,
    query: view.query,
    capabilities: view.capabilities,
    generation: view.generation,
    next_request_id: view.next_request_id,
    ordered_ids: view.ordered_ids.copy(),
    total: view.total,
    objects: view.objects.copy(),
    email_state: view.email_state,
    // A query token is not reusable after query history invalidation (or a
    // `notFound` response that explicitly invalidates the cached ordering).
    // Keep the stale value on the in-memory view for diagnostics, but never
    // persist it as if it were a resumable query baseline.  A valid token that
    // is merely awaiting reconciliation remains persisted and can still be
    // used by a caller that continues the same view directly.
    query_state: if query_required && !view.query_valid {
      None
    } else {
      view.query_state
    },
    completeness: view.completeness,
    pending_reason: view.pending_reason,
    pending_ids: view.pending_get.copy(),
    query_required,
    email_required: view.email_required,
    query_changes_allowed: view.query_changes_allowed,
    changes_seen: view.changes_seen,
  }
}

///|
/// Validate and restore a persisted checkpoint without treating a stale or
/// failed token as a usable view. The caller still owns durable storage; this
/// function only performs structural/context checks before planning resumes.
pub fn restore_checkpoint(
  saved : Checkpoint,
  limits : Limits,
) -> Result[EmailView, String] {
  if saved.generation < 0 || saved.next_request_id <= 0 || saved.total < 0 {
    return Err("checkpoint has a negative generation or total")
  }
  if saved.changes_seen < 0 || saved.changes_seen > limits.max_changes {
    return Err("checkpoint Email/changes count exceeds the supplied budget")
  }
  if saved.account.service_identity == "" || saved.account.account_id == "" {
    return Err("checkpoint account scope must be non-empty")
  }
  if !view_spec_valid(saved.query.view) {
    return Err("checkpoint view mailbox id must be non-empty")
  }
  if saved.query.collapse_threads {
    return Err("checkpoint collapseThreads must be false")
  }
  if limits.prefix_limit <= 0 ||
    limits.max_rounds <= 0 ||
    limits.max_bytes <= 0 ||
    limits.max_objects_per_get <= 0 ||
    limits.max_changes <= 0 {
    return Err("limits must be positive when restoring a checkpoint")
  }
  if saved.query.account != saved.account {
    return Err("checkpoint query is bound to another account")
  }
  match capability_error(saved.capabilities) {
    Some(reason) =>
      return Err("checkpoint capabilities are unusable: " + reason)
    None => ()
  }
  if saved.ordered_ids.length() > limits.prefix_limit ||
    saved.ordered_ids.length() > saved.total ||
    !unique_nonempty(saved.ordered_ids) {
    return Err("checkpoint ordered prefix is invalid")
  }
  if !unique(saved.objects.map(fn(record) { record.id })) {
    return Err("checkpoint contains duplicate objects")
  }
  for record in saved.objects {
    if record.id == "" {
      return Err("checkpoint contains an object with an empty id")
    }
    if !contains_string(saved.ordered_ids, record.id) {
      return Err("checkpoint contains an object outside its ordered prefix")
    }
  }
  if !unique_nonempty(saved.pending_ids) {
    return Err("checkpoint pending ids are duplicated")
  }
  for id in saved.pending_ids {
    if !contains_string(saved.ordered_ids, id) {
      return Err("checkpoint pending id is outside its ordered prefix")
    }
  }
  // A checkpoint that claims no query work remains must carry a queryState;
  // otherwise restore would turn a short prefix into a fill request whose
  // expected state is `None`, which can never be accepted safely.  The
  // converse (query work required with no token) is valid and represents a
  // fresh query or an invalidated query history.
  if !saved.query_required && saved.query_state is None {
    return Err("checkpoint has no queryState while query work is not required")
  }
  // An empty Email baseline is valid only while the query/bootstrap work is
  // still outstanding.  Once query work is complete, a checkpoint without an
  // Email state cannot establish the object progress needed for a later get.
  if !saved.email_required &&
    saved.email_state is None &&
    !saved.query_required &&
    saved.completeness != NeedsRefresh {
    return Err("checkpoint has no Email state while Email work is not required")
  }
  match saved.completeness {
    Unsupported | ProtocolFailure =>
      return Err("unsupported or protocol-failed checkpoint is not resumable")
    Ready => {
      if saved.query_state is None ||
        saved.email_state is None ||
        saved.query_required ||
        saved.email_required ||
        saved.pending_ids.length() > 0 {
        return Err("Ready checkpoint does not contain complete progress")
      }
      // A persisted checkpoint is an input boundary too: do not trust a
      // caller-supplied Ready marker when one of the cached objects is only
      // an ID-shaped or otherwise incomplete projection.
      for id in saved.ordered_ids {
        if !has_complete_record(saved.objects, id) {
          return Err("Ready checkpoint contains an incomplete object")
        }
      }
      for record in saved.objects {
        if !saved.query.view.matches_record(record) {
          return Err("Ready checkpoint contradicts its mailbox/unread view")
        }
      }
    }
    Pending | NeedsRefresh => ()
  }
  // The checkpoint builder omits a token when its history is invalid.  A
  // present token therefore remains a valid baseline even when work is still
  // required to reconcile it (for example queryChanges after an Email
  // history reset or a paginated Email/changes feed).
  let query_valid = saved.query_state is Some(_)
  let email_valid = saved.email_state is Some(_)
  let effective_limits = {
    prefix_limit: limits.prefix_limit,
    max_rounds: limits.max_rounds,
    max_bytes: limits.max_bytes,
    max_objects_per_get: min_int(
      limits.max_objects_per_get,
      saved.capabilities.max_objects_per_get,
    ),
    max_changes: limits.max_changes,
  }
  let restored : EmailView = {
    account: saved.account,
    query: saved.query,
    capabilities: saved.capabilities,
    limits: effective_limits,
    ordered_ids: saved.ordered_ids.copy(),
    total: saved.total,
    objects: saved.objects.copy(),
    email_state: saved.email_state,
    query_state: saved.query_state,
    email_valid,
    query_valid,
    completeness: saved.completeness,
    generation: saved.generation,
    next_request_id: saved.next_request_id,
    rounds: 0,
    bytes_seen: 0,
    query_required: saved.query_required,
    email_required: saved.email_required,
    query_fill_required: saved.ordered_ids.length() <
    min_int(effective_limits.prefix_limit, saved.total) &&
    !saved.query_required,
    query_fill_position: saved.ordered_ids.length(),
    pending_get: saved.pending_ids.copy(),
    pending_reason: saved.pending_reason,
    query_changes_allowed: saved.query_changes_allowed,
    changes_seen: saved.changes_seen,
  }
  // A budget can be exhausted by the final response itself.  Such a
  // checkpoint is persisted as Pending even though all semantic work is
  // complete.  Restoring with a larger budget must make that state
  // committable instead of returning a no-op Pending view with no plan.
  if saved.completeness == Pending && ready(restored) {
    restored.completeness = Ready
  }
  Ok(restored)
}

///|
pub fn resumable(view : EmailView) -> ResumableProgress {
  {
    checkpoint: checkpoint(view),
    pending_ids: view.pending_get.copy(),
    query_required: view.query_required || view.query_fill_required,
    email_required: view.email_required,
  }
}

///|
/// Return display records in the server's query order only after the fixed
/// mailbox window is Ready. Pending/invalidated cache entries are never a
/// readable mail snapshot. Copy nested collections so UI changes cannot
/// mutate a subsequent checkpoint through the returned values.
pub fn committed_emails(
  view : EmailView,
) -> Result[Array[@email.EmailRecord], String] {
  if view.completeness != Ready || !ready(view) {
    return Err("mailbox prefix is not Ready for display")
  }
  let records : Array[@email.EmailRecord] = []
  for id in view.ordered_ids {
    for record in view.objects {
      if record.id == id {
        records.push({
          ..record,
          mailbox_ids: record.mailbox_ids.map(fn(entries) { entries.copy() }),
          keywords: record.keywords.map(fn(entries) { entries.copy() }),
          from: record.from.map(fn(entries) { entries.copy() }),
        })
      }
    }
  }
  Ok(records)
}

///|
/// Begin or continue work. Plans contain one call at a time; this keeps the
/// acceptance boundary explicit and prevents a caller from accidentally
/// using a ResultReference across a `maxCallsInRequest=1` transport.
pub fn plan(view : EmailView) -> Plan {
  let next = view
  next.completeness = Pending
  make_next_plan(next)
}

// Refresh and resume start a new request generation.  Build a detached view
// before mutating it so the caller can still retain the previous view for
// stale-response checks; assigning a mutable struct directly would alias the
// original view and advance its generation in place.

///|
fn detached_view(view : EmailView) -> EmailView {
  {
    ..view,
    ordered_ids: view.ordered_ids.copy(),
    objects: view.objects.copy(),
    pending_get: view.pending_get.copy(),
  }
}

///|
pub fn refresh(view : EmailView) -> RefreshStart {
  begin_refresh(view)
}

///|
/// Increment a request generation without allowing a signed `Int` to wrap.
///
/// MoonBit's `Int` is the 32-bit `@int` type on every target supported by this
/// package. Arithmetic wraps at the type boundary, so `generation + 1` is not
/// a safe way to create a new stale-response fence. Keep this check in one
/// small, public helper so durable-checkpoint callers can validate a restored
/// generation before asking for a new plan.
pub fn checked_next_generation(generation : Int32) -> Result[Int32, String] {
  if generation < 0 {
    Err("generation must be non-negative")
  } else if generation == @int.MAX_VALUE {
    Err("generation overflow: maximum generation reached")
  } else {
    Ok(generation + 1)
  }
}

///|
/// Build a refresh using a checked generation transition. The old
/// `begin_refresh` API remains available for compatibility; callers that need
/// an explicit, typed failure boundary should use this function.
pub fn begin_refresh_checked(
  view : EmailView,
) -> Result[RefreshStart, ReasonResult] {
  match checked_next_generation(view.generation) {
    Ok(next_generation) => Ok(build_refresh_start(view, next_generation))
    Err(reason) => Err(generation_failure(view, reason))
  }
}

///|
/// Start a refresh while retaining the incremented generation together with
/// its plan. Callers must feed the returned `view` into `accept_response`; the
/// old view intentionally cannot accept responses from this generation.
pub fn begin_refresh(view : EmailView) -> RefreshStart {
  match checked_next_generation(view.generation) {
    Ok(next_generation) => build_refresh_start(view, next_generation)
    Err(reason) => failed_refresh_start(view, reason)
  }
}

///|
fn build_refresh_start(
  view : EmailView,
  next_generation : Int32,
) -> RefreshStart {
  let next = detached_view(view)
  next.generation = next_generation
  next.rounds = 0
  next.bytes_seen = 0
  next.completeness = Pending
  next.query_required = true
  next.email_required = true
  next.query_fill_required = false
  next.query_fill_position = 0
  next.pending_get = []
  next.pending_reason = None
  next.changes_seen = 0
  { view: next, plan: make_next_plan(next), }
}

///|
/// Resume after an invalid Email history with a fresh account state supplied
/// by the caller. The old token is never reused; query progress is retained.
pub fn resume_with_email_state(
  view : EmailView,
  state : String,
) -> RefreshStart {
  begin_resume_with_email_state(view, state)
}

///|
/// Variant of `resume_with_email_state` that returns the new generation along
/// with its first plan, so stale responses cannot be accidentally accepted.
pub fn begin_resume_with_email_state(
  view : EmailView,
  state : String,
) -> RefreshStart {
  match checked_next_generation(view.generation) {
    Ok(next_generation) => build_resume_start(view, state, next_generation)
    Err(reason) => failed_refresh_start(view, reason)
  }
}

///|
/// Resume with a checked generation transition. The `Err` branch contains a
/// protocol-failed detached view, preserving the old view for stale-response
/// diagnostics and durable logging.
pub fn begin_resume_with_email_state_checked(
  view : EmailView,
  state : String,
) -> Result[RefreshStart, ReasonResult] {
  match checked_next_generation(view.generation) {
    Ok(next_generation) => Ok(build_resume_start(view, state, next_generation))
    Err(reason) => Err(generation_failure(view, reason))
  }
}

///|
fn build_resume_start(
  view : EmailView,
  state : String,
  next_generation : Int32,
) -> RefreshStart {
  let next = detached_view(view)
  next.generation = next_generation
  next.rounds = 0
  next.bytes_seen = 0
  next.email_state = Some(state)
  next.email_valid = false
  next.email_required = false
  next.completeness = Pending
  // A queryState that survived an Email history failure is still usable, but
  // it must be reconciled after the fresh Email baseline is installed. If it
  // was already invalid, rebuild it; otherwise queryChanges checks whether a
  // changed sort/filter membership invalidates the retained prefix before
  // object projections are committed.
  next.query_required = !view.query_valid || view.query_required
  next.query_valid = view.query_valid
  next.query_fill_required = false
  next.pending_get = if view.query_valid { view.ordered_ids.copy() } else { [] }
  next.pending_reason = None
  next.changes_seen = 0
  { view: next, plan: make_next_plan(next), }
}

///|
fn generation_failure(view : EmailView, reason : String) -> ReasonResult {
  let next = detached_view(view)
  next.completeness = ProtocolFailure
  next.pending_reason = Some(reason)
  { view: next, reason, }
}

// The compatibility APIs return a RefreshStart rather than a Result. They
// therefore surface the same checked failure through a protocol-failed view
// and an empty plan, never by wrapping generation back to a stale value.

///|
fn failed_refresh_start(view : EmailView, reason : String) -> RefreshStart {
  let failed = generation_failure(view, reason)
  {
    view: failed.view,
    plan: {
      generation: failed.view.generation,
      reason: failed.reason,
      requests: [],
    },
  }
}

///|
fn make_next_plan(view : EmailView) -> Plan {
  let working = view
  let request = make_next_request(working)
  match request {
    Some(request) =>
      {
        generation: working.generation,
        reason: request_reason(request.kind),
        requests: [request],
      }
    None => { generation: working.generation, reason: "no work", requests: [], }
  }
}

///|
fn request_reason(kind : RequestKind) -> String {
  match kind {
    Query => "rebuild query prefix"
    QueryChanges => "追赶查询顺序变化"
    Get => "取得窗口邮件属性"
    Changes => "追赶 Email 对象变化"
  }
}

///|
fn make_ticket(
  view : EmailView,
  kind : RequestKind,
  ids : Array[String],
  position : Int32,
  limit : Int32,
) -> RequestTicket {
  {
    generation: view.generation,
    request_id: view.next_request_id,
    account: view.account,
    query: view.query,
    kind,
    expected_query_state: view.query_state,
    expected_email_state: view.email_state,
    requested_ids: ids,
    position,
    limit,
    max_changes: if kind == Changes {
      remaining_changes(view)
    } else {
      0
    },
  }
}

///|
fn remaining_changes(view : EmailView) -> Int32 {
  let remaining = view.limits.max_changes - view.changes_seen
  if remaining > 0 {
    remaining
  } else {
    0
  }
}

///|
fn make_next_request(view : EmailView) -> Request? {
  // When both chains are due, drain Email/changes first. Its final state is
  // the object baseline for the subsequent queryChanges pass; doing the
  // reverse can publish ordering based on an older object state.
  // A query that explicitly advertised `canCalculateChanges=false` is the
  // exception: it has no legal queryChanges request at all, so rebuild the
  // query before any optional Email/changes work. This keeps the typed wire
  // capability from being accidentally bypassed by the ordering rule above.
  if view.query_required && !view.query_changes_allowed {
    let ticket = make_ticket(view, Query, [], 0, view.limits.prefix_limit)
    Some({
      ticket,
      kind: Query,
      ids: [],
      position: 0,
      limit: view.limits.prefix_limit,
      max_changes: 0,
      filter: Some(view.query.view.filter_spec()),
      sort: Some(view.query.view.sort_spec()),
      properties: @email.default_properties(),
    })
  } else if view.email_required && view.query_valid && view.email_state is None {
    // An invalid Email history needs a fresh account baseline before the
    // retained queryState can be reconciled.  This is also the bootstrap
    // path for a view opened without an Email state.
    let ticket = make_ticket(view, Get, [], 0, 0)
    Some({
      ticket,
      kind: Get,
      ids: [],
      position: 0,
      limit: 0,
      max_changes: 0,
      filter: None,
      sort: None,
      properties: @email.default_properties(),
    })
  } else if view.email_required &&
    view.query_valid &&
    view.email_state is Some(_) &&
    remaining_changes(view) > 0 {
    let change_limit = remaining_changes(view)
    let ticket = make_ticket(view, Changes, [], 0, change_limit)
    Some({
      ticket,
      kind: Changes,
      ids: [],
      position: 0,
      limit: change_limit,
      max_changes: change_limit,
      filter: None,
      sort: None,
      properties: @email.default_properties(),
    })
  } else if view.email_required && remaining_changes(view) <= 0 {
    // Do not advance the query chain while Email/changes still has an
    // unconsumed page sequence but its cumulative budget is exhausted.
    None
  } else if view.query_required {
    let kind = if view.query_state is Some(_) &&
      view.query_valid &&
      view.query_changes_allowed {
      QueryChanges
    } else {
      Query
    }
    let ticket = make_ticket(view, kind, [], 0, view.limits.prefix_limit)
    Some({
      ticket,
      kind,
      ids: [],
      position: 0,
      limit: view.limits.prefix_limit,
      max_changes: 0,
      filter: Some(view.query.view.filter_spec()),
      sort: Some(view.query.view.sort_spec()),
      properties: @email.default_properties(),
    })
  } else if view.query_fill_required {
    let missing = view.limits.prefix_limit - view.ordered_ids.length()
    if missing <= 0 || view.ordered_ids.length() >= view.total {
      None
    } else {
      let ticket = make_ticket(
        view,
        Query,
        [],
        view.query_fill_position,
        min_int(missing, view.limits.prefix_limit),
      )
      Some({
        ticket,
        kind: Query,
        ids: [],
        position: view.query_fill_position,
        limit: min_int(missing, view.limits.prefix_limit),
        max_changes: 0,
        filter: Some(view.query.view.filter_spec()),
        sort: Some(view.query.view.sort_spec()),
        properties: @email.default_properties(),
      })
    }
  } else if view.email_required {
    match view.email_state {
      Some(_) => {
        if remaining_changes(view) <= 0 {
          return None
        }
        let change_limit = remaining_changes(view)
        let ticket = make_ticket(view, Changes, [], 0, change_limit)
        Some({
          ticket,
          kind: Changes,
          ids: [],
          position: 0,
          limit: change_limit,
          max_changes: change_limit,
          filter: None,
          sort: None,
          properties: @email.default_properties(),
        })
      }
      None =>
        // Email/get with an empty id set still returns the account's current
        // Email state. It establishes a baseline without pretending that an
        // empty query means there are no object changes.
        if view.query_valid {
          let ticket = make_ticket(view, Get, [], 0, 0)
          Some({
            ticket,
            kind: Get,
            ids: [],
            position: 0,
            limit: 0,
            max_changes: 0,
            filter: None,
            sort: None,
            properties: @email.default_properties(),
          })
        } else {
          None
        }
    }
  } else if view.pending_get.length() > 0 {
    let count = min_int(
      view.pending_get.length(),
      view.limits.max_objects_per_get,
    )
    let ids = prefix_strings(view.pending_get, count)
    let ticket = make_ticket(view, Get, ids, 0, count)
    Some({
      ticket,
      kind: Get,
      ids,
      position: 0,
      limit: count,
      max_changes: 0,
      filter: None,
      sort: None,
      properties: @email.default_properties(),
    })
  } else {
    None
  }
}

///|
fn min_int(left : Int32, right : Int32) -> Int32 {
  if left < right {
    left
  } else {
    right
  }
}

///|
fn prefix_strings(values : Array[String], count : Int32) -> Array[String] {
  Array::from_iter(values.iter().take(count))
}

///|
fn target_length(view : EmailView) -> Int32 {
  min_int(view.limits.prefix_limit, view.total)
}

///|
fn contains_string(values : Array[String], wanted : String) -> Bool {
  values.contains(wanted)
}

///|
fn remove_string(values : Array[String], wanted : String) -> Array[String] {
  values.filter(fn(value) { value != wanted })
}

///|
fn remove_strings(
  values : Array[String],
  unwanted : Array[String],
) -> Array[String] {
  values.filter(fn(value) { !contains_string(unwanted, value) })
}

///|
fn missing_object_ids(view : EmailView) -> Array[String] {
  let result : Array[String] = []
  for id in view.ordered_ids {
    // Presence of an ID alone is insufficient for a Ready checkpoint.  The
    // fixed presentation projection has required fields (mailbox/keyword
    // maps, thread and display properties) that must survive decoding.  An
    // incomplete record remains a fetch obligation so a malformed or partial
    // Email/get response cannot be published as if it were complete.
    let complete = has_complete_object(view, id)
    if !complete && !contains_string(result, id) {
      result.push(id)
    }
  }
  result
}

///|
fn has_complete_object(view : EmailView, id : String) -> Bool {
  has_complete_record(view.objects, id)
}

///|
fn has_complete_record(
  records : Array[@email.EmailRecord],
  id : String,
) -> Bool {
  for record in records {
    if record.id == id && record.is_complete() {
      return true
    }
  }
  false
}

///|
fn has_full_prefix(view : EmailView) -> Bool {
  view.ordered_ids.length() >= target_length(view)
}

///|
fn ready_progress(view : EmailView) -> Bool {
  view.query_valid &&
  view.email_valid &&
  !view.query_required &&
  !view.query_fill_required &&
  !view.email_required &&
  view.pending_get.length() == 0 &&
  has_full_prefix(view) &&
  missing_object_ids(view).length() == 0
}

///|
fn prefix_matches_view(view : EmailView) -> Bool {
  view.objects.all(fn(record) {
    !view.ordered_ids.contains(record.id) ||
    view.query.view.matches_record(record)
  })
}

///|
fn ready(view : EmailView) -> Bool {
  ready_progress(view) && prefix_matches_view(view)
}

///|
fn finish_or_continue(view : EmailView) -> Acceptance {
  let next = view
  let missing = missing_object_ids(next)
  for id in missing {
    if !contains_string(next.pending_get, id) {
      next.pending_get.push(id)
    }
  }
  if next.ordered_ids.length() < target_length(next) {
    next.query_fill_required = true
    next.query_fill_position = next.ordered_ids.length()
  } else {
    next.query_fill_required = false
  }
  // A response that consumes the final round/byte budget is resumable but
  // must not be published as Ready.  Check the limits before completeness so
  // callers can explicitly decide whether to continue with a larger budget.
  if next.rounds >= next.limits.max_rounds {
    next.completeness = Pending
    next.pending_reason = Some("round budget exhausted")
    Pending(PendingResult::{
      view: next,
      checkpoint: checkpoint(next),
      reason: "round budget exhausted",
    })
  } else if next.bytes_seen >= next.limits.max_bytes {
    next.completeness = Pending
    next.pending_reason = Some("byte budget exhausted")
    Pending(PendingResult::{
      view: next,
      checkpoint: checkpoint(next),
      reason: "byte budget exhausted",
    })
  } else if next.email_required && next.changes_seen >= next.limits.max_changes {
    next.completeness = Pending
    next.pending_reason = Some("Email/changes budget exhausted")
    Pending(PendingResult::{
      view: next,
      checkpoint: checkpoint(next),
      reason: "Email/changes budget exhausted",
    })
  } else if ready_progress(next) {
    if !prefix_matches_view(next) {
      needs_refresh(
        next, "Email/get projection contradicts its mailbox/unread query",
      )
    } else {
      next.completeness = Ready
      Commit(CommitResult::{ view: next, checkpoint: checkpoint(next), })
    }
  } else {
    next.completeness = Pending
    let next_plan = make_next_plan(next)
    if next_plan.requests.length() == 0 {
      next.pending_reason = Some("email baseline required")
      Pending(PendingResult::{
        view: next,
        checkpoint: checkpoint(next),
        reason: "email baseline required",
      })
    } else {
      Continue(ContinueResult::{ view: next, plan: next_plan, })
    }
  }
}

///|
fn protocol_failure(view : EmailView, reason : String) -> Acceptance {
  let next = view
  next.completeness = ProtocolFailure
  next.pending_reason = Some(reason)
  ProtocolFailure(ReasonResult::{ view: next, reason, })
}

///|
fn unsupported(view : EmailView, reason : String) -> Acceptance {
  let next = view
  next.completeness = Unsupported
  next.pending_reason = Some(reason)
  Unsupported(ReasonResult::{ view: next, reason, })
}

///|
fn needs_refresh(view : EmailView, reason : String) -> Acceptance {
  let next = view
  next.completeness = NeedsRefresh
  next.query_required = true
  next.query_valid = false
  // Keep the old value only on the transient in-memory view for diagnostics;
  // it is not a reusable baseline after query history invalidation.  The
  // checkpoint builder also defensively omits any stale value it receives.
  next.query_state = None
  next.query_fill_required = false
  next.pending_reason = Some(reason)
  NeedsRefresh(NeedsRefreshResult::{
    view: next,
    reason,
    progress: resumable(next),
  })
}

///|
fn email_history_invalid(view : EmailView, reason : String) -> Acceptance {
  let next = view
  next.completeness = NeedsRefresh
  next.email_valid = false
  // The old Email token can no longer be used to describe the cached
  // objects.  Keep an explicit baseline request outstanding so callers that
  // continue the returned view (or restore its checkpoint) do not get a
  // misleading `no work` plan when every cached object happens to look
  // complete.  The empty Email/get establishes a fresh state first; the
  // pending IDs below then force the bounded prefix to be re-fetched against
  // that baseline.
  next.email_required = true
  next.email_state = None
  next.pending_get = next.ordered_ids.copy()
  // Keep a valid queryState for the independent queryChanges reconciliation;
  // otherwise an Email-history reset could re-fetch stale objects and publish
  // the old ordering without checking membership or sort changes.
  if next.query_valid {
    next.query_required = true
  }
  // Keep query progress reusable, but never advance the invalid Email token.
  next.pending_reason = Some(reason)
  NeedsRefresh(NeedsRefreshResult::{
    view: next,
    reason,
    progress: resumable(next),
  })
}

///|
fn validate_ticket(
  view : EmailView,
  ticket : RequestTicket,
  expected : RequestKind,
) -> String? {
  if view.completeness == ProtocolFailure {
    Some("view is already protocol-failed")
  } else if ticket.request_id <= 0 {
    Some("request ticket has no positive request id")
  } else if ticket.generation != view.generation {
    Some("late response from an older request generation")
  } else if ticket.request_id != view.next_request_id {
    Some("response request id is not the currently outstanding request")
  } else if ticket.account != view.account || ticket.query != view.query {
    Some("response ticket belongs to another account or query")
  } else if ticket.kind != expected {
    Some("response method does not match request ticket")
  } else if ticket.expected_query_state != view.query_state ||
    ticket.expected_email_state != view.email_state {
    Some("response ticket state baseline does not match the current view")
  } else if !ticket_shape_valid(view, ticket, expected) {
    Some("response ticket payload does not match the current plan")
  } else {
    None
  }
}

///|
/// RequestTicket is public so a caller can persist or transport it, but a
/// response must still prove that its payload is the one emitted by the
/// current view. Without these checks a forged ticket could reuse a request
/// id while changing Email/get IDs or a state baseline.
fn ticket_shape_valid(
  view : EmailView,
  ticket : RequestTicket,
  expected : RequestKind,
) -> Bool {
  match expected {
    Query =>
      if ticket.max_changes != 0 ||
        ticket.requested_ids.length() != 0 ||
        ticket.limit <= 0 {
        false
      } else if view.query_fill_required {
        let missing = view.limits.prefix_limit - view.ordered_ids.length()
        ticket.position == view.query_fill_position &&
        ticket.limit == min_int(missing, view.limits.prefix_limit)
      } else {
        ticket.position == 0 && ticket.limit == view.limits.prefix_limit
      }
    QueryChanges =>
      ticket.requested_ids.length() == 0 &&
      ticket.position == 0 &&
      ticket.limit == view.limits.prefix_limit &&
      ticket.max_changes == 0
    Changes =>
      ticket.requested_ids.length() == 0 &&
      ticket.position == 0 &&
      ticket.limit > 0 &&
      ticket.max_changes == ticket.limit &&
      ticket.limit == remaining_changes(view)
    Get =>
      if ticket.max_changes != 0 || ticket.position != 0 {
        false
      } else if ticket.requested_ids.length() == 0 {
        // The only empty Email/get emitted by this planner establishes an
        // account baseline when no Email state is known yet.
        view.email_state is None &&
        view.query_valid &&
        view.email_required &&
        ticket.limit == 0
      } else {
        let count = min_int(
          view.pending_get.length(),
          view.limits.max_objects_per_get,
        )
        let expected_ids = prefix_strings(view.pending_get, count)
        ticket.requested_ids == expected_ids && ticket.limit == count
      }
  }
}

///|
fn dropped(view : EmailView, reason : String) -> Acceptance {
  Dropped(ReasonResult::{ view, reason, })
}

///|
/// Apply one decoded response. A response with an old generation is dropped
/// and never mutates the current view, which is the key stale-response guard.
pub fn accept_response(
  view : EmailView,
  ticket : RequestTicket,
  response : ServerResponse,
) -> Acceptance {
  match response {
    Error(error) =>
      match validate_ticket(view, ticket, ticket.kind) {
        Some(reason) =>
          if ticket.generation != view.generation {
            dropped(view, reason)
          } else {
            protocol_failure(view, reason)
          }
        None => accept_error(view, ticket, error)
      }
    QueryResult(data) =>
      match validate_ticket(view, ticket, Query) {
        Some(reason) =>
          if ticket.generation != view.generation {
            dropped(view, reason)
          } else {
            protocol_failure(view, reason)
          }
        None => accept_query(view, ticket, data)
      }
    QueryChangesResult(data) =>
      match validate_ticket(view, ticket, QueryChanges) {
        Some(reason) =>
          if ticket.generation != view.generation {
            dropped(view, reason)
          } else {
            protocol_failure(view, reason)
          }
        None => accept_query_changes(view, ticket, data)
      }
    GetResult(data) =>
      match validate_ticket(view, ticket, Get) {
        Some(reason) =>
          if ticket.generation != view.generation {
            dropped(view, reason)
          } else {
            protocol_failure(view, reason)
          }
        None => accept_get(view, ticket, data)
      }
    EmailChangesResult(data) =>
      match validate_ticket(view, ticket, Changes) {
        Some(reason) =>
          if ticket.generation != view.generation {
            dropped(view, reason)
          } else {
            protocol_failure(view, reason)
          }
        None => accept_email_changes(view, ticket, data)
      }
  }
}

///|
fn bound_account_error(view : EmailView, account_id : String) -> String? {
  if account_id == "" {
    Some("typed response accountId is empty")
  } else if account_id != view.account.account_id {
    Some("typed response accountId does not match the current account")
  } else {
    None
  }
}

///|
fn bound_rejection(
  view : EmailView,
  ticket : RequestTicket,
  reason : String,
) -> Acceptance {
  if ticket.generation != view.generation {
    dropped(view, "late typed response from an older request generation")
  } else {
    protocol_failure(view, reason)
  }
}

///|
fn accept_bound_query(
  view : EmailView,
  ticket : RequestTicket,
  envelope : QueryResponseEnvelope,
) -> Acceptance {
  // Do not record canCalculateChanges until the ticket itself is accepted.
  // A malformed or replayed response must not be able to downgrade the
  // current query planner as a side effect of returning ProtocolFailure.
  match validate_ticket(view, ticket, Query) {
    Some(reason) =>
      if ticket.generation != view.generation {
        dropped(view, reason)
      } else {
        protocol_failure(view, reason)
      }
    None => {
      match response_counter_error(view, ticket, envelope.data.bytes, true) {
        Some(reason) => return protocol_failure(view, reason)
        None => ()
      }
      if envelope.data.state == "" {
        return protocol_failure(view, "query state token must be non-empty")
      }
      match response_budget_pending(view) {
        Some(pending) => return pending
        None => ()
      }
      let next = view
      next.query_changes_allowed = envelope.can_calculate_changes.unwrap_or(
        true,
      )
      accept_query(next, ticket, envelope.data)
    }
  }
}

///|
/// Apply a response that crossed the strict typed adapter boundary.
///
/// The legacy `accept_response` API remains available for existing replay
/// fixtures. A production wire adapter should call this entry point: it
/// proves that every response belongs to the current account before
/// delegating to the ticket/generation/state checks. The optional
/// Email/query `canCalculateChanges` flag is retained as a per-query
/// capability. When false, subsequent refreshes use a full Email/query
/// rebuild instead of sending an invalid Email/queryChanges request.
pub fn accept_bound_response(
  view : EmailView,
  ticket : RequestTicket,
  response : BoundServerResponse,
) -> Acceptance {
  match response {
    BoundServerResponse::QueryResult(envelope) =>
      match bound_account_error(view, envelope.account_id) {
        Some(reason) => bound_rejection(view, ticket, reason)
        None => accept_bound_query(view, ticket, envelope)
      }
    BoundServerResponse::QueryChangesResult(envelope) =>
      match bound_account_error(view, envelope.account_id) {
        Some(reason) => bound_rejection(view, ticket, reason)
        None =>
          accept_response(
            view,
            ticket,
            ServerResponse::QueryChangesResult(envelope.data),
          )
      }
    BoundServerResponse::GetResult(envelope) =>
      match bound_account_error(view, envelope.account_id) {
        Some(reason) => bound_rejection(view, ticket, reason)
        None =>
          accept_response(
            view,
            ticket,
            ServerResponse::GetResult(envelope.data),
          )
      }
    BoundServerResponse::EmailChangesResult(envelope) =>
      match bound_account_error(view, envelope.account_id) {
        Some(reason) => bound_rejection(view, ticket, reason)
        None =>
          accept_response(
            view,
            ticket,
            ServerResponse::EmailChangesResult(envelope.data),
          )
      }
    BoundServerResponse::Error(envelope) =>
      match bound_account_error(view, envelope.account_id) {
        Some(reason) => bound_rejection(view, ticket, reason)
        None =>
          accept_response(view, ticket, ServerResponse::Error(envelope.error))
      }
  }
}

///|
/// Remove IDs that were destroyed from the follow-up object-fetch queue. A
/// server may legally report one ID in both `updated` and `destroyed`; the
/// destruction wins and the synchronizer must not schedule an Email/get for a
/// record which no longer exists. The query itself remains responsible for
/// removing the stale ID from the ordered prefix.
fn clear_destroyed_pending(
  result : Acceptance,
  destroyed : Array[String],
) -> Acceptance {
  match result {
    Continue(next) => {
      let view = next.view
      view.pending_get = remove_strings(view.pending_get, destroyed)
      // The plan was built before destruction won over an overlapping
      // update. Rebuild it so a stale Email/get request cannot escape in the
      // returned continuation.
      let plan = make_next_plan(view)
      Continue({ view, plan, })
    }
    Commit(next) => {
      let pending = remove_strings(next.view.pending_get, destroyed)
      next.view.pending_get = pending
      let checkpoint = { ..next.checkpoint, pending_ids: pending, }
      Commit({ ..next, checkpoint, })
    }
    Pending(next) => {
      let pending = remove_strings(next.view.pending_get, destroyed)
      next.view.pending_get = pending
      let checkpoint = { ..next.checkpoint, pending_ids: pending, }
      Pending({ ..next, checkpoint, })
    }
    NeedsRefresh(next) => {
      let pending = remove_strings(next.view.pending_get, destroyed)
      next.view.pending_get = pending
      let checkpoint = { ..next.progress.checkpoint, pending_ids: pending, }
      let progress = { ..next.progress, pending_ids: pending, checkpoint, }
      NeedsRefresh({ ..next, progress, })
    }
    Unsupported(next) => Unsupported(next)
    ProtocolFailure(next) => ProtocolFailure(next)
    Dropped(next) => Dropped(next)
  }
}

///|
/// Reject arithmetic that would wrap before any response state is changed.
/// Budget exhaustion remains resumable Pending; an unrepresentable counter
/// is a protocol failure rather than a silently reset budget.
fn response_counter_error(
  view : EmailView,
  ticket : RequestTicket,
  bytes : Int32,
  counts_round : Bool,
) -> String? {
  if ticket.request_id == @int.MAX_VALUE {
    Some("request id overflow")
  } else if view.rounds < 0 || view.bytes_seen < 0 {
    Some("response counters must be non-negative")
  } else if counts_round && view.rounds == @int.MAX_VALUE {
    Some("response round counter overflow")
  } else if bytes >= 0 && bytes > @int.MAX_VALUE - view.bytes_seen {
    Some("response byte counter overflow")
  } else {
    None
  }
}

///|
/// A caller may still hold an outstanding ticket when a previous response
/// exhausted its budget. Keep that checkpoint resumable without consuming
/// another response or advancing any of its counters.
fn response_budget_pending(view : EmailView) -> Acceptance? {
  let reason = if view.rounds >= view.limits.max_rounds {
    Some("round budget exhausted")
  } else if view.bytes_seen >= view.limits.max_bytes {
    Some("byte budget exhausted")
  } else if view.email_required && view.changes_seen >= view.limits.max_changes {
    Some("Email/changes budget exhausted")
  } else {
    None
  }
  match reason {
    Some(reason) => {
      view.completeness = Pending
      view.pending_reason = Some(reason)
      Some(Pending({ view, checkpoint: checkpoint(view), reason, }))
    }
    None => None
  }
}

///|
fn accept_error(
  view : EmailView,
  ticket : RequestTicket,
  error : ResponseError,
) -> Acceptance {
  match response_counter_error(view, ticket, 0, false) {
    Some(reason) => return protocol_failure(view, reason)
    None => ()
  }
  view.next_request_id = ticket.request_id + 1
  match error {
    CannotCalculateChanges =>
      if ticket.kind == QueryChanges {
        needs_refresh(view, "query history is no longer available")
      } else if ticket.kind == Changes {
        email_history_invalid(view, "Email history is no longer available")
      } else {
        protocol_failure(view, "changes error on a non-changes request")
      }
    TooManyChanges =>
      if ticket.kind == QueryChanges {
        needs_refresh(view, "query changes exceed the bounded refresh budget")
      } else if ticket.kind == Changes {
        email_history_invalid(
          view, "Email changes exceed the bounded refresh budget",
        )
      } else {
        protocol_failure(view, "tooManyChanges on a non-changes request")
      }
    NotFound =>
      if ticket.kind == Changes {
        email_history_invalid(view, "Email state was not found")
      } else if ticket.kind == QueryChanges {
        needs_refresh(view, "query state was not found")
      } else {
        needs_refresh(view, "requested state was not found")
      }
    Unsupported(reason) => unsupported(view, reason)
    Malformed(reason) => protocol_failure(view, reason)
  }
}

///|
fn accept_query(
  view : EmailView,
  ticket : RequestTicket,
  data : QueryData,
) -> Acceptance {
  match response_counter_error(view, ticket, data.bytes, true) {
    Some(reason) => return protocol_failure(view, reason)
    None => ()
  }
  if data.state == "" {
    return protocol_failure(view, "query state token must be non-empty")
  }
  match response_budget_pending(view) {
    Some(pending) => return pending
    None => ()
  }
  view.next_request_id = ticket.request_id + 1
  if data.bytes < 0 || data.total < 0 || data.ids.length() > data.total {
    return protocol_failure(view, "query total is smaller than returned ids")
  }
  if data.ids.length() > ticket.limit {
    return protocol_failure(
      view, "query returned more ids than the requested limit",
    )
  }
  // Use subtraction after non-negative bounds checks, rather than allowing
  // position + length to wrap for a malformed large response.
  if ticket.position < 0 ||
    ticket.position > data.total ||
    data.ids.length() > data.total - ticket.position {
    return protocol_failure(view, "query page is outside the reported total")
  }
  // A non-empty page budget with no returned IDs cannot make progress while
  // `position` is still before the server-reported total. This applies to
  // both an initial query page and a later prefix fill; accepting it would
  // schedule the same position again and can spin until the round budget.
  if data.ids.length() == 0 && ticket.limit > 0 && ticket.position < data.total {
    return protocol_failure(
      view, "query page returned no ids before the reported total",
    )
  }
  if !unique_nonempty(data.ids) {
    return protocol_failure(view, "query returned duplicate ids")
  }
  let is_fill = ticket.position > 0 || view.query_fill_required
  let next = view
  if is_fill {
    if ticket.position != view.ordered_ids.length() {
      return protocol_failure(
        view, "query fill is not contiguous with the cached prefix",
      )
    }
    match ticket.expected_query_state {
      Some(expected) =>
        if expected != data.state {
          return needs_refresh(
            view, "prefix fill crossed queryState boundaries",
          )
        }
      None =>
        return protocol_failure(view, "prefix fill has no expected queryState")
    }
    if data.total != view.total {
      return protocol_failure(
        view, "query fill changed total without changing queryState",
      )
    }
    for id in data.ids {
      if contains_string(view.ordered_ids, id) {
        return protocol_failure(view, "query fill overlaps the cached prefix")
      }
    }
    for id in data.ids {
      if next.ordered_ids.length() < next.limits.prefix_limit {
        next.ordered_ids.push(id)
      }
    }
    next.total = data.total
    next.query_fill_required = false
  } else {
    next.ordered_ids = prefix_strings(data.ids, next.limits.prefix_limit)
    next.total = data.total
    next.query_state = Some(data.state)
    next.query_valid = true
    next.query_required = false
    if next.email_state is None {
      next.email_required = true
    }
    next.query_fill_required = next.ordered_ids.length() < target_length(next)
    next.query_fill_position = next.ordered_ids.length()
    next.pending_get = []
    next.objects = next.objects.filter(fn(record) {
      contains_string(next.ordered_ids, record.id)
    })
  }
  next.rounds = next.rounds + 1
  next.bytes_seen = next.bytes_seen + data.bytes
  finish_or_continue(next)
}

///|
/// Keep only the leading IDs that a query delta cannot affect. Do not
/// insert, move or reconstruct IDs locally. The first removed cached slot
/// or added final rank cuts the trusted prefix; Email/query then reads the
/// entire uncertain suffix under the newly accepted queryState.
fn unchanged_query_cut(
  cached_ids : Array[String],
  removed : Array[String],
  added : Array[Added],
  target : Int32,
) -> Int32 {
  let mut cut = min_int(target, cached_ids.length())
  for index, id in cached_ids {
    if index < cut && removed.contains(id) {
      cut = index
    }
  }
  for addition in added {
    if addition.index < cut {
      cut = addition.index
    }
  }
  cut
}

///|
fn accept_query_changes(
  view : EmailView,
  ticket : RequestTicket,
  data : QueryChangesData,
) -> Acceptance {
  match response_counter_error(view, ticket, data.bytes, true) {
    Some(reason) => return protocol_failure(view, reason)
    None => ()
  }
  if data.old_state == "" || data.new_state == "" {
    return protocol_failure(view, "queryChanges state tokens must be non-empty")
  }
  match response_budget_pending(view) {
    Some(pending) => return pending
    None => ()
  }
  view.next_request_id = ticket.request_id + 1
  match view.query_state {
    Some(state) =>
      if state != data.old_state ||
        state != ticket.expected_query_state.unwrap_or("") {
        return protocol_failure(
          view, "queryChanges oldState does not match checkpoint",
        )
      }
    None =>
      return protocol_failure(
        view, "queryChanges requires an existing queryState",
      )
  }
  if data.bytes < 0 ||
    data.total < 0 ||
    !unique_nonempty(data.removed) ||
    !unique_added_ids(data.added) {
    return protocol_failure(view, "queryChanges returned invalid ids")
  }
  let mut previous_index = -1
  for added in data.added {
    if added.index < 0 || added.index >= data.total {
      return protocol_failure(
        view, "queryChanges returned an out-of-range insertion index",
      )
    }
    // RFC 8620 section 5.6 gives indexes in the new result and requires
    // ascending order. Distinct IDs cannot occupy the same final position.
    if added.index <= previous_index {
      return protocol_failure(
        view, "queryChanges added indexes must be strictly increasing",
      )
    }
    previous_index = added.index
    if contains_string(view.ordered_ids, added.id) &&
      !contains_string(data.removed, added.id) {
      return protocol_failure(
        view, "queryChanges re-added a cached id without removing it",
      )
    }
  }
  let new_target = min_int(view.limits.prefix_limit, data.total)
  // Equal queryState can conservatively remove/re-add an unchanged ID at
  // its existing rank. Reject contradictions that are visible in our old
  // prefix without running a general sequence reconstruction algorithm.
  let same_state = data.old_state == data.new_state
  if same_state {
    if data.total != view.total {
      return protocol_failure(
        view, "queryChanges changed total without changing queryState",
      )
    }
    for position, id in view.ordered_ids {
      if data.removed.contains(id) &&
        !data.added.any(fn(item) { item.id == id && item.index == position }) {
        return protocol_failure(
          view, "queryChanges changed the known result without changing queryState",
        )
      }
    }
    for item in data.added {
      if item.index < view.ordered_ids.length() &&
        view.ordered_ids[item.index] != item.id {
        return protocol_failure(
          view, "queryChanges changed the known result without changing queryState",
        )
      }
    }
  }
  let cut = if same_state {
    min_int(new_target, view.ordered_ids.length())
  } else {
    unchanged_query_cut(view.ordered_ids, data.removed, data.added, new_target)
  }
  let updated_ids = prefix_strings(view.ordered_ids, cut)
  let next = view
  next.ordered_ids = updated_ids
  for id in data.removed {
    next.objects = next.objects.filter(fn(record) { record.id != id })
  }
  next.total = data.total
  next.query_state = Some(data.new_state)
  next.query_valid = true
  next.query_required = false
  next.query_fill_required = next.ordered_ids.length() < target_length(next)
  next.query_fill_position = next.ordered_ids.length()
  // Cache and fetch obligations are confined to the confirmed leading
  // prefix. Suffix IDs are admitted only after the server returns them.
  next.objects = next.objects.filter(fn(record) {
    updated_ids.contains(record.id)
  })
  next.pending_get = next.pending_get.filter(fn(id) { updated_ids.contains(id) })
  next.rounds = next.rounds + 1
  next.bytes_seen = next.bytes_seen + data.bytes
  finish_or_continue(next)
}

///|
/// Apply one RFC Email/changes page without reducing its created, updated,
/// and destroyed sets to a generic two-set change projection. Every wire
/// entry consumes maxChanges, even when IDs overlap between change sets.
fn accept_email_changes(
  view : EmailView,
  ticket : RequestTicket,
  data : EmailChangesData,
) -> Acceptance {
  if !unique_nonempty(data.created) ||
    !unique_nonempty(data.destroyed) ||
    !unique_nonempty(data.updated) {
    return protocol_failure(view, "Email/changes returned duplicate ids")
  }
  // Int arithmetic wraps on every supported target. Count before summing.
  if data.created.length() > @int.MAX_VALUE - data.updated.length() ||
    data.destroyed.length() >
    @int.MAX_VALUE - data.created.length() - data.updated.length() {
    return protocol_failure(view, "Email/changes entry count overflow")
  }
  let change_count = data.created.length() +
    data.updated.length() +
    data.destroyed.length()
  match response_counter_error(view, ticket, data.bytes, true) {
    Some(reason) => return protocol_failure(view, reason)
    None => ()
  }
  if data.old_state == "" || data.new_state == "" {
    return protocol_failure(
      view, "Email/changes state tokens must be non-empty",
    )
  }
  match response_budget_pending(view) {
    Some(pending) => return pending
    None => ()
  }
  // A continuation must advance or repeating it would fetch the same page.
  // A final page may conservatively report updates even when the server's
  // current data has returned to the supplied baseline state.
  if data.old_state == data.new_state && data.has_more_changes {
    return protocol_failure(
      view, "Email/changes continuation did not advance its state",
    )
  }
  view.next_request_id = ticket.request_id + 1
  if data.bytes < 0 {
    return protocol_failure(
      view, "Email/changes returned invalid ids or byte count",
    )
  }
  if ticket.max_changes <= 0 ||
    ticket.limit != ticket.max_changes ||
    change_count > ticket.max_changes ||
    view.changes_seen < 0 ||
    view.changes_seen > view.limits.max_changes ||
    change_count > view.limits.max_changes - view.changes_seen {
    return protocol_failure(
      view, "Email/changes exceeded the requested change budget",
    )
  }
  match view.email_state {
    Some(state) =>
      if state != data.old_state ||
        state != ticket.expected_email_state.unwrap_or("") {
        return protocol_failure(
          view, "Email/changes oldState does not match checkpoint",
        )
      }
    None =>
      return protocol_failure(view, "Email/changes requires an existing state")
  }
  let next = view
  next.email_required = false
  next.email_valid = true
  next.email_state = Some(data.new_state)
  next.changes_seen = next.changes_seen + change_count
  // A paginated Email/changes response must be fully consumed before a
  // queryChanges pass. Re-querying here would race the next Email state and
  // could publish a list that skipped an intermediate object update. Once
  // the page sequence is drained, any actual object change also requires a
  // query reconciliation: an updated keyword/mailbox/date can change query
  // membership or ordering even when the ID remains in the cached prefix,
  // and a destroyed ID must be removed and replaced from the query result.
  // Created IDs may be outside the cached query. They still require query
  // reconciliation once the Email/changes page sequence has been drained.
  next.query_required = !data.has_more_changes ||
    data.created.length() > 0 ||
    data.destroyed.length() > 0 ||
    data.updated.length() > 0
  // Email object history and query ordering have independent tokens. An
  // object update requests a queryChanges pass but does not invalidate the
  // previously accepted queryState.
  next.query_fill_required = false
  next.pending_get = remove_strings(next.pending_get, data.destroyed)
  let live_updated = data.updated.filter(fn(id) {
    !contains_string(data.destroyed, id)
  })
  // A changed prefix member is no longer a displayable old payload. Retain
  // its query position until queryChanges decides membership, but remove
  // its stale fields immediately. Off-prefix creations/updates never become
  // cache entries or direct Email/get obligations in this bounded view.
  next.objects = next.objects.filter(fn(record) {
    !contains_string(live_updated, record.id)
  })
  for id in live_updated {
    if contains_string(next.ordered_ids, id) &&
      !contains_string(next.pending_get, id) {
      next.pending_get.push(id)
    }
  }
  for id in data.destroyed {
    next.objects = next.objects.filter(fn(record) { record.id != id })
  }
  next.rounds = next.rounds + 1
  next.bytes_seen = next.bytes_seen + data.bytes
  if data.has_more_changes {
    next.email_required = true
  }
  // finish_or_continue also inspects the ordered prefix, which can still
  // contain a destroyed ID until queryChanges removes it. Destruction wins
  // over that interim object-fetch obligation and any overlapping update.
  clear_destroyed_pending(finish_or_continue(next), data.destroyed)
}

///|
fn accept_get(
  view : EmailView,
  ticket : RequestTicket,
  data : GetData,
) -> Acceptance {
  match response_counter_error(view, ticket, data.bytes, true) {
    Some(reason) => return protocol_failure(view, reason)
    None => ()
  }
  if data.state == "" {
    return protocol_failure(view, "Email/get state token must be non-empty")
  }
  match response_budget_pending(view) {
    Some(pending) => return pending
    None => ()
  }
  view.next_request_id = ticket.request_id + 1
  if data.bytes < 0 {
    return protocol_failure(view, "Email/get reported a negative byte count")
  }
  // Validate the complete response before mutating the cached object set.
  // The wire adapter performs the same checks, but ServerResponse is public
  // and callers can construct it directly in a replay or test harness.
  if !unique_nonempty(ticket.requested_ids) {
    return protocol_failure(
      view, "Email/get request contains duplicate or empty ids",
    )
  }
  if !unique_nonempty(data.not_found) {
    return protocol_failure(
      view, "Email/get returned duplicate or empty notFound ids",
    )
  }
  let list_ids : Array[String] = []
  for record in data.list {
    if !unique_nonempty([record.id]) || contains_string(list_ids, record.id) {
      return protocol_failure(
        view, "Email/get returned duplicate or empty object ids",
      )
    }
    if contains_string(data.not_found, record.id) {
      return protocol_failure(
        view, "Email/get returned an id in both list and notFound",
      )
    }
    if !contains_string(ticket.requested_ids, record.id) {
      return protocol_failure(
        view, "Email/get returned an id that was not requested",
      )
    }
    // Keep an incomplete projection as an explicit pending object.  It is
    // useful for diagnostics and can be replaced by a later Email/get, but
    // `missing_object_ids` treats it as missing so this response can never
    // produce Ready.
    list_ids.push(record.id)
  }
  for id in data.not_found {
    if !contains_string(ticket.requested_ids, id) {
      return protocol_failure(
        view, "Email/get returned an unrequested notFound id",
      )
    }
  }
  // Every explicitly requested ID must be accounted for by either `list` or
  // `notFound`.  Silently accepting an omitted ID would allow an old cached
  // object to satisfy the request after its pending marker is removed, which
  // could publish stale attributes as Ready.  The empty-ID baseline request
  // is still valid because there is nothing to account for.
  for id in ticket.requested_ids {
    if !contains_string(list_ids, id) && !contains_string(data.not_found, id) {
      return protocol_failure(view, "Email/get omitted a requested id")
    }
  }
  let next = view
  let expected_state = ticket.expected_email_state
  match expected_state {
    Some(expected) =>
      if expected != data.state {
        next.email_required = true
        next.email_valid = false
      } else {
        next.email_valid = true
      }
    None => {
      next.email_state = Some(data.state)
      next.email_valid = true
      next.email_required = false
    }
  }
  for record in data.list {
    next.objects = next.objects.filter(fn(old) { old.id != record.id })
    if contains_string(next.ordered_ids, record.id) {
      next.objects.push(record)
    }
    next.pending_get = remove_string(next.pending_get, record.id)
  }
  for id in data.not_found {
    next.pending_get = remove_string(next.pending_get, id)
    next.objects = next.objects.filter(fn(record) { record.id != id })
    // Keep the old ordered prefix intact until a fresh query proves the
    // member is gone. Removing it locally would create a short, falsely
    // complete list and lose the position that needs to be replenished.
    next.query_required = true
    next.query_valid = false
  }
  for id in ticket.requested_ids {
    next.pending_get = remove_string(next.pending_get, id)
  }
  next.rounds = next.rounds + 1
  next.bytes_seen = next.bytes_seen + data.bytes
  finish_or_continue(next)
}

///|
fn unique_added_ids(values : Array[Added]) -> Bool {
  let ids : Array[String] = []
  for value in values {
    if value.id == "" || contains_string(ids, value.id) {
      return false
    }
    ids.push(value.id)
  }
  true
}

///|
fn unique(values : Array[String]) -> Bool {
  let seen : Array[String] = []
  for value in values {
    if contains_string(seen, value) {
      return false
    }
    seen.push(value)
  }
  true
}

///|
fn unique_nonempty(values : Array[String]) -> Bool {
  for value in values {
    if value == "" {
      return false
    }
  }
  unique(values)
}
