///|
/// The certificate tests use synthetic IDs and state tokens only. They verify
/// the domain positional contract without a wire server or a generic patch engine.
test "certificate describes each bounded query result slot" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "acc-cert",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  before.ordered_ids = ["a", "b"]
  before.total = 2
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    ordered_ids: ["x", "a", "b"],
    total: 3,
    query_state: Some("q1"),
    completeness: @sync.Completeness::Pending,
  }
  let certificate = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::Pending,
    "query delta applied",
  ).unwrap()
  assert_eq(certificate.slots.length(), 3)
  assert_true(certificate.slots[0] == @sync.PrefixSlotWitness::Introduced("x"))
  assert_true(certificate.slots[1] == @sync.PrefixSlotWitness::FromBefore(0))
  assert_true(certificate.slots[2] == @sync.PrefixSlotWitness::FromBefore(1))
  match certificate.kind {
    @sync.WitnessKind::QueryDelta => ()
    _ => assert_true(false)
  }
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(_) => assert_true(false)
  }
}

///|
test "certificate points moved query slots at immutable before positions" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "move-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Unread("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  before.ordered_ids = ["a", "b", "c"]
  before.total = 3
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    ordered_ids: ["c", "a", "b"],
    query_state: Some("q1"),
  }
  let certificate = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::Pending,
    "query reorder",
  ).unwrap()
  assert_eq(certificate.slots.length(), 3)
  assert_true(certificate.slots[0] == @sync.PrefixSlotWitness::FromBefore(2))
  assert_true(certificate.slots[1] == @sync.PrefixSlotWitness::FromBefore(0))
  assert_true(certificate.slots[2] == @sync.PrefixSlotWitness::FromBefore(1))
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(_) => assert_true(false)
  }
}

///|
fn certificate_test_view(
  ids : Array[String],
  query_state : String,
) -> @sync.EmailView {
  let view = @sync.open_view(
    {
      service_identity: "certificate-service",
      account_id: "reorder-regression-acc",
    },
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  view.ordered_ids = ids.copy()
  view.total = ids.length()
  view.query_state = Some(query_state)
  view.query_valid = true
  view.query_required = false
  view.email_required = false
  view
}

///|
test "certificate preserves fixed positions during a partial reorder" {
  let certificate = @sync.certificate_from_views(
    certificate_test_view(["a", "b", "c"], "q0"),
    certificate_test_view(["b", "a", "c"], "q1"),
    @sync.Completeness::Pending,
    "swap first two while preserving third",
  ).unwrap()
  assert_eq(certificate.slots.length(), 3)
  assert_true(certificate.slots[0] == @sync.PrefixSlotWitness::FromBefore(1))
  assert_true(certificate.slots[1] == @sync.PrefixSlotWitness::FromBefore(0))
  assert_true(certificate.slots[2] == @sync.PrefixSlotWitness::FromBefore(2))
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
}

///|
test "certificate combines reorder and set changes around a retained anchor" {
  let certificate = @sync.certificate_from_views(
    certificate_test_view(["a", "b", "c", "d"], "q0"),
    certificate_test_view(["c", "b", "x"], "q1"),
    @sync.Completeness::Pending,
    "move c and replace the tail while b stays at one",
  ).unwrap()
  assert_eq(certificate.slots.length(), 3)
  assert_true(certificate.slots[0] == @sync.PrefixSlotWitness::FromBefore(2))
  assert_true(certificate.slots[1] == @sync.PrefixSlotWitness::FromBefore(1))
  assert_true(certificate.slots[2] == @sync.PrefixSlotWitness::Introduced("x"))
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
}

///|
test "certificate rejects forged and duplicate positional references" {
  let certificate = @sync.certificate_from_views(
    certificate_test_view(["a", "b", "c"], "q0"),
    certificate_test_view(["b", "a", "c"], "q1"),
    @sync.Completeness::Pending,
    "swap first two while preserving third",
  ).unwrap()
  let wrong_id = certificate.slots.copy()
  wrong_id[0] = @sync.PrefixSlotWitness::FromBefore(0)
  match @sync.verify_certificate({ ..certificate, slots: wrong_id, }) {
    Ok(_) => fail("a slot must reference the matching before ID")
    Err(reason) => assert_true(reason.contains("ID differs"))
  }
  let duplicate = certificate.slots.copy()
  duplicate[1] = @sync.PrefixSlotWitness::FromBefore(1)
  match @sync.verify_certificate({ ..certificate, slots: duplicate, }) {
    Ok(_) => fail("two result slots cannot consume one before position")
    Err(reason) => assert_true(reason.contains("reuse"))
  }
  let invented = certificate.slots.copy()
  invented[2] = @sync.PrefixSlotWitness::Introduced("c")
  match @sync.verify_certificate({ ..certificate, slots: invented, }) {
    Ok(_) => fail("an existing Email ID cannot claim an introduced slot")
    Err(reason) => assert_true(reason.contains("already exists"))
  }
  let outside = certificate.slots.copy()
  outside[2] = @sync.PrefixSlotWitness::FromBefore(3)
  match @sync.verify_certificate({ ..certificate, slots: outside, }) {
    Ok(_) => fail("a slot cannot read outside the bounded before prefix")
    Err(reason) => assert_true(reason.contains("out-of-range"))
  }
  match @sync.verify_certificate({ ..certificate, slots: [], }) {
    Ok(_) => fail("each result position requires one witness slot")
    Err(reason) => assert_true(reason.contains("slot count"))
  }
}

///|
fn certificate_test_ordered_subsets(
  prefix : Array[String],
  remaining : Array[String],
  output : Array[Array[String]],
) -> Unit {
  output.push(prefix.copy())
  for index, id in remaining {
    let next = prefix.copy()
    next.push(id)
    let rest = remaining.copy()
    let _ = rest.remove(index)
    certificate_test_ordered_subsets(next, rest, output)
  }
}

///|
test "certificate verifies all 4225 transitions of four unique ids" {
  let prefixes : Array[Array[String]] = []
  certificate_test_ordered_subsets([], ["a", "b", "c", "d"], prefixes)
  assert_eq(prefixes.length(), 65)
  let mut transitions = 0
  for before_ids in prefixes {
    for after_ids in prefixes {
      let certificate = @sync.certificate_from_views(
        certificate_test_view(before_ids, "q0"),
        certificate_test_view(after_ids, "q1"),
        @sync.Completeness::Pending,
        "exhaustive bounded prefix transition",
      ).unwrap()
      match @sync.verify_certificate(certificate) {
        Ok(_) => ()
        Err(reason) => fail(reason)
      }
      assert_eq(certificate.slots.length(), after_ids.length())
      for position, slot in certificate.slots {
        match slot {
          @sync.PrefixSlotWitness::FromBefore(origin) =>
            assert_eq(before_ids[origin], after_ids[position])
          @sync.PrefixSlotWitness::Introduced(id) =>
            assert_eq(id, after_ids[position])
        }
      }
      transitions = transitions + 1
    }
  }
  assert_eq(transitions, 4225)
}

///|
test "certificate rejects a stale state disappearance outside invalidation" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "state-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    query_state: None,
    completeness: @sync.Completeness::Pending,
  }
  let result = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::Pending,
    "unexpected state disappearance",
  )
  match result {
    Ok(_) => assert_true(false)
    Err(reason) => assert_true(reason.contains("not verifiable"))
  }
}

