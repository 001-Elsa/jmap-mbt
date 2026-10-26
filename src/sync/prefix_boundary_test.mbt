///|
/// Regression inputs use only synthetic IDs and states. RFC 8620 sections
/// 5.5/5.6 bound query pages and define queryChanges as remove, then insert
/// in ascending final-index order, then truncate to the new total.
fn boundary_view(
  ids : Array[String],
  total : Int32,
  prefix_limit : Int32,
) -> @sync.EmailView {
  let view = @sync.open_view(
    { service_identity: "boundary-service", account_id: "boundary-account", },
    @email.Latest("inbox"),
    { ..@sync.default_limits(), prefix_limit, },
    Some("e0"),
  )
  view.ordered_ids = ids
  view.total = total
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_valid = true
  view.email_required = false
  view
}

///|
fn boundary_fresh_view(prefix_limit : Int32) -> @sync.EmailView {
  let view = boundary_view([], 0, prefix_limit)
  view.query_state = None
  view.query_valid = false
  view.query_required = true
  view
}

///|
fn boundary_expect_failure(
  result : @sync.Acceptance,
  fragment : String,
) -> Unit raise {
  match result {
    @sync.Acceptance::ProtocolFailure(failed) =>
      assert_true(failed.reason.contains(fragment))
    _ => fail("expected ProtocolFailure containing: " + fragment)
  }
}

///|
test "query rejects more IDs than its requested limit before truncation" {
  let view = boundary_fresh_view(2)
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: ["a", "b", "c"],
        total: 3,
        state: "q0",
        bytes: 1,
      }),
    ),
    "requested limit",
  )
  assert_eq(view.ordered_ids, [])
}

///|
test "same queryState fill cannot change the snapshot total" {
  let view = boundary_view(["a"], 3, 3)
  view.query_fill_required = true
  view.query_fill_position = 1
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: ["b"],
        total: 4,
        state: "q0",
        bytes: 1,
      }),
    ),
    "changed total",
  )
  assert_eq(view.ordered_ids, ["a"])
  assert_eq(view.total, 3)
}

///|
test "queryChanges result growth retains the newly appended prefix ID" {
  let view = boundary_view(["a"], 1, 3)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: [],
        added: [{ id: "b", index: 1, }],
        total: 2,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.ordered_ids, ["a", "b"])
      assert_eq(next.view.total, 2)
      assert_false(next.view.query_fill_required)
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::Get)
    }
    _ => fail("growing query should fetch its complete two-ID prefix")
  }
}

///|
test "queryChanges permits a removed cached ID to be reinserted at its final index" {
  let view = boundary_view(["a", "b"], 2, 3)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: ["a"],
        added: [{ id: "a", index: 1, }],
        total: 2,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) =>
      assert_eq(next.view.ordered_ids, ["b", "a"])
    _ => fail("RFC remove/reinsert movement should remain supported")
  }
}

///|
test "queryChanges rejects readding an unremoved cached ID before an unsafe splice" {
  let view = boundary_view(["a", "b"], 2, 3)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: [],
        added: [{ id: "a", index: 2, }],
        total: 3,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ),
    "without removing",
  )
  assert_eq(view.ordered_ids, ["a", "b"])
}

///|
test "queryChanges rejects distinct added IDs at the same final index" {
  let view = boundary_view(["a"], 1, 3)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: [],
        added: [{ id: "x", index: 0, }, { id: "y", index: 0, }],
        total: 3,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ),
    "strictly increasing",
  )
  assert_eq(view.ordered_ids, ["a"])
}

///|
test "queryChanges rejects an added array that violates RFC ascending index order" {
  let view = boundary_view(["a"], 1, 3)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: [],
        added: [{ id: "x", index: 1, }, { id: "y", index: 0, }],
        total: 3,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ),
    "strictly increasing",
  )
  assert_eq(view.ordered_ids, ["a"])
}

