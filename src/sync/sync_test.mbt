///|
/// Transport-free tests for the ticket and state boundary. The independent
/// Python oracle covers larger mutation combinations in tests/verify.py.
test "open view emits a bounded query plan" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "acc-1",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let next = @sync.plan(view)
  assert_eq(next.requests.length(), 1)
  assert_true(next.requests[0].kind == @sync.RequestKind::Query)
  assert_eq(next.requests[0].position, 0)
  assert_eq(next.requests[0].limit, 50)
  assert_eq(next.requests[0].ticket.generation, 0)
}

///|
test "query response preserves order and schedules the object chain" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "acc-1",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 2,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 2,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  let first = @sync.plan(view).requests[0]
  let response = @sync.ServerResponse::QueryResult({
    ids: ["b", "a"],
    total: 2,
    state: "q0",
    bytes: 12,
  })
  let result = @sync.accept_response(view, first.ticket, response)
  match result {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.ordered_ids, ["b", "a"])
      assert_eq(next.plan.requests.length(), 1)
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::Changes)
    }
    @sync.Acceptance::ProtocolFailure(reason) => fail(reason.reason)
    @sync.Acceptance::Dropped(reason) => fail(reason.reason)
    _ => assert_true(false)
  }
}

///|
test "late generation response is dropped without mutation" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "acc-1",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Unread("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let old_ticket = @sync.plan(view).requests[0].ticket
  let stale_ticket : @sync.RequestTicket = { ..old_ticket, generation: 1, }
  let result = @sync.accept_response(
    view,
    stale_ticket,
    @sync.ServerResponse::QueryResult({
      ids: [],
      total: 0,
      state: "q1",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Dropped(reason) =>
      assert_true(reason.reason.contains("older"))
    _ => assert_true(false)
  }
}

///|
test "refresh returns the new generation view and accepts its plan" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "acc-1",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let started = @sync.refresh(view)
  assert_eq(started.view.generation, view.generation + 1)
  assert_eq(started.plan.requests.length(), 1)
  let resumed = @sync.resume_with_email_state(view, "e1")
  assert_eq(resumed.view.generation, view.generation + 1)
  assert_eq(resumed.plan.requests.length(), 1)
  let ticket = started.plan.requests[0].ticket
  assert_eq(ticket.generation, started.view.generation)
  match
    @sync.accept_response(
      view,
      ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Dropped(reason) =>
      assert_true(reason.reason.contains("older"))
    _ => assert_true(false)
  }
  match
    @sync.accept_response(
      started.view,
      ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) =>
      assert_eq(next.view.generation, started.view.generation)
    @sync.Acceptance::Commit(next) =>
      assert_eq(next.view.generation, started.view.generation)
    @sync.Acceptance::Pending(next) =>
      assert_eq(next.view.generation, started.view.generation)
    @sync.Acceptance::Dropped(reason) => fail(reason.reason)
    @sync.Acceptance::NeedsRefresh(reason) => fail(reason.reason)
    @sync.Acceptance::Unsupported(reason) => fail(reason.reason)
    @sync.Acceptance::ProtocolFailure(reason) => fail(reason.reason)
  }
}

///|
test "generation increment is checked at the Int boundary" {
  match @sync.checked_next_generation(@int.MAX_VALUE) {
    Err(reason) => assert_true(reason.contains("overflow"))
    Ok(_) => assert_true(false)
  }
  match @sync.checked_next_generation(-1) {
    Err(reason) => assert_true(reason.contains("non-negative"))
    Ok(_) => assert_true(false)
  }
  match @sync.checked_next_generation(@int.MAX_VALUE - 1) {
    Ok(next) => assert_eq(next, @int.MAX_VALUE)
    Err(_) => assert_true(false)
  }
}