///|
test "certificate accepts query invalidation as an explicit boundary" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "invalidate-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  before.ordered_ids = ["a"]
  before.total = 1
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    query_state: None,
    query_valid: false,
    query_required: true,
    completeness: @sync.Completeness::NeedsRefresh,
  }
  let certificate = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::NeedsRefresh,
    "query history invalidated",
  ).unwrap()
  match certificate.kind {
    @sync.WitnessKind::QueryDelta => ()
    _ => assert_true(false)
  }
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(_) => assert_true(false)
  }
}

///|
test "email prefix coverage records an open same-state fill frontier" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "coverage-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    { ..@sync.default_limits(), prefix_limit: 3, },
    Some("e0"),
  )
  before.ordered_ids = ["a"]
  before.total = 3
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    ordered_ids: ["a", "b"],
    query_state: Some("q0"),
    completeness: @sync.Completeness::Pending,
  }
  let certificate = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::Pending,
    "same-state prefix fill",
  ).unwrap()
  assert_eq(certificate.coverage.start, 0)
  assert_eq(certificate.coverage.end, 2)
  assert_eq(certificate.coverage.target_end, 3)
  assert_eq(certificate.coverage.missing, 1)
  assert_true(certificate.coverage.frontier == @sync.PrefixFrontier::Open)
  assert_true(certificate.coverage.same_query_state_fill)
  assert_false(certificate.coverage.objects_complete)
  match @sync.verify_email_prefix_proof(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
}

