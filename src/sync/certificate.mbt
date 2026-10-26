///|
/// A domain-specific witness for one bounded Email query-view transition.
///
/// This is intentionally narrower than a generic JSON patch or workflow log:
/// it can only describe the ordered prefix used by MoonJMAP's two supported
/// projections. Each resulting slot identifies its earlier position, or an
/// Email ID newly entering the bounded prefix. The verifier checks position
/// correspondence and the two independent JMAP state boundaries; no generic
/// edit script or fingerprint is involved.
pub(all) enum WitnessKind {
  Noop
  QueryDelta
  EmailDelta
  MixedDelta
} derive(Eq)

///|
pub extend WitnessKind with Eq::{not_equal, equal}

///|
/// One resulting Email/query prefix slot. A retained Email may change its
/// position, but its identity comes directly from the immutable before
/// position. Introduced IDs must be absent from that bounded before prefix;
/// this does not assert that the Email was created on the server.
pub(all) enum PrefixSlotWitness {
  FromBefore(Int32)
  Introduced(String)
} derive(Eq)

///|
pub extend PrefixSlotWitness with Eq::{not_equal, equal}

///|
/// The part of the ordered Email prefix that this witness covers.  The
/// interval is half-open: `[start, end)` is known, while
/// `[end, target_end)` is a deliberately visible gap when the bounded query
/// is still being filled.  This is specific to the fixed JMAP Email/query
/// projection; it is not a generic collection reconciliation range.
pub(all) enum PrefixFrontier {
  Open
  Closed
} derive(Eq)

///|
pub extend PrefixFrontier with Eq::{not_equal, equal}

///|
pub(all) struct PrefixCoverage {
  start : Int32
  end : Int32
  target_end : Int32
  missing : Int32
  frontier : PrefixFrontier
  /// True only when a query fill appended to an already known prefix without
  /// changing queryState.  This proves that the fill did not silently mix
  /// two query snapshots.
  same_query_state_fill : Bool
  /// Whether every Email ID in the after prefix has the fixed presentation
  /// projection required for a Ready commit.
  objects_complete : Bool
} derive(Eq)

///|
pub extend PrefixCoverage with Eq::{not_equal, equal}

///|
/// A binding to the one concrete JMAP request that produced a transition.
/// Keeping the request shape in the witness makes a prefix proof reject a
/// certificate copied from another query, page, or account generation.
pub(all) struct EmailPrefixPlanBinding {
  /// The complete typed request is retained, including account, QueryKey,
  /// expected states, requested IDs, fixed filter/sort and properties. These
  /// are checked as fields rather than a delimiter string or digest.
  request : Request
} derive(Eq)

///|
pub extend EmailPrefixPlanBinding with Eq::{not_equal, equal}

///|
pub(all) struct DecisionCertificate {
  query : QueryKey
  generation_before : Int32
  generation_after : Int32
  before_ids : Array[String]
  after_ids : Array[String]
  before_prefix_limit : Int32
  after_prefix_limit : Int32
  before_total : Int32
  after_total : Int32
  /// Exactly one positional explanation for each after slot.
  slots : Array[PrefixSlotWitness]
  query_state_before : String?
  query_state_after : String?
  email_state_before : String?
  email_state_after : String?
  completeness : Completeness
  kind : WitnessKind
  reason : String
  coverage : PrefixCoverage
  plan_binding : EmailPrefixPlanBinding?
} derive(Eq)

///|
pub extend DecisionCertificate with Eq::{not_equal, equal}

///|
/// Public domain name for the certificate.  `DecisionCertificate` remains as
/// a compatibility spelling, while new integrations can make it explicit
/// that this artifact is only a JMAP Email query-prefix certificate.
pub type JmapEmailPrefixCertificate = DecisionCertificate

///|
/// Build a certificate from two views.  The arrays are copied so the witness
/// remains stable if a caller mutates a subsequent view. Each resulting slot
/// refers to its original position when that Email was already in the bounded
/// prefix; an ID absent from the prefix receives an Introduced slot.
pub fn certificate_from_views(
  before : EmailView,
  after : EmailView,
  completeness : Completeness,
  reason : String,
) -> Result[DecisionCertificate, String] {
  certificate_from_views_bound(before, after, completeness, reason, None)
}