///|
test "refresh and resume expose generation overflow as protocol failure" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "overflow-acc",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  view.generation = @int.MAX_VALUE
  match @sync.begin_refresh_checked(view) {
    Err(reason) => {
      assert_eq(reason.view.generation, @int.MAX_VALUE)
      assert_true(
        reason.view.completeness == @sync.Completeness::ProtocolFailure,
      )
      assert_true(reason.reason.contains("overflow"))
    }
    Ok(_) => assert_true(false)
  }
  let refresh = @sync.begin_refresh(view)
  assert_eq(refresh.view.generation, @int.MAX_VALUE)
  assert_true(refresh.view.completeness == @sync.Completeness::ProtocolFailure)
  assert_eq(refresh.plan.requests.length(), 0)
  let old_ticket = @sync.plan(view).requests[0].ticket
  match
    @sync.accept_response(
      refresh.view,
      old_ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::ProtocolFailure(reason) =>
      assert_true(reason.reason.contains("protocol-failed"))
    _ => assert_true(false)
  }
  match @sync.begin_resume_with_email_state_checked(view, "e1") {
    Err(reason) => {
      assert_eq(reason.view.generation, @int.MAX_VALUE)
      assert_true(
        reason.view.completeness == @sync.Completeness::ProtocolFailure,
      )
      assert_true(reason.reason.contains("overflow"))
    }
    Ok(_) => assert_true(false)
  }
  let resumed = @sync.begin_resume_with_email_state(view, "e1")
  assert_eq(resumed.view.generation, @int.MAX_VALUE)
  assert_true(resumed.view.completeness == @sync.Completeness::ProtocolFailure)
  assert_eq(resumed.plan.requests.length(), 0)
}

///|
test "query response keeps the returned order" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "acc-1",
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
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  let ticket = @sync.plan(view).requests[0].ticket
  let result = @sync.accept_response(
    view,
    ticket,
    @sync.ServerResponse::QueryResult({
      ids: ["c", "a", "b"],
      total: 3,
      state: "q0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Continue(next) =>
      assert_eq(next.view.ordered_ids, ["c", "a", "b"])
    _ => assert_true(false)
  }
}

///|
test "empty Email baseline is established by an empty get" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "empty-acc",
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
    @email.ViewSpec::Latest("inbox"),
    limits,
    None,
  )
  let query_ticket = @sync.plan(view).requests[0].ticket
  let after_query = @sync.accept_response(
    view,
    query_ticket,
    @sync.ServerResponse::QueryResult({
      ids: [],
      total: 0,
      state: "q0",
      bytes: 1,
    }),
  )
  match after_query {
    @sync.Acceptance::Continue(next) => {
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::Get)
      assert_eq(next.plan.requests[0].ids, [])
      let after_get = @sync.accept_response(
        next.view,
        next.plan.requests[0].ticket,
        @sync.ServerResponse::GetResult({
          list: [],
          not_found: [],
          state: "e0",
          bytes: 1,
        }),
      )
      match after_get {
        @sync.Acceptance::Commit(done) => {
          assert_true(done.checkpoint.completeness == @sync.Completeness::Ready)
          assert_eq(done.checkpoint.email_state, Some("e0"))
          assert_eq(done.checkpoint.query_state, Some("q0"))
          assert_eq(done.checkpoint.pending_ids, [])
        }
        _ => assert_true(false)
      }
    }
    _ => assert_true(false)
  }
}

///|
test "query history invalidation keeps the bad token out of the pending checkpoint" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "history-acc",
  }
  let mut view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  // Establish a valid query token, then ask explicitly for a query delta.
  let first = @sync.plan(view).requests[0]
  let first_result = @sync.accept_response(
    view,
    first.ticket,
    @sync.ServerResponse::QueryResult({
      ids: ["a"],
      total: 1,
      state: "q0",
      bytes: 1,
    }),
  )
  match first_result {
    @sync.Acceptance::Continue(next) => view = next.view
    _ => assert_true(false)
  }
  // The first query normally asks for the Email baseline. Mark that work as
  // already supplied so this test targets queryChanges directly.
  view.email_required = false
  view.email_valid = true
  view.query_required = true
  view.query_valid = true
  let query_changes = @sync.plan(view)
  assert_true(query_changes.requests[0].kind == @sync.RequestKind::QueryChanges)
  let result = @sync.accept_response(
    view,
    query_changes.requests[0].ticket,
    @sync.ServerResponse::Error(@sync.ResponseError::CannotCalculateChanges),
  )
  match result {
    @sync.Acceptance::NeedsRefresh(next) => {
      assert_true(next.view.completeness == @sync.Completeness::NeedsRefresh)
      assert_eq(next.view.query_state, None)
      assert_true(next.view.query_required)
      assert_true(!next.view.query_valid)
      assert_true(
        next.progress.checkpoint.completeness ==
        @sync.Completeness::NeedsRefresh,
      )
      assert_eq(next.progress.checkpoint.query_state, None)
    }
    _ => assert_true(false)
  }
}