///|
test "email prefix proof binds one planned JMAP request" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "binding-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let planned = @sync.plan(before)
  let after = {
    ..before,
    ordered_ids: ["a"],
    total: 1,
    query_state: Some("q0"),
    query_valid: true,
    query_required: false,
    completeness: @sync.Completeness::Pending,
  }
  let certificate = @sync.certificate_from_views_with_plan(
    before,
    after,
    @sync.Completeness::Pending,
    "initial Email/query page",
    planned,
  ).unwrap()
  match certificate.plan_binding {
    Some(binding) => {
      assert_true(binding.request.kind == @sync.RequestKind::Query)
      assert_eq(binding.request.ticket.generation, 0)
      assert_eq(binding.request.position, 0)
      assert_eq(binding.request.limit, 50)
      assert_true(binding.request == planned.requests[0])
      assert_true(binding.request.ticket.query == certificate.query)
    }
    None => assert_true(false)
  }
  match @sync.verify_email_prefix_proof(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
}

///|
test "email prefix proof rejects a copied request shape" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "binding-tamper-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let planned = @sync.plan(before)
  let after = {
    ..before,
    ordered_ids: ["a"],
    total: 1,
    query_state: Some("q0"),
    query_valid: true,
    query_required: false,
    completeness: @sync.Completeness::Pending,
  }
  let certificate = @sync.certificate_from_views_with_plan(
    before,
    after,
    @sync.Completeness::Pending,
    "initial Email/query page",
    planned,
  ).unwrap()
  let forged = match certificate.plan_binding {
    Some(binding) =>
      {
        ..certificate,
        plan_binding: Some({
          request: {
            ..binding.request,
            limit: binding.request.limit + 1,
            ticket: {
              ..binding.request.ticket,
              limit: binding.request.limit + 1,
            },
          },
        }),
      }
    None => certificate
  }
  match @sync.verify_email_prefix_proof(forged) {
    Ok(_) => assert_true(false)
    Err(reason) => assert_true(reason.contains("prefix frontier"))
  }
  let copied_page = match certificate.plan_binding {
    Some(binding) =>
      {
        ..certificate,
        plan_binding: Some({
          request: {
            ..binding.request,
            position: 1,
            limit: 49,
            ticket: { ..binding.request.ticket, position: 1, limit: 49, },
          },
        }),
      }
    None => certificate
  }
  match @sync.verify_email_prefix_proof(copied_page) {
    Ok(_) => assert_true(false)
    Err(reason) => assert_true(reason.contains("prefix frontier"))
  }
}

///|
test "Ready email prefix proof requires complete fixed projection" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "certificate-service",
    account_id: "ready-coverage-acc",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  before.ordered_ids = ["a"]
  before.total = 1
  before.query_state = Some("q0")
  before.query_valid = true
  before.query_required = false
  before.email_required = false
  let after = {
    ..before,
    query_state: Some("q1"),
    email_state: Some("e1"),
    completeness: @sync.Completeness::Ready,
  }
  let result = @sync.certificate_from_views(
    before,
    after,
    @sync.Completeness::Ready,
    "ready projection",
  )
  match result {
    Ok(_) => assert_true(false)
    Err(reason) => assert_true(reason.contains("incomplete object"))
  }
}