///|
/// Build a prefix certificate and bind it to the single request in `plan`.
/// The ordinary view-only constructor remains useful for a persisted state
/// transition; this variant is the stronger form for a live adapter because
/// it proves which JMAP page was allowed to cause the transition.
pub fn certificate_from_views_with_plan(
  before : EmailView,
  after : EmailView,
  completeness : Completeness,
  reason : String,
  plan : Plan,
) -> Result[DecisionCertificate, String] {
  match email_prefix_plan_binding(plan) {
    Ok(binding) => {
      match make_next_request(before) {
        Some(expected) =>
          if binding.request != expected {
            return Err("planned request differs from the current Email view")
          }
        None => return Err("Email view has no request for this plan binding")
      }
      certificate_from_views_bound(
        before,
        after,
        completeness,
        reason,
        Some(binding),
      )
    }
    Err(error) => Err(error)
  }
}

///|
/// Domain-named entry point for callers that want to make the JMAP-specific
/// nature of the artifact explicit in their own APIs.
pub fn email_prefix_proof_from_views(
  before : EmailView,
  after : EmailView,
  completeness : Completeness,
  reason : String,
) -> Result[DecisionCertificate, String] {
  certificate_from_views(before, after, completeness, reason)
}

///|
fn certificate_from_views_bound(
  before : EmailView,
  after : EmailView,
  completeness : Completeness,
  reason : String,
  plan_binding : EmailPrefixPlanBinding?,
) -> Result[DecisionCertificate, String] {
  if before.account != after.account ||
    before.query != after.query ||
    before.account != before.query.account ||
    after.account != after.query.account {
    return Err("certificate views belong to different accounts or queries")
  }
  if before.generation < 0 ||
    after.generation < 0 ||
    after.generation < before.generation {
    return Err("certificate generation moved backwards")
  }
  if before.total < 0 ||
    after.total < 0 ||
    before.limits.prefix_limit <= 0 ||
    after.limits.prefix_limit <= 0 ||
    before.ordered_ids.length() > before.total ||
    after.ordered_ids.length() > after.total ||
    before.ordered_ids.length() > before.limits.prefix_limit ||
    after.ordered_ids.length() > after.limits.prefix_limit {
    return Err("certificate prefix exceeds its reported total")
  }
  if !unique_nonempty_certificate(before.ordered_ids) ||
    !unique_nonempty_certificate(after.ordered_ids) {
    return Err("certificate prefix contains duplicate or empty ids")
  }
  if reason == "" {
    return Err("certificate reason must be non-empty")
  }
  if !valid_state_option(before.query_state) ||
    !valid_state_option(after.query_state) ||
    !valid_state_option(before.email_state) ||
    !valid_state_option(after.email_state) {
    return Err("certificate state token cannot be empty")
  }
  let slots = prefix_slots(before.ordered_ids, after.ordered_ids)
  let coverage = prefix_coverage(before, after)
  let kind = witness_kind(
    before.ordered_ids,
    after.ordered_ids,
    before.query_state,
    after.query_state,
    before.email_state,
    after.email_state,
  )
  let certificate : DecisionCertificate = {
    query: before.query,
    generation_before: before.generation,
    generation_after: after.generation,
    before_ids: before.ordered_ids.copy(),
    after_ids: after.ordered_ids.copy(),
    before_prefix_limit: before.limits.prefix_limit,
    after_prefix_limit: after.limits.prefix_limit,
    before_total: before.total,
    after_total: after.total,
    slots,
    query_state_before: before.query_state,
    query_state_after: after.query_state,
    email_state_before: before.email_state,
    email_state_after: after.email_state,
    completeness,
    kind,
    reason,
    coverage,
    plan_binding,
  }
  match verify_certificate(certificate) {
    Ok(_) => Ok(certificate)
    Err(error) => Err("generated certificate is not verifiable: " + error)
  }
}

///|
/// Extract a binding from a one-request plan.  MoonJMAP deliberately emits
/// one call per plan, so accepting a multi-request plan here would make the
/// provenance ambiguous.
pub fn email_prefix_plan_binding(
  plan : Plan,
) -> Result[EmailPrefixPlanBinding, String] {
  if plan.requests.length() != 1 {
    return Err("email prefix proof requires exactly one planned request")
  }
  let request = plan.requests[0]
  if request.ticket.generation != plan.generation {
    return Err("planned request generation does not match its plan")
  }
  match request_shape_error(request) {
    Some(error) => return Err(error)
    None => ()
  }
  Ok({
    request: {
      ..request,
      ticket: {
        ..request.ticket,
        requested_ids: request.ticket.requested_ids.copy(),
      },
      ids: request.ids.copy(),
      properties: request.properties.copy(),
    },
  })
}