///|
test "Email history invalidation clears only Email progress" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "email-history-acc",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = true
  let changes = @sync.plan(view)
  assert_true(changes.requests[0].kind == @sync.RequestKind::Changes)
  let result = @sync.accept_response(
    view,
    changes.requests[0].ticket,
    @sync.ServerResponse::Error(@sync.ResponseError::CannotCalculateChanges),
  )
  match result {
    @sync.Acceptance::NeedsRefresh(next) => {
      assert_eq(next.view.email_state, None)
      assert_true(!next.view.email_valid)
      assert_eq(next.view.query_state, Some("q0"))
      assert_true(next.view.query_valid)
      // The valid query token is retained, but the ordering must be
      // reconciled after a fresh Email baseline.
      assert_true(next.progress.query_required)
    }
    _ => assert_true(false)
  }
}

///|
test "Email history invalidation checkpoint remains resumable with a fresh baseline" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "restore-email-history-service",
    account_id: "restore-email-history-account",
  }
  let limits = @sync.default_limits()
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = true
  let request = @sync.plan(view).requests[0]
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::Error(@sync.ResponseError::CannotCalculateChanges),
  )
  match result {
    @sync.Acceptance::NeedsRefresh(next) => {
      assert_eq(next.progress.checkpoint.email_state, None)
      match @sync.restore_checkpoint(next.progress.checkpoint, limits) {
        Ok(restored) => {
          assert_true(restored.completeness == @sync.Completeness::NeedsRefresh)
          let resumed = @sync.begin_resume_with_email_state(restored, "e2")
          assert_true(resumed.view.query_required)
          assert_true(
            resumed.plan.requests[0].kind == @sync.RequestKind::QueryChanges,
          )
        }
        Err(reason) => fail(reason)
      }
    }
    _ => assert_true(false)
  }
}