///|
test "response request ID cannot wrap past the signed Int maximum" {
  let view = boundary_fresh_view(1)
  view.next_request_id = @int.MAX_VALUE
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q0",
        bytes: 1,
      }),
    ),
    "request id overflow",
  )
  assert_eq(view.next_request_id, @int.MAX_VALUE)
}

///|
test "typed query counter rejection preserves the capability projection" {
  let view = boundary_fresh_view(1)
  view.next_request_id = @int.MAX_VALUE
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_bound_response(
      view,
      request.ticket,
      @sync.BoundServerResponse::QueryResult(
        @sync.QueryResponseEnvelope::new(
          "boundary-account",
          { ids: [], total: 0, state: "q0", bytes: 1, },
          Some(false),
        ).unwrap(),
      ),
    ),
    "request id overflow",
  )
  assert_true(view.query_changes_allowed)
  assert_eq(view.query_state, None)
}

///|
test "response round count cannot wrap and reset the budget" {
  let view = boundary_fresh_view(1)
  view.rounds = @int.MAX_VALUE
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q0",
        bytes: 1,
      }),
    ),
    "round counter overflow",
  )
  assert_eq(view.rounds, @int.MAX_VALUE)
  assert_eq(view.next_request_id, 1)
}

///|
test "response byte sum cannot wrap and reset the budget" {
  let view = boundary_fresh_view(1)
  view.bytes_seen = @int.MAX_VALUE - 1
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q0",
        bytes: 2,
      }),
    ),
    "byte counter overflow",
  )
  assert_eq(view.bytes_seen, @int.MAX_VALUE - 1)
  assert_eq(view.next_request_id, 1)
}

///|
test "Email get counter rejection leaves objects and pending IDs intact" {
  let view = boundary_view(["a"], 1, 1)
  view.pending_get = ["a"]
  view.bytes_seen = @int.MAX_VALUE - 1
  let request = @sync.plan(view).requests[0]
  assert_true(request.kind == @sync.RequestKind::Get)
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::GetResult({
        list: [@email.EmailRecord::empty("a")],
        not_found: [],
        state: "e0",
        bytes: 2,
      }),
    ),
    "byte counter overflow",
  )
  assert_eq(view.objects.length(), 0)
  assert_eq(view.pending_get, ["a"])
  assert_eq(view.next_request_id, 1)
}

///|
test "largest representable byte sum is Pending without wrapping" {
  let view = {
    ..boundary_fresh_view(1),
    limits: {
      ..@sync.default_limits(),
      prefix_limit: 1,
      max_bytes: @int.MAX_VALUE,
    },
  }
  view.bytes_seen = @int.MAX_VALUE - 1
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "q0",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Pending(next) => {
      assert_eq(next.reason, "byte budget exhausted")
      assert_eq(next.view.bytes_seen, @int.MAX_VALUE)
      assert_eq(next.view.rounds, 1)
    }
    _ => fail("representable exact byte limit should be Pending")
  }
}

///|
test "Email changes cannot exceed the remaining budget near the Int maximum" {
  let view = {
    ..boundary_view(["a"], 1, 3),
    limits: {
      ..@sync.default_limits(),
      prefix_limit: 3,
      max_changes: @int.MAX_VALUE,
    },
  }
  view.email_required = true
  view.changes_seen = @int.MAX_VALUE - 1
  let request = @sync.plan(view).requests[0]
  assert_eq(request.max_changes, 1)
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::EmailChangesResult({
        created: ["x", "y"],
        updated: [],
        destroyed: [],
        old_state: "e0",
        new_state: "e1",
        has_more_changes: false,
        bytes: 1,
      }),
    ),
    "change budget",
  )
  assert_eq(view.changes_seen, @int.MAX_VALUE - 1)
  assert_eq(view.email_state, Some("e0"))
}

///|
test "query rejects an empty opaque state before advancing progress" {
  let view = boundary_fresh_view(1)
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryResult({
        ids: [],
        total: 0,
        state: "",
        bytes: 1,
      }),
    ),
    "state token must be non-empty",
  )
  assert_eq(view.query_state, None)
  assert_eq(view.next_request_id, 1)
}