///|
/// Check the finite JMAP request representation directly. Fixed filter, sort,
/// properties and duplicate-free IDs are part of the shape, including fields
/// that a string summary could accidentally omit or ambiguously delimit.
fn request_shape_error(request : Request) -> String? {
  let ticket = request.ticket
  if ticket.generation < 0 ||
    ticket.request_id <= 0 ||
    request.position < 0 ||
    request.limit < 0 ||
    request.max_changes < 0 {
    return Some("planned request has an invalid coverage bound")
  }
  if !valid_certificate_query(ticket.query) ||
    ticket.account != ticket.query.account {
    return Some("planned request account does not match its structured query")
  }
  if request.kind != ticket.kind ||
    request.ids != ticket.requested_ids ||
    request.position != ticket.position ||
    request.limit != ticket.limit ||
    request.max_changes != ticket.max_changes {
    return Some("planned request shape is inconsistent with its ticket")
  }
  if !valid_state_option(ticket.expected_query_state) ||
    !valid_state_option(ticket.expected_email_state) {
    return Some("planned request has an empty expected state")
  }
  if !unique_nonempty_certificate(request.ids) {
    return Some("planned request has duplicate or empty Email IDs")
  }
  if request.properties != @email.default_properties() {
    return Some("planned request properties differ from fixed Email projection")
  }
  match request.kind {
    Query | QueryChanges => {
      if request.filter != Some(ticket.query.view.filter_spec()) ||
        request.sort != Some(ticket.query.view.sort_spec()) {
        return Some(
          "planned request filter or sort differs from structured query",
        )
      }
      if request.ids.length() != 0 ||
        request.limit <= 0 ||
        request.max_changes != 0 {
        return Some("planned query request has an invalid payload")
      }
      if request.kind == QueryChanges &&
        (request.position != 0 || ticket.expected_query_state is None) {
        return Some("Email/queryChanges request lacks its prior queryState")
      }
    }
    Get | Changes => {
      if request.filter is Some(_) ||
        request.sort is Some(_) ||
        request.position != 0 {
        return Some("planned Email object request carries query-only fields")
      }
      if request.kind == Get {
        if request.max_changes != 0 || request.limit != request.ids.length() {
          return Some("Email/get shape does not match its requested IDs")
        }
        if request.ids.length() == 0 && ticket.expected_email_state is Some(_) {
          return Some("baseline Email/get request already has an Email state")
        }
      } else if request.ids.length() != 0 ||
        request.limit <= 0 ||
        request.max_changes != request.limit ||
        ticket.expected_email_state is None {
        return Some("Email/changes request has an invalid state or maxChanges")
      }
    }
  }
  None
}

///|
fn valid_certificate_query(query : QueryKey) -> Bool {
  let mailbox_valid = match query.view {
    @email.ViewSpec::Latest(mailbox) | @email.ViewSpec::Unread(mailbox) =>
      mailbox != ""
  }
  query.account.service_identity != "" &&
  query.account.account_id != "" &&
  !query.collapse_threads &&
  mailbox_valid
}

///|
pub fn verify_email_prefix_proof(
  certificate : DecisionCertificate,
) -> Result[Unit, String] {
  verify_certificate(certificate)
}

///|
/// Explicitly named compatibility entry point for integrations that expose
/// the public `JmapEmailPrefixCertificate` alias.
pub fn verify_jmap_email_prefix_certificate(
  certificate : JmapEmailPrefixCertificate,
) -> Result[Unit, String] {
  verify_certificate(certificate)
}

///|
/// Generate a witness directly from one sync acceptance.  Every acceptance
/// carries the resulting view, including dropped and failed responses, so an
/// audit trail can explain both committed and rejected transitions.
pub fn certificate_from_acceptance(
  before : EmailView,
  result : Acceptance,
) -> Result[DecisionCertificate, String] {
  match result {
    Continue(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.plan.reason,
      )
    Commit(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        "committed",
      )
    Pending(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.reason,
      )
    NeedsRefresh(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.reason,
      )
    Unsupported(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.reason,
      )
    ProtocolFailure(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.reason,
      )
    Dropped(value) =>
      certificate_from_views(
        before,
        value.view,
        value.view.completeness,
        value.reason,
      )
  }
}