///|
test "Email history invalidation keeps a fresh baseline and prefix refetch plan" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "email-history-plan-service",
    account_id: "email-history-plan-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 2,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 2,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a", "b"]
  view.total = 2
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = true
  view.email_valid = true
  let changes = @sync.plan(view).requests[0]
  let result = @sync.accept_response(
    view,
    changes.ticket,
    @sync.ServerResponse::Error(@sync.ResponseError::CannotCalculateChanges),
  )
  match result {
    @sync.Acceptance::NeedsRefresh(next) => {
      assert_true(next.view.email_required)
      assert_eq(next.view.email_state, None)
      assert_eq(next.view.pending_get, ["a", "b"])
      assert_eq(next.progress.checkpoint.pending_ids, ["a", "b"])
      let baseline = @sync.plan(next.view)
      assert_eq(baseline.requests.length(), 1)
      assert_true(baseline.requests[0].kind == @sync.RequestKind::Get)
      assert_eq(baseline.requests[0].ids, [])
      let after_baseline = @sync.accept_response(
        next.view,
        baseline.requests[0].ticket,
        @sync.ServerResponse::GetResult({
          list: [],
          not_found: [],
          state: "e1",
          bytes: 1,
        }),
      )
      match after_baseline {
        @sync.Acceptance::Continue(cont) => {
          // The retained queryState is reconciled before refetching the
          // prefix objects, so membership/sort changes during the invalid
          // Email history window cannot be hidden.
          assert_true(
            cont.plan.requests[0].kind == @sync.RequestKind::QueryChanges,
          )
          let after_query = @sync.accept_response(
            cont.view,
            cont.plan.requests[0].ticket,
            @sync.ServerResponse::QueryChangesResult({
              removed: [],
              added: [],
              total: 2,
              old_state: "q0",
              new_state: "q1",
              bytes: 1,
            }),
          )
          match after_query {
            @sync.Acceptance::Continue(done) => {
              assert_true(done.plan.requests[0].kind == @sync.RequestKind::Get)
              assert_eq(done.plan.requests[0].ids, ["a", "b"])
            }
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
test "Email changes hasMore keeps the second page on the Changes method" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "paged-acc",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = true
  let first = @sync.plan(view).requests[0]
  let first_result = @sync.accept_response(
    view,
    first.ticket,
    @sync.ServerResponse::EmailChangesResult({
      created: [],
      destroyed: [],
      updated: [],
      old_state: "e0",
      new_state: "e1",
      has_more_changes: true,
      bytes: 1,
    }),
  )
  match first_result {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.email_state, Some("e1"))
      assert_true(next.view.email_required)
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::Changes)
      let second_result = @sync.accept_response(
        next.view,
        next.plan.requests[0].ticket,
        @sync.ServerResponse::EmailChangesResult({
          created: [],
          destroyed: [],
          updated: [],
          old_state: "e1",
          new_state: "e2",
          has_more_changes: false,
          bytes: 1,
        }),
      )
      match second_result {
        @sync.Acceptance::Continue(done) => {
          assert_eq(done.view.email_state, Some("e2"))
          assert_true(
            done.plan.requests[0].kind == @sync.RequestKind::QueryChanges,
          )
        }
        _ => assert_true(false)
      }
    }
    _ => assert_true(false)
  }
}

///|
test "Email changes plan and checkpoint enforce cumulative maxChanges" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "changes-budget-service",
    account_id: "changes-budget-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 1,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 1,
    max_changes: 1,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = true
  let first = @sync.plan(view).requests[0]
  assert_true(first.kind == @sync.RequestKind::Changes)
  assert_eq(first.limit, 1)
  assert_eq(first.max_changes, 1)
  assert_eq(first.ticket.max_changes, 1)
  let result = @sync.accept_response(
    view,
    first.ticket,
    @sync.ServerResponse::EmailChangesResult({
      created: [],
      destroyed: [],
      updated: ["a"],
      old_state: "e0",
      new_state: "e1",
      has_more_changes: true,
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Pending(done) => {
      assert_eq(done.view.changes_seen, 1)
      assert_true(done.view.email_required)
      assert_true(done.reason.contains("change"))
      assert_eq(done.checkpoint.changes_seen, 1)
      assert_eq(done.checkpoint.email_state, Some("e1"))
      assert_eq(@sync.plan(done.view).requests.length(), 0)
      match @sync.restore_checkpoint(done.checkpoint, limits) {
        Ok(restored) => {
          assert_eq(restored.changes_seen, 1)
          assert_eq(@sync.plan(restored).requests.length(), 0)
        }
        Err(reason) => fail(reason)
      }
      let larger_limits = { ..limits, max_changes: 2, }
      match @sync.restore_checkpoint(done.checkpoint, larger_limits) {
        Ok(restored) => {
          let resumed_plan = @sync.plan(restored)
          assert_eq(resumed_plan.requests.length(), 1)
          assert_true(
            resumed_plan.requests[0].kind == @sync.RequestKind::Changes,
          )
          assert_eq(resumed_plan.requests[0].max_changes, 1)
        }
        Err(reason) => fail(reason)
      }
      let forged_view = @sync.open_view(
        account,
        @email.ViewSpec::Latest("inbox"),
        limits,
        Some("e0"),
      )
      forged_view.query_state = Some("q0")
      forged_view.query_valid = true
      forged_view.query_required = false
      forged_view.email_required = true
      let forged_ticket = @sync.plan(forged_view).requests[0].ticket
      match
        @sync.accept_response(
          forged_view,
          forged_ticket,
          @sync.ServerResponse::EmailChangesResult({
            created: [],
            destroyed: [],
            updated: ["a", "b"],
            old_state: "e0",
            new_state: "e1",
            has_more_changes: true,
            bytes: 1,
          }),
        ) {
        @sync.Acceptance::ProtocolFailure(reason) =>
          assert_true(reason.reason.contains("budget"))
        _ => assert_true(false)
      }
    }
    _ => assert_true(false)
  }
}

///|
test "Email object changes schedule query reconciliation before get" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "email-object-query-service",
    account_id: "email-object-query-account",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 1,
    max_rounds: 8,
    max_bytes: 10000,
    max_objects_per_get: 1,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a"]
  view.total = 1
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_valid = true
  view.email_required = true
  let changes = @sync.plan(view).requests[0]
  let result = @sync.accept_response(
    view,
    changes.ticket,
    @sync.ServerResponse::EmailChangesResult({
      created: [],
      destroyed: [],
      updated: ["a"],
      old_state: "e0",
      new_state: "e1",
      has_more_changes: false,
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Continue(next) => {
      assert_true(next.view.query_required)
      assert_eq(next.view.pending_get, ["a"])
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::QueryChanges)
      assert_eq(next.plan.requests[0].ticket.expected_query_state, Some("q0"))
    }
    _ => assert_true(false)
  }
}

///|
test "destroyed wins over updated for an Email/changes page" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "destroyed-acc",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.ordered_ids = ["gone"]
  view.total = 1
  view.objects = [@email.EmailRecord::empty("gone")]
  view.email_required = true
  let first = @sync.plan(view).requests[0]
  let query_result = @sync.accept_response(
    view,
    first.ticket,
    @sync.ServerResponse::EmailChangesResult({
      created: [],
      updated: ["gone"],
      destroyed: ["gone"],
      old_state: "e0",
      new_state: "e1",
      has_more_changes: true,
      bytes: 1,
    }),
  )
  match query_result {
    @sync.Acceptance::Continue(next) => {
      assert_true(!next.view.objects.map(fn(item) { item.id }).contains("gone"))
      assert_eq(next.view.pending_get.length(), 0)
    }
    @sync.Acceptance::ProtocolFailure(reason) => fail(reason.reason)
    @sync.Acceptance::Dropped(reason) => fail(reason.reason)
    _ => assert_true(false)
  }
}

///|
test "pending checkpoint carries incompleteness and resume work" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "budget-acc",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 2,
    max_rounds: 8,
    max_bytes: 1,
    max_objects_per_get: 2,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  let ticket = @sync.plan(view).requests[0].ticket
  let result = @sync.accept_response(
    view,
    ticket,
    @sync.ServerResponse::QueryResult({
      ids: ["a", "b"],
      total: 2,
      state: "q0",
      bytes: 2,
    }),
  )
  match result {
    @sync.Acceptance::Pending(next) => {
      assert_true(next.checkpoint.completeness == @sync.Completeness::Pending)
      assert_true(next.checkpoint.pending_reason is Some(_))
      assert_true(
        next.checkpoint.query_required || next.checkpoint.email_required,
      )
    }
    _ => assert_true(false)
  }
}