///|
test "typed query empty state rejection does not change queryChanges capability" {
  let view = boundary_fresh_view(1)
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_bound_response(
      view,
      request.ticket,
      @sync.BoundServerResponse::QueryResult(
        @sync.QueryResponseEnvelope::new(
          "boundary-account",
          { ids: [], total: 0, state: "", bytes: 1, },
          Some(false),
        ).unwrap(),
      ),
    ),
    "state token must be non-empty",
  )
  assert_true(view.query_changes_allowed)
  assert_eq(view.query_state, None)
}

///|
test "queryChanges rejects either empty opaque state boundary" {
  for states in [("", "q1"), ("q0", "")] {
    let view = boundary_view(["a"], 1, 1)
    view.query_required = true
    let request = @sync.plan(view).requests[0]
    boundary_expect_failure(
      @sync.accept_response(
        view,
        request.ticket,
        @sync.ServerResponse::QueryChangesResult({
          removed: [],
          added: [],
          total: 1,
          old_state: states.0,
          new_state: states.1,
          bytes: 1,
        }),
      ),
      "state tokens must be non-empty",
    )
    assert_eq(view.query_state, Some("q0"))
    assert_eq(view.next_request_id, 1)
  }
}

///|
test "Email changes rejects either empty opaque state boundary" {
  for states in [("", "e1"), ("e0", "")] {
    let view = boundary_view(["a"], 1, 1)
    view.email_required = true
    let request = @sync.plan(view).requests[0]
    boundary_expect_failure(
      @sync.accept_response(
        view,
        request.ticket,
        @sync.ServerResponse::EmailChangesResult({
          created: [],
          updated: [],
          destroyed: [],
          old_state: states.0,
          new_state: states.1,
          has_more_changes: false,
          bytes: 1,
        }),
      ),
      "state tokens must be non-empty",
    )
    assert_eq(view.email_state, Some("e0"))
    assert_eq(view.next_request_id, 1)
  }
}

///|
test "Email changes rejects an empty new state before advancing accepted state" {
  let view = boundary_view(["a"], 1, 1)
  view.email_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::EmailChangesResult({
        created: [],
        destroyed: [],
        updated: [],
        old_state: "e0",
        new_state: "",
        has_more_changes: false,
        bytes: 1,
      }),
    ),
    "state tokens must be non-empty",
  )
  assert_eq(view.email_state, Some("e0"))
}

///|
test "Email get rejects empty state without publishing object progress" {
  let view = boundary_view(["a"], 1, 1)
  view.pending_get = ["a"]
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::GetResult({
        list: [@email.EmailRecord::empty("a")],
        not_found: [],
        state: "",
        bytes: 1,
      }),
    ),
    "state token must be non-empty",
  )
  assert_eq(view.objects.length(), 0)
  assert_eq(view.pending_get, ["a"])
  assert_eq(view.email_state, Some("e0"))
}

///|
test "same queryState cannot conceal a reordered known prefix" {
  let view = boundary_view(["a", "b"], 2, 2)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: ["a"],
        added: [{ id: "a", index: 1, }],
        total: 2,
        old_state: "q0",
        new_state: "q0",
        bytes: 1,
      }),
    ),
    "without changing queryState",
  )
  assert_eq(view.ordered_ids, ["a", "b"])
  assert_eq(view.query_state, Some("q0"))
}

///|
test "same queryState cannot report a different result total" {
  let view = boundary_view(["a"], 1, 2)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  boundary_expect_failure(
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: [],
        added: [],
        total: 2,
        old_state: "q0",
        new_state: "q0",
        bytes: 1,
      }),
    ),
    "without changing queryState",
  )
  assert_eq(view.total, 1)
}