///|
fn certificate_test_bound_query(
  service : String,
  account_id : String,
) -> @sync.DecisionCertificate {
  let before = @sync.open_view(
    { service_identity: service, account_id, },
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let planned = @sync.plan(before)
  let after = {
    ..before,
    ordered_ids: ["a"],
    total: 1,
    query_state: Some("q0"),
    query_valid: true,
    query_required: false,
  }
  @sync.certificate_from_views_with_plan(
    before,
    after,
    @sync.Completeness::Pending,
    "typed Email/query binding",
    planned,
  ).unwrap()
}

///|
test "structured query identities cannot alias at delimiter boundaries" {
  let certificate = certificate_test_bound_query("service|part", "account")
  let other = certificate_test_bound_query("service", "part|account")
  // This is why canonical debug text is no longer used as identity.
  assert_eq(certificate.query.canonical(), other.query.canonical())
  assert_true(certificate.query != other.query)
  let forged = { ..certificate, plan_binding: other.plan_binding, }
  match @sync.verify_certificate(forged) {
    Ok(_) => fail("distinct structured account boundaries must not alias")
    Err(reason) => assert_true(reason.contains("structured query differs"))
  }
}

///|
test "typed plan binding rejects altered filter projection and ticket fields" {
  let certificate = certificate_test_bound_query(
    "shape-service", "shape-account",
  )
  let binding = certificate.plan_binding.unwrap()
  let request = binding.request
  let bad_requests : Array[@sync.Request] = [
    { ..request, filter: Some(@email.FilterSpec::InMailbox("another|inbox")), },
    { ..request, properties: ["id", "subject"], },
    { ..request, sort: None, },
    { ..request, kind: @sync.RequestKind::Get, },
    {
      ..request,
      ticket: {
        ..request.ticket,
        account: { service_identity: "other", account_id: "other", },
      },
    },
    {
      ..request,
      ticket: { ..request.ticket, expected_email_state: Some("another-state"), },
    },
    {
      ..request,
      max_changes: 1,
      ticket: { ..request.ticket, max_changes: 1, },
    },
    {
      ..request,
      ids: ["a"],
      ticket: { ..request.ticket, requested_ids: ["a"], },
    },
  ]
  for bad in bad_requests {
    match
      @sync.verify_certificate({
        ..certificate,
        plan_binding: Some({ request: bad, }),
      }) {
      Ok(_) => fail("a changed typed request field must be checked")
      Err(_) => ()
    }
  }
}

///|
test "typed get binding checks requested Email IDs against the bounded prefix" {
  let before = certificate_test_view(["a"], "q0")
  before.pending_get = ["a"]
  let planned = @sync.plan(before)
  assert_true(planned.requests[0].kind == @sync.RequestKind::Get)
  let certificate = @sync.certificate_from_views_with_plan(
    before,
    before,
    @sync.Completeness::Pending,
    "get one missing Email projection",
    planned,
  ).unwrap()
  let binding = certificate.plan_binding.unwrap()
  let request = binding.request
  let forged = {
    ..certificate,
    plan_binding: Some({
      request: {
        ..request,
        ids: ["z"],
        ticket: { ..request.ticket, requested_ids: ["z"], },
      },
    }),
  }
  match @sync.verify_certificate(forged) {
    Ok(_) => fail("get binding cannot fetch an ID outside its before prefix")
    Err(reason) => assert_true(reason.contains("outside the before prefix"))
  }
}

///|
test "bound constructor compares the complete request with the current planner" {
  let before = certificate_test_view(["a"], "q0")
  before.pending_get = ["a"]
  let planned = @sync.plan(before)
  let request = planned.requests[0]
  let forged : @sync.Plan = {
    ..planned,
    requests: [
      {
        ..request,
        ticket: { ..request.ticket, request_id: request.ticket.request_id + 1, },
      },
    ],
  }
  match
    @sync.certificate_from_views_with_plan(
      before,
      before,
      @sync.Completeness::Pending,
      "wrong request id despite a valid method shape",
      forged,
    ) {
    Ok(_) => fail("constructor must compare with the current view's request")
    Err(reason) => assert_true(reason.contains("current Email view"))
  }
  let certificate = @sync.certificate_from_views_with_plan(
    before,
    before,
    @sync.Completeness::Pending,
    "detached typed request arrays",
    planned,
  ).unwrap()
  request.ids[0] = "tampered-after-construction"
  request.properties[0] = "tampered-property"
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
}

///|
test "bound Get NotFound certificate retains its explicit query invalidation" {
  let before = certificate_test_view(["a"], "q0")
  before.pending_get = ["a"]
  let planned = @sync.plan(before)
  assert_true(planned.requests[0].kind == @sync.RequestKind::Get)
  // Keep the immutable certificate input separate from the mutable sync view.
  let accepted = @sync.accept_response(
    { ..before, },
    planned.requests[0].ticket,
    @sync.ServerResponse::Error(@sync.ResponseError::NotFound),
  )
  let after = match accepted {
    @sync.Acceptance::NeedsRefresh(result) => result.view
    _ =>
      fail("NotFound on the current Get must explicitly invalidate the query")
  }
  assert_true(after.query_state is None)
  assert_true(after.ordered_ids == before.ordered_ids)
  assert_eq(after.total, before.total)
  let certificate = @sync.certificate_from_views_with_plan(
    before,
    after,
    after.completeness,
    "Email/get NotFound invalidated the unavailable query snapshot",
    planned,
  ).unwrap()
  match @sync.verify_certificate(certificate) {
    Ok(_) => ()
    Err(reason) => fail(reason)
  }
  // Invalidation clears a token; it never grants permission to replace it.
  match
    @sync.verify_certificate({ ..certificate, query_state_after: Some("q1"), }) {
    Ok(_) => fail("a failed Get cannot install a different queryState")
    Err(reason) => assert_true(reason.contains("cannot replace queryState"))
  }
  match
    @sync.certificate_from_views_with_plan(
      before,
      { ..before, query_state: Some("q1"), },
      @sync.Completeness::Pending,
      "forged successful Get queryState change",
      planned,
    ) {
    Ok(_) => fail("a normal Get cannot advance the queryState")
    Err(reason) => assert_true(reason.contains("cannot replace queryState"))
  }
}