///|
test "incomplete EmailRecord cannot produce Ready" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "incomplete-record-acc",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  // Set up a fully valid query/Email baseline with one object fetch pending.
  // The response intentionally carries only the ID projection; the core must
  // keep that object pending instead of committing a false Ready checkpoint.
  view.ordered_ids = ["a"]
  view.total = 1
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.query_fill_required = false
  view.email_required = false
  view.email_valid = true
  view.pending_get = ["a"]
  let request = @sync.plan(view).requests[0]
  assert_true(request.kind == @sync.RequestKind::Get)
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::GetResult({
      list: [@email.EmailRecord::empty("a")],
      not_found: [],
      state: "e0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Continue(next) => {
      assert_true(next.view.completeness == @sync.Completeness::Pending)
      assert_eq(next.view.objects.length(), 1)
      assert_true(!next.view.objects[0].is_complete())
      assert_eq(next.plan.requests.length(), 1)
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::Get)
      assert_eq(next.plan.requests[0].ids, ["a"])
    }
    @sync.Acceptance::Commit(_) => assert_true(false)
    @sync.Acceptance::Pending(next) =>
      fail("unexpected Pending: " + next.reason)
    @sync.Acceptance::ProtocolFailure(reason) => fail(reason.reason)
    @sync.Acceptance::Unsupported(reason) => fail(reason.reason)
    @sync.Acceptance::NeedsRefresh(next) => fail(next.reason)
    @sync.Acceptance::Dropped(reason) => fail(reason.reason)
  }
}