///|
test "same queryState still permits a conservative remove readd with unchanged result" {
  let view = boundary_view(["a", "b"], 2, 2)
  view.query_required = true
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::QueryChangesResult({
        removed: ["a"],
        added: [{ id: "a", index: 0, }],
        total: 2,
        old_state: "q0",
        new_state: "q0",
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.ordered_ids, ["a", "b"])
      assert_eq(next.view.query_state, Some("q0"))
    }
    _ =>
      fail(
        "conservative RFC remove/readd must not be rejected solely for equal queryState",
      )
  }
}

///|
test "same Email state cannot continue a nonadvancing changes page" {
  for updated in [[], ["a"]] {
    let view = boundary_view(["a"], 1, 1)
    view.email_required = true
    let request = @sync.plan(view).requests[0]
    boundary_expect_failure(
      @sync.accept_response(
        view,
        request.ticket,
        @sync.ServerResponse::EmailChangesResult({
          created: [],
          updated,
          destroyed: [],
          old_state: "e0",
          new_state: "e0",
          has_more_changes: true,
          bytes: 1,
        }),
      ),
      "did not advance its state",
    )
    assert_eq(view.email_state, Some("e0"))
    assert_eq(view.changes_seen, 0)
  }
}

///|
test "same Email state final updates retain object fetch and query reconciliation obligations" {
  let view = boundary_view(["a"], 1, 1)
  view.email_required = true
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::EmailChangesResult({
        created: [],
        updated: ["a"],
        destroyed: [],
        old_state: "e0",
        new_state: "e0",
        has_more_changes: false,
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.email_state, Some("e0"))
      assert_eq(next.view.changes_seen, 1)
      assert_eq(next.view.pending_get, ["a"])
      assert_true(next.view.query_required)
      assert_true(next.plan.requests[0].kind == @sync.RequestKind::QueryChanges)
    }
    _ =>
      fail(
        "same-token final updates must retain normal reconciliation obligations",
      )
  }
}

///|
test "same Email state is valid for an empty final changes page" {
  let view = boundary_view(["a"], 1, 1)
  view.email_required = true
  let request = @sync.plan(view).requests[0]
  match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.ServerResponse::EmailChangesResult({
        created: [],
        updated: [],
        destroyed: [],
        old_state: "e0",
        new_state: "e0",
        has_more_changes: false,
        bytes: 1,
      }),
    ) {
    @sync.Acceptance::Continue(next) => {
      assert_eq(next.view.email_state, Some("e0"))
      assert_eq(next.view.changes_seen, 0)
    }
    _ => fail("an empty final page need not advance the Email state")
  }
}

///|
test "responses after budget exhaustion preserve the checkpoint as Pending" {
  for budget in ["round", "byte", "change"] {
    let view = boundary_fresh_view(1)
    match budget {
      "round" => view.rounds = view.limits.max_rounds
      "byte" => view.bytes_seen = view.limits.max_bytes
      _ => {
        view.changes_seen = view.limits.max_changes
        view.email_required = true
        // This capability legitimately plans a full query before an optional
        // changes pass, even when no change budget remains.
        view.query_changes_allowed = false
      }
    }
    let before_rounds = view.rounds
    let before_bytes = view.bytes_seen
    let request = @sync.plan(view).requests[0]
    match
      @sync.accept_response(
        view,
        request.ticket,
        @sync.ServerResponse::QueryResult({
          ids: [],
          total: 0,
          state: "q0",
          bytes: 1,
        }),
      ) {
      @sync.Acceptance::Pending(next) => {
        assert_true(next.reason.contains("budget exhausted"))
        assert_eq(next.view.rounds, before_rounds)
        assert_eq(next.view.bytes_seen, before_bytes)
        assert_eq(next.view.next_request_id, 1)
        assert_eq(next.view.query_state, None)
        assert_eq(next.checkpoint.next_request_id, 1)
      }
      _ =>
        fail(
          "exhausted budget must remain resumable without accepting another response",
        )
    }
  }
}