///|
/// Verify a certificate without network access, JSON, or mutable global state.
/// It checks the certificate's internal consistency on every MoonBit target.
/// The optional request is a typed local binding, not authenticated server
/// provenance. objects_complete is a producer assertion, not Email payload.
pub fn verify_certificate(
  certificate : DecisionCertificate,
) -> Result[Unit, String] {
  if !valid_certificate_query(certificate.query) {
    return Err("certificate structured query is invalid")
  }
  if certificate.generation_before < 0 ||
    certificate.generation_after < 0 ||
    certificate.generation_after < certificate.generation_before {
    return Err("certificate generation moved backwards")
  }
  if certificate.before_total < 0 ||
    certificate.after_total < 0 ||
    certificate.before_prefix_limit <= 0 ||
    certificate.after_prefix_limit <= 0 ||
    certificate.before_ids.length() > certificate.before_total ||
    certificate.after_ids.length() > certificate.after_total ||
    certificate.before_ids.length() > certificate.before_prefix_limit ||
    certificate.after_ids.length() > certificate.after_prefix_limit {
    return Err("certificate prefix is longer than its total")
  }
  if !unique_nonempty_certificate(certificate.before_ids) ||
    !unique_nonempty_certificate(certificate.after_ids) {
    return Err("certificate contains duplicate or empty prefix ids")
  }
  if !valid_state_option(certificate.query_state_before) ||
    !valid_state_option(certificate.query_state_after) ||
    !valid_state_option(certificate.email_state_before) ||
    !valid_state_option(certificate.email_state_after) {
    return Err("certificate state token cannot be empty")
  }
  if certificate.reason == "" {
    return Err("certificate reason is empty")
  }
  match verify_prefix_coverage(certificate) {
    Some(error) => return Err(error)
    None => ()
  }
  match verify_plan_binding(certificate) {
    Some(error) => return Err(error)
    None => ()
  }
  match
    verify_state_boundary(
      certificate.query_state_before,
      certificate.query_state_after,
      certificate.completeness,
      "queryState",
    ) {
    Some(error) => return Err(error)
    None => ()
  }
  match
    verify_state_boundary(
      certificate.email_state_before,
      certificate.email_state_after,
      certificate.completeness,
      "emailState",
    ) {
    Some(error) => return Err(error)
    None => ()
  }
  if certificate.before_ids != certificate.after_ids &&
    certificate.query_state_after is None {
    return Err("ordered query prefix changed without an after queryState")
  }
  match verify_prefix_slots(certificate) {
    Some(error) => return Err(error)
    None => ()
  }
  let expected_kind = witness_kind(
    certificate.before_ids,
    certificate.after_ids,
    certificate.query_state_before,
    certificate.query_state_after,
    certificate.email_state_before,
    certificate.email_state_after,
  )
  if expected_kind != certificate.kind {
    return Err("certificate kind does not match its state and prefix delta")
  }
  if certificate.completeness == Ready {
    if certificate.query_state_after is None ||
      certificate.email_state_after is None {
      return Err("Ready certificate has no current queryState or emailState")
    }
  }
  Ok(())
}

///|
fn prefix_coverage(before : EmailView, after : EmailView) -> PrefixCoverage {
  let target_end = min_certificate(after.total, after.limits.prefix_limit)
  let end = after.ordered_ids.length()
  let missing = target_end - end
  let same_query_state_fill = before.query_state is Some(before_state) &&
    after.query_state is Some(after_state) &&
    before_state == after_state &&
    end > before.ordered_ids.length() &&
    is_prefix_certificate(before.ordered_ids, after.ordered_ids)
  {
    start: 0,
    end,
    target_end,
    missing,
    frontier: if missing == 0 {
      Closed
    } else {
      Open
    },
    same_query_state_fill,
    objects_complete: complete_objects_for_prefix(after),
  }
}