///|
test "Email/get cannot omit a requested id and reuse a stale cached object" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "omitted-get-service",
    account_id: "omitted-get-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let record : @email.EmailRecord = {
    id: "a",
    thread_id: "thread-a",
    mailbox_ids: Some([]),
    keywords: Some([]),
    received_at: Some("2026-10-25T00:00:00Z"),
    subject: Some("old subject"),
    from: Some([]),
    preview: Some("old preview"),
  }
  view.ordered_ids = ["a"]
  view.total = 1
  view.objects = [record]
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.query_fill_required = false
  view.email_valid = true
  view.email_required = false
  view.pending_get = ["a"]
  let request = @sync.plan(view).requests[0]
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::GetResult({
      list: [],
      not_found: [],
      state: "e0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::ProtocolFailure(reason) =>
      assert_true(reason.reason.contains("omitted a requested id"))
    _ => assert_true(false)
  }
}

///|
test "Ready checkpoint must contain every complete prefix object" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "test-service",
    account_id: "forged-ready-acc",
  }
  let limits = @sync.default_limits()
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a"]
  view.total = 1
  view.query_state = Some("q0")
  view.email_state = Some("e0")
  view.query_valid = true
  view.email_valid = true
  view.query_required = false
  view.email_required = false
  view.query_fill_required = false
  view.pending_get = []
  view.completeness = @sync.Completeness::Ready
  let forged = { ..@sync.checkpoint(view), objects: [], }
  match @sync.restore_checkpoint(forged, limits) {
    Err(reason) => assert_true(reason.contains("incomplete object"))
    Ok(_) => assert_true(false)
  }
}

///|
test "restore rejects a pending checkpoint without a required query state" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "restore-shape-service",
    account_id: "restore-shape-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  // This shape cannot be produced by a valid query response: the caller says
  // no query work remains while the checkpoint carries no queryState. Without
  // restore validation it would be re-planned as a prefix fill with no
  // expected state and every response would fail at the acceptance boundary.
  view.query_required = false
  view.query_valid = false
  let saved = @sync.checkpoint(view)
  match @sync.restore_checkpoint(saved, @sync.default_limits()) {
    Err(reason) => assert_true(reason.contains("queryState"))
    Ok(_) => assert_true(false)
  }
}

///|
test "restore rejects checkpoints outside the fixed view contract" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "restore-contract-service",
    account_id: "restore-contract-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let base = @sync.checkpoint(view)
  let bad_query = { ..base.query, collapse_threads: true, }
  let bad = { ..base, query: bad_query, }
  match @sync.restore_checkpoint(bad, @sync.default_limits()) {
    Err(reason) => assert_true(reason.contains("collapseThreads"))
    Ok(_) => assert_true(false)
  }
  let bad_ids = { ..base, ordered_ids: [""], }
  match @sync.restore_checkpoint(bad_ids, @sync.default_limits()) {
    Err(reason) => assert_true(reason.contains("ordered prefix"))
    Ok(_) => assert_true(false)
  }
}

