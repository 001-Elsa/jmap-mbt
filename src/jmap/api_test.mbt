///|
test "typed method response retains account and query capability" {
  let response = @jmap.TypedMethodResponse::new(
    @jmap.MethodName::EmailQuery,
    "account-1",
    { "accountId": Json::string("account-1") },
    "q1",
    Some(false),
  )
  match response {
    None => assert_true(false)
    Some(value) => {
      assert_true(value.account_matches("account-1"))
      assert_true(!value.account_matches("account-2"))
      let raw = value.to_method_response()
      assert_true(raw is Some(_))
    }
  }
}

///|
test "typed method response rejects query capability on another method" {
  let response = @jmap.TypedMethodResponse::new(
    @jmap.MethodName::EmailGet,
    "account-1",
    { "accountId": Json::string("account-1") },
    "g1",
    Some(true),
  )
  assert_true(response is None)
}

///|
test "planned queries explicitly request total and retain structured unread filters" {
  let view = @sync.open_view(
    { service_identity: "wire-test", account_id: "a", },
    @email.Unread("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let request = @sync.plan(view).requests[0]
  let encoded = @jmap.encode_planned_request(request, "q").unwrap()
  let arguments = match encoded.method_calls[0].arguments {
    Json::Object(fields) => fields
    _ => fail("fixed query arguments must be an object")
  }
  assert_true(arguments.get("calculateTotal") == Some(Json::boolean(true)))
  assert_true(
    arguments.get("filter") ==
    Some({
      "operator": Json::string("AND"),
      "conditions": Json::array([
        { "inMailbox": Json::string("inbox") },
        { "notKeyword": Json::string("$seen") },
      ]),
    }),
  )
  view.ordered_ids = ["a", "b"]
  view.total = 20
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = true
  view.email_required = false
  let delta = @sync.plan(view).requests[0]
  let call = @jmap.encode_planned_request(delta, "qc").unwrap().method_calls[0]
  assert_true(call.method_name == @jmap.EmailQueryChanges)
  match call.arguments {
    Json::Object(fields) => {
      assert_true(fields.get("sinceQueryState") == Some(Json::string("q0")))
      assert_true(fields.get("calculateTotal") == Some(Json::boolean(true)))
      assert_true(fields.get("upToId") is None)
      assert_true(fields.get("limit") is None)
    }
    _ => fail("queryChanges arguments must be an object")
  }
}

///|
test "planned wire encoder rejects altered fields and preserves empty baseline gets" {
  let view = @sync.open_view(
    { service_identity: "wire-test", account_id: "a", },
    @email.Latest("inbox"),
    @sync.default_limits(),
    None,
  )
  let request = @sync.plan(view).requests[0]
  assert_true(
    @jmap.encode_planned_request(
      { ..request, filter: Some(@email.InMailbox("other")), },
      "q",
    )
    is Err(_),
  )
  assert_true(@jmap.encode_planned_request(request, "") is Err(_))
  let baseline = match
    @sync.accept_response(
      view,
      request.ticket,
      @sync.QueryResult({ ids: [], total: 0, state: "q0", bytes: 1, }),
    ) {
    @sync.Continue(next) => next.plan.requests[0]
    _ => fail("empty query without an Email baseline must schedule Email/get")
  }
  let wire = @jmap.encode_planned_request(baseline, "g").unwrap()
  assert_true(wire.method_calls[0].method_name == @jmap.EmailGet)
  match wire.method_calls[0].arguments {
    Json::Object(fields) =>
      assert_true(fields.get("ids") == Some(Json::array([])))
    _ => fail("get arguments must be an object")
  }
  let known = @sync.open_view(
    { service_identity: "wire-test", account_id: "a", },
    @email.Latest("inbox"),
    @sync.default_limits(),
    Some("e0"),
  )
  let query = @sync.plan(known).requests[0]
  let changes = match
    @sync.accept_response(
      known,
      query.ticket,
      @sync.QueryResult({ ids: [], total: 0, state: "q0", bytes: 1, }),
    ) {
    @sync.Continue(next) => next.plan.requests[0]
    _ =>
      fail("query with an existing Email baseline must schedule Email/changes")
  }
  let call = @jmap.encode_planned_request(changes, "c").unwrap().method_calls[0]
  assert_true(call.method_name == @jmap.EmailChanges)
  match call.arguments {
    Json::Object(fields) =>
      assert_true(fields.get("maxChanges") == Some(Json::number(500.0)))
    _ => fail("changes arguments must be an object")
  }
}

///|
test "planned suffix wire keeps the confirmed position and explicit object projection" {
  let view = @sync.open_view(
    { service_identity: "wire-test", account_id: "a", },
    @email.Latest("inbox"),
    { ..@sync.default_limits(), prefix_limit: 3, },
    Some("e0"),
  )
  view.ordered_ids = ["a", "b", "c"]
  view.total = 3
  view.query_state = Some("q0")
  view.query_valid = true
  view.email_required = false
  let delta = @sync.plan(view).requests[0]
  let next = match
    @sync.accept_response(
      view,
      delta.ticket,
      @sync.QueryChangesResult({
        removed: ["c"],
        added: [{ id: "d", index: 2, }],
        total: 3,
        old_state: "q0",
        new_state: "q1",
        bytes: 1,
      }),
    ) {
    @sync.Continue(next) => next
    _ => fail("changed suffix must require a server query")
  }
  let suffix = next.plan.requests[0]
  let wire = @jmap.encode_planned_request(suffix, "fill").unwrap()
  assert_eq(wire.method_calls.length(), 1)
  assert_true(wire.method_calls[0].method_name == @jmap.EmailQuery)
  match wire.method_calls[0].arguments {
    Json::Object(fields) => {
      assert_true(fields.get("position") == Some(Json::number(2.0)))
      assert_true(fields.get("limit") == Some(Json::number(1.0)))
      assert_true(fields.get("calculateTotal") == Some(Json::boolean(true)))
    }
    _ => fail("suffix request must use query arguments")
  }
  let get = match
    @sync.accept_response(
      next.view,
      suffix.ticket,
      @sync.QueryResult({ ids: ["d"], total: 3, state: "q1", bytes: 1, }),
    ) {
    @sync.Continue(after) => after.plan.requests[0]
    _ => fail("confirmed suffix must request its missing objects")
  }
  let encoded = @jmap.encode_planned_request(get, "get").unwrap()
  match encoded.method_calls[0].arguments {
    Json::Object(fields) => {
      assert_true(
        fields.get("ids") ==
        Some(
          Json::array([Json::string("a"), Json::string("b"), Json::string("d")]),
        ),
      )
      assert_true(
        fields.get("properties") ==
        Some(Json::array(@email.default_properties().map(Json::string))),
      )
      assert_true(fields.get("#ids") is None)
    }
    _ => fail("object request must use explicit ids and properties")
  }
  assert_true(
    @jmap.encode_planned_request({ ..get, properties: ["id"], }, "bad")
    is Err(_),
  )
  assert_true(
    @jmap.encode_planned_request({ ..get, ids: ["outside"], }, "bad") is Err(_),
  )
}
