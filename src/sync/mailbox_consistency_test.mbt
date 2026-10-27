///|
fn mailbox_record(
  id : String,
  mailbox : String,
  seen : Bool,
) -> @email.EmailRecord {
  {
    id,
    thread_id: "thread-" + id,
    mailbox_ids: Some([{ key: mailbox, value: true, }]),
    keywords: Some(if seen { [{ key: "$seen", value: true, }] } else { [] }),
    received_at: Some("2026-10-26T00:00:00Z"),
    subject: Some("synthetic"),
    from: Some([]),
    preview: Some(""),
  }
}

///|
fn mailbox_view(spec : @email.ViewSpec) -> @sync.EmailView {
  let view = @sync.open_view(
    { service_identity: "mailbox-race", account_id: "a", },
    spec,
    @sync.default_limits(),
    Some("e0"),
  )
  view.ordered_ids = ["m"]
  view.total = 1
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = false
  view.email_required = false
  view.pending_get = ["m"]
  view
}

///|
test "mailbox or seen race never publishes a complete wrong-view object" {
  for
    (spec, record) in [
      (@email.Latest("inbox"), mailbox_record("m", "archive", false)),
      (@email.Unread("inbox"), mailbox_record("m", "inbox", true)),
    ] {
    let view = mailbox_view(spec)
    let ticket = @sync.plan(view).requests[0].ticket
    match
      @sync.accept_response(
        view,
        ticket,
        @sync.GetResult({
          list: [record],
          not_found: [],
          state: "e0",
          bytes: 1,
        }),
      ) {
      @sync.NeedsRefresh(result) => {
        assert_true(result.reason.contains("mailbox/unread"))
        assert_eq(result.view.query_state, None)
        assert_eq(result.view.ordered_ids, ["m"])
        assert_eq(result.view.email_state, Some("e0"))
      }
      _ => fail("a complete record outside the fixed query must not commit")
    }
  }
}

///|
test "Latest allows seen mail but Unread requires an absent seen keyword" {
  for
    (spec, seen) in [
      (@email.Latest("inbox"), true),
      (@email.Unread("inbox"), false),
    ] {
    let view = mailbox_view(spec)
    let ticket = @sync.plan(view).requests[0].ticket
    match
      @sync.accept_response(
        view,
        ticket,
        @sync.GetResult({
          list: [mailbox_record("m", "inbox", seen)],
          not_found: [],
          state: "e0",
          bytes: 1,
        }),
      ) {
      @sync.Commit(_) => ()
      _ => fail("matching complete projections should commit")
    }
  }
}

///|
test "restoring Ready cannot bypass the unread mailbox predicate" {
  let view = mailbox_view(@email.Unread("inbox"))
  view.pending_get = []
  view.objects = [mailbox_record("m", "inbox", true)]
  view.completeness = @sync.Ready
  match
    @sync.restore_checkpoint(@sync.checkpoint(view), @sync.default_limits()) {
    Err(reason) => assert_true(reason.contains("mailbox/unread"))
    Ok(_) => fail("forged Ready must still satisfy the query predicate")
  }
}

///|
test "Email changes invalidates visible payloads without fetching off-prefix IDs" {
  let view = mailbox_view(@email.Unread("inbox"))
  view.objects = [mailbox_record("m", "inbox", false)]
  view.pending_get = []
  view.email_required = true
  let ticket = @sync.plan(view).requests[0].ticket
  match
    @sync.accept_response(
      view,
      ticket,
      @sync.EmailChangesResult({
        created: ["new-outside"],
        updated: ["m", "other-outside"],
        destroyed: [],
        old_state: "e0",
        new_state: "e1",
        has_more_changes: false,
        bytes: 1,
      }),
    ) {
    @sync.Continue(result) => {
      assert_eq(result.view.ordered_ids, ["m"])
      assert_eq(result.view.objects.length(), 0)
      assert_eq(result.view.pending_get, ["m"])
      assert_true(result.plan.requests[0].kind == @sync.QueryChanges)
      assert_true(@sync.committed_emails(result.view) is Err(_))
    }
    _ =>
      fail("updated mail must lose its stale fields while query work remains")
  }
}

///|
test "committed records follow query order and detach mutable email maps" {
  let view = mailbox_view(@email.Latest("inbox"))
  view.ordered_ids = ["b", "a"]
  view.total = 2
  view.pending_get = []
  view.objects = [
    mailbox_record("a", "inbox", true),
    mailbox_record("b", "inbox", false),
  ]
  view.completeness = @sync.Ready
  let records = @sync.committed_emails(view).unwrap()
  assert_eq(records.map(fn(record) { record.id }), ["b", "a"])
  let mailboxes = records[0].mailbox_ids.unwrap()
  mailboxes[0] = { key: "archive", value: true, }
  assert_true(@sync.committed_emails(view) is Ok(_))
  assert_eq(view.objects[1].mailbox_ids.unwrap()[0].key, "inbox")
  view.completeness = @sync.Pending
  assert_true(@sync.committed_emails(view) is Err(_))
}
