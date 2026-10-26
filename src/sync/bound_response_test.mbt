///|
/// Tests for the account-bound typed response bridge.  Legacy response
/// literals remain covered by sync_test; these cases prove that a wire
/// adapter cannot accidentally apply another account's response.
test "typed query envelope records canCalculateChanges=false" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "typed-service",
    account_id: "typed-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let request = @sync.plan(view).requests[0]
  let data : @sync.QueryData = @sync.QueryData::{
    ids: ["a"],
    total: 1,
    state: "q0",
    bytes: 1,
  }
  let envelope = match
    @sync.QueryResponseEnvelope::new("typed-account", data, Some(false)) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let result = @sync.accept_bound_response(
    view,
    request.ticket,
    @sync.BoundServerResponse::QueryResult(envelope),
  )
  match result {
    @sync.Acceptance::Continue(next) => {
      assert_true(!next.view.query_changes_allowed)
      // A later generation must rebuild the query instead of emitting a
      // queryChanges request for a query that advertised false.
      let refreshed = @sync.begin_refresh(next.view)
      assert_eq(refreshed.plan.requests.length(), 1)
      assert_true(refreshed.plan.requests[0].kind == @sync.RequestKind::Query)
    }
    @sync.Acceptance::ProtocolFailure(reason) => fail(reason.reason)
    @sync.Acceptance::Dropped(reason) => fail(reason.reason)
    _ => assert_true(false)
  }
}

///|
test "typed response rejects account mismatch before state mutation" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "typed-service",
    account_id: "typed-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let request = @sync.plan(view).requests[0]
  let envelope = match
    @sync.QueryResponseEnvelope::new(
      "other-account",
      @sync.QueryData::{ ids: [], total: 0, state: "q0", bytes: 1, },
      None,
    ) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let result = @sync.accept_bound_response(
    view,
    request.ticket,
    @sync.BoundServerResponse::QueryResult(envelope),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(reason) => {
      assert_true(reason.reason.contains("accountId"))
      assert_eq(reason.view.next_request_id, view.next_request_id)
    }
    _ => assert_true(false)
  }
}

///|
test "typed query capability is not recorded from a forged ticket" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "typed-service",
    account_id: "typed-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let request = @sync.plan(view).requests[0]
  let forged : @sync.RequestTicket = {
    ..request.ticket,
    request_id: request.ticket.request_id + 1,
  }
  let envelope = match
    @sync.QueryResponseEnvelope::new(
      "typed-account",
      @sync.QueryData::{ ids: [], total: 0, state: "q0", bytes: 1, },
      Some(false),
    ) {
    Ok(value) => value
    Err(reason) => fail(reason)
  }
  let result = @sync.accept_bound_response(
    view,
    forged,
    @sync.BoundServerResponse::QueryResult(envelope),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(reason) =>
      assert_true(reason.view.query_changes_allowed)
    _ => assert_true(false)
  }
}

///|
test "typed envelope constructor rejects an empty account id" {
  let result = @sync.QueryResponseEnvelope::new(
    "",
    @sync.QueryData::{ ids: [], total: 0, state: "q0", bytes: 0, },
    None,
  )
  match result {
    Err(reason) => assert_true(reason.contains("account_id"))
    Ok(_) => assert_true(false)
  }
}