///|
fn verify_prefix_coverage(certificate : DecisionCertificate) -> String? {
  let expected_target = min_certificate(
    certificate.after_total,
    certificate.after_prefix_limit,
  )
  let expected_end = certificate.after_ids.length()
  if certificate.coverage.start != 0 {
    return Some("Email prefix coverage must start at zero")
  }
  if certificate.coverage.end != expected_end ||
    certificate.coverage.target_end != expected_target {
    return Some("Email prefix coverage interval does not match after prefix")
  }
  if certificate.coverage.missing != expected_target - expected_end ||
    certificate.coverage.missing < 0 {
    return Some("Email prefix coverage gap is inconsistent")
  }
  let expected_frontier = if certificate.coverage.missing == 0 {
    PrefixFrontier::Closed
  } else {
    PrefixFrontier::Open
  }
  if certificate.coverage.frontier != expected_frontier {
    return Some("Email prefix frontier does not match its gap")
  }
  if certificate.completeness == Ready &&
    certificate.coverage.frontier != PrefixFrontier::Closed {
    return Some("Ready Email prefix proof still has an open frontier")
  }
  let expected_same_state_fill = certificate.query_state_before
    is Some(before_state) &&
    certificate.query_state_after is Some(after_state) &&
    before_state == after_state &&
    certificate.after_ids.length() > certificate.before_ids.length() &&
    is_prefix_certificate(certificate.before_ids, certificate.after_ids)
  if certificate.coverage.same_query_state_fill != expected_same_state_fill {
    return Some("same queryState fill witness is inconsistent")
  }
  if certificate.completeness == Ready && !certificate.coverage.objects_complete {
    return Some("Ready Email prefix proof has incomplete object projection")
  }
  None
}

///|
fn verify_plan_binding(certificate : DecisionCertificate) -> String? {
  match certificate.plan_binding {
    None => None
    Some(binding) => {
      let request = binding.request
      let ticket = request.ticket
      match request_shape_error(request) {
        Some(error) => return Some(error)
        None => ()
      }
      if ticket.query != certificate.query ||
        ticket.account != certificate.query.account {
        return Some(
          "plan binding account or structured query differs from certificate",
        )
      }
      if certificate.before_prefix_limit != certificate.after_prefix_limit {
        return Some("planned request cannot change the bounded prefix limit")
      }
      if ticket.generation != certificate.generation_before ||
        ticket.generation != certificate.generation_after {
        return Some("plan binding generation does not cover certificate")
      }
      if ticket.expected_query_state != certificate.query_state_before ||
        ticket.expected_email_state != certificate.email_state_before {
        return Some("plan binding state frontier does not match before view")
      }
      verify_bound_request_shape(certificate, request)
    }
  }
}

///|
/// Match the complete typed JMAP request to this bounded Email prefix. The
/// verifier checks protocol-specific constraints without accepting a hash of
/// a caller-provided record as evidence for the record itself.
fn verify_bound_request_shape(
  certificate : DecisionCertificate,
  request : Request,
) -> String? {
  match request.kind {
    Query => {
      if certificate.email_state_before != certificate.email_state_after {
        return Some("Email/query binding cannot advance the Email state")
      }
      let expected_limit = if request.position == 0 {
        certificate.before_prefix_limit
      } else if request.position == certificate.before_ids.length() {
        certificate.before_prefix_limit - certificate.before_ids.length()
      } else {
        -1
      }
      if expected_limit <= 0 || request.limit != expected_limit {
        return Some(
          "Email/query plan binding page does not match prefix frontier",
        )
      }
      if request.position > 0 {
        if !is_prefix_certificate(certificate.before_ids, certificate.after_ids) ||
          certificate.query_state_before != certificate.query_state_after {
          return Some(
            "Email/query fill binding crosses its fixed queryState prefix",
          )
        }
        if certificate.after_ids.length() > request.position + request.limit {
          return Some("Email/query fill exceeds its planned page")
        }
      }
    }
    QueryChanges => {
      if certificate.email_state_before != certificate.email_state_after {
        return Some("Email/queryChanges binding cannot advance the Email state")
      }
      if request.limit != certificate.before_prefix_limit {
        return Some(
          "Email/queryChanges plan binding has an invalid prefix limit",
        )
      }
    }
    Get => {
      for id in request.ids {
        if !contains_certificate(certificate.before_ids, id) {
          return Some(
            "Email/get binding requests an ID outside the before prefix",
          )
        }
      }
      if certificate.before_ids != certificate.after_ids ||
        certificate.before_total != certificate.after_total {
        return Some("Email/get binding cannot change the ordered query prefix")
      }
      // A failed Email/get may invalidate an unavailable query snapshot.
      // It cannot replace that query's token or publish another ordering.
      let query_invalidated = certificate.query_state_before is Some(_) &&
        certificate.query_state_after is None &&
        (
          certificate.completeness == NeedsRefresh ||
          certificate.completeness == ProtocolFailure
        )
      if certificate.query_state_before != certificate.query_state_after &&
        !query_invalidated {
        return Some("Email/get binding cannot replace queryState")
      }
    }
    Changes =>
      if certificate.before_ids != certificate.after_ids ||
        certificate.query_state_before != certificate.query_state_after ||
        certificate.before_total != certificate.after_total {
        return Some(
          "Email/changes binding cannot change the ordered query prefix",
        )
      }
  }
  None
}

