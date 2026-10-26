///|
test "queryChanges rejects an insertion index outside total" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "edge-service",
    account_id: "edge-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 3,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 3,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.Latest("inbox"),
    limits,
    Some("e0"),
  )
  let query_request = @sync.plan(view).requests[0]
  let after_query = @sync.accept_response(
    view,
    query_request.ticket,
    @sync.ServerResponse::QueryResult({
      ids: ["a"],
      total: 1,
      state: "q0",
      bytes: 1,
    }),
  )
  match after_query {
    @sync.Acceptance::Continue(next) => {
      let after_email = @sync.accept_response(
        next.view,
        next.plan.requests[0].ticket,
        @sync.ServerResponse::EmailChangesResult({
          created: [],
          destroyed: [],
          updated: [],
          old_state: "e0",
          new_state: "e1",
          has_more_changes: false,
          bytes: 1,
        }),
      )
      match after_email {
        @sync.Acceptance::Continue(next2) => {
          let invalid = @sync.accept_response(
            next2.view,
            next2.plan.requests[0].ticket,
            @sync.ServerResponse::QueryChangesResult({
              removed: [],
              added: [{ id: "x", index: 4, }],
              total: 1,
              old_state: "q0",
              new_state: "q1",
              bytes: 1,
            }),
          )
          match invalid {
            @sync.Acceptance::ProtocolFailure(_) => ()
            _ => assert_true(false)
          }
        }
        _ => assert_true(false)
      }
    }
    _ => assert_true(false)
  }
}

///|
test "query fill rejects an ID already present in the prefix" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "edge-service",
    account_id: "fill-overlap-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 3,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 3,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a"]
  view.total = 2
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.query_fill_required = true
  view.query_fill_position = 1
  view.email_required = false
  view.email_valid = true
  let request = @sync.plan(view).requests[0]
  assert_true(request.kind == @sync.RequestKind::Query)
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::QueryResult({
      ids: ["a"],
      total: 2,
      state: "q0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(_) => ()
    _ => assert_true(false)
  }
}

///|
test "query fill rejects an empty page that cannot make progress" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "edge-service",
    account_id: "fill-empty-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 3,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 3,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a"]
  view.total = 3
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.query_fill_required = true
  view.query_fill_position = 1
  view.email_required = false
  view.email_valid = true
  let request = @sync.plan(view).requests[0]
  assert_true(request.kind == @sync.RequestKind::Query)
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::QueryResult({
      ids: [],
      total: 3,
      state: "q0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(reason) =>
      assert_true(reason.reason.contains("no ids"))
    _ => assert_true(false)
  }
}

///|
test "initial query rejects an empty page before the reported total" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "edge-service",
    account_id: "initial-empty-page-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 3,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 3,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.Latest("inbox"),
    limits,
    Some("e0"),
  )
  let request = @sync.plan(view).requests[0]
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::QueryResult({
      ids: [],
      total: 3,
      state: "q0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(reason) =>
      assert_true(reason.reason.contains("no ids"))
    _ => assert_true(false)
  }
}