///|
test "restore upgrades a budget-pending complete checkpoint to Ready" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "restore-budget-service",
    account_id: "restore-budget-account",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let record : @email.EmailRecord = {
    id: "a",
    thread_id: "thread-a",
    mailbox_ids: Some([]),
    keywords: Some([]),
    received_at: Some("2026-10-25T00:00:00Z"),
    subject: Some("subject"),
    from: Some([]),
    preview: Some("preview"),
  }
  view.ordered_ids = ["a"]
  view.total = 1
  view.objects = [record]
  view.query_state = Some("q0")
  view.email_state = Some("e0")
  view.query_valid = true
  view.email_valid = true
  view.query_required = false
  view.email_required = false
  view.query_fill_required = false
  view.pending_get = []
  view.completeness = @sync.Completeness::Pending
  let saved = @sync.checkpoint(view)
  match @sync.restore_checkpoint(saved, @sync.default_limits()) {
    Ok(restored) =>
      assert_true(restored.completeness == @sync.Completeness::Ready)
    Err(reason) => fail(reason)
  }
}

///|
test "capability projection rejects unsupported fixed query semantics" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "capability-service",
    account_id: "capability-account",
  }
  let capabilities : @sync.CapabilityProjection = @sync.CapabilityProjection::{
    supports_filter: false,
    supports_sort: true,
    supports_query_changes: true,
    supports_email_changes: true,
    supports_result_reference: false,
    max_objects_per_get: 10,
    max_calls_in_request: 1,
  }
  match
    @sync.open_view_with_capabilities(
      account,
      @email.ViewSpec::Latest("inbox"),
      capabilities,
      @sync.default_limits(),
      None,
    ) {
    @sync.OpenViewResult::Unsupported(reason) =>
      assert_eq(reason, "fixed_query_projection_not_supported")
    _ => assert_true(false)
  }
}

///|
test "capability object limit constrains the view planner" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "capability-service",
    account_id: "bounded-account",
  }
  let capabilities : @sync.CapabilityProjection = @sync.CapabilityProjection::{
    supports_filter: true,
    supports_sort: true,
    supports_query_changes: true,
    supports_email_changes: true,
    supports_result_reference: false,
    max_objects_per_get: 1,
    max_calls_in_request: 1,
  }
  match
    @sync.open_view_with_capabilities(
      account,
      @email.ViewSpec::Latest("inbox"),
      capabilities,
      @sync.default_limits(),
      Some("e0"),
    ) {
    @sync.OpenViewResult::Accepted(view) => {
      assert_eq(view.limits.max_objects_per_get, 1)
      let request = @sync.plan(view).requests[0]
      assert_true(request.kind == @sync.RequestKind::Query)
    }
    _ => assert_true(false)
  }
}

///|
test "final response at byte budget remains Pending" {
  let account : @sync.AccountScope = @sync.AccountScope::{
    service_identity: "budget-service",
    account_id: "final-byte-budget",
  }
  let limits : @sync.Limits = @sync.Limits::{
    prefix_limit: 1,
    max_rounds: 8,
    max_bytes: 1,
    max_objects_per_get: 1,
    max_changes: 500,
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    limits,
    Some("e0"),
  )
  view.ordered_ids = ["a"]
  view.total = 1
  view.query_state = Some("q0")
  view.query_valid = true
  view.email_valid = true
  view.query_required = false
  view.email_required = false
  view.query_fill_required = false
  view.pending_get = ["a"]
  let request = @sync.plan(view).requests[0]
  let record : @email.EmailRecord = {
    id: "a",
    thread_id: "thread-a",
    mailbox_ids: Some([]),
    keywords: Some([]),
    received_at: Some("2026-10-25T00:00:00Z"),
    subject: Some("subject"),
    from: Some([]),
    preview: Some("preview"),
  }
  let result = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::GetResult({
      list: [record],
      not_found: [],
      state: "e0",
      bytes: 1,
    }),
  )
  match result {
    @sync.Acceptance::Pending(next) =>
      assert_eq(next.reason, "byte budget exhausted")
    @sync.Acceptance::Commit(_) => assert_true(false)
    _ => assert_true(false)
  }
}