///|
fn min_certificate(left : Int32, right : Int32) -> Int32 {
  if left < right {
    left
  } else {
    right
  }
}

///|
fn is_prefix_certificate(
  prefix : Array[String],
  values : Array[String],
) -> Bool {
  if prefix.length() > values.length() {
    return false
  }
  for index, value in prefix {
    if values[index] != value {
      return false
    }
  }
  true
}

///|
fn complete_objects_for_prefix(view : EmailView) -> Bool {
  for id in view.ordered_ids {
    let mut found = false
    for record in view.objects {
      if record.id == id && record.is_complete() {
        found = true
        break
      }
    }
    if !found {
      return false
    }
  }
  true
}

///|
fn valid_state_option(value : String?) -> Bool {
  match value {
    None => true
    Some(state) => state != ""
  }
}

///|
fn index_of_certificate(values : Array[String], wanted : String) -> Int32 {
  for index, value in values {
    if value == wanted {
      return index
    }
  }
  -1
}

///|
fn contains_certificate(values : Array[String], wanted : String) -> Bool {
  index_of_certificate(values, wanted) >= 0
}

///|
fn unique_nonempty_certificate(values : Array[String]) -> Bool {
  let seen : Array[String] = []
  for value in values {
    if value == "" || contains_certificate(seen, value) {
      return false
    }
    seen.push(value)
  }
  true
}

///|
fn prefix_slots(
  before : Array[String],
  after : Array[String],
) -> Array[PrefixSlotWitness] {
  after.map(fn(id) {
    let origin = index_of_certificate(before, id)
    if origin < 0 {
      Introduced(id)
    } else {
      FromBefore(origin)
    }
  })
}

///|
/// Validate a positional witness in one pass over resulting slots. There is
/// no sequential remove/insert interpretation: every retained slot reads an
/// immutable before position, so moves and fixed points share one rule.
fn verify_prefix_slots(certificate : DecisionCertificate) -> String? {
  if certificate.slots.length() != certificate.after_ids.length() {
    return Some("prefix slot count does not match after prefix")
  }
  let referenced : Array[Bool] = Array::make(
    certificate.before_ids.length(),
    false,
  )
  for position, slot in certificate.slots {
    let after_id = certificate.after_ids[position]
    match slot {
      FromBefore(origin) => {
        if origin < 0 || origin >= certificate.before_ids.length() {
          return Some("prefix slot refers to an out-of-range before position")
        }
        if referenced[origin] {
          return Some("prefix slots reuse a before position")
        }
        if certificate.before_ids[origin] != after_id {
          return Some("prefix slot ID differs from its before position")
        }
        referenced[origin] = true
      }
      Introduced(id) => {
        if id != after_id || id == "" {
          return Some("introduced prefix slot ID differs from after position")
        }
        if contains_certificate(certificate.before_ids, id) {
          return Some("introduced prefix slot already exists in before prefix")
        }
      }
    }
  }
  None
}

///|
fn state_changed(before : String?, after : String?) -> Bool {
  before != after
}

///|
fn witness_kind(
  before_ids : Array[String],
  after_ids : Array[String],
  query_before : String?,
  query_after : String?,
  email_before : String?,
  email_after : String?,
) -> WitnessKind {
  let query_changed = before_ids != after_ids ||
    state_changed(query_before, query_after)
  let email_changed = state_changed(email_before, email_after)
  if query_changed && email_changed {
    MixedDelta
  } else if query_changed {
    QueryDelta
  } else if email_changed {
    EmailDelta
  } else {
    Noop
  }
}

///|
fn verify_state_boundary(
  before : String?,
  after : String?,
  completeness : Completeness,
  label : String,
) -> String? {
  match (before, after) {
    (Some(_), None) =>
      if completeness == NeedsRefresh || completeness == ProtocolFailure {
        None
      } else {
        Some(label + " disappeared without an invalidation outcome")
      }
    _ => None
  }
}
