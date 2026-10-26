test "empty EmailRecord remains incomplete" {
  let record = @email.EmailRecord::empty("a")
  assert_false(record.is_complete())
}

test "explicit empty maps are distinct from missing maps" {
  let record : @email.EmailRecord = {
    id: "a",
    thread_id: "thread-a",
    mailbox_ids: Some([]),
    keywords: Some([]),
    received_at: Some("2026-10-25T00:00:00Z"),
    subject: Some(""),
    from: Some([]),
    preview: Some(""),
  }
  assert_true(record.is_complete())
}

test "duplicate object keys and blank addresses are incomplete" {
  let complete : @email.EmailRecord = {
    id: "a",
    thread_id: "thread-a",
    mailbox_ids: Some([{ key: "inbox", value: true }]),
    keywords: Some([]),
    received_at: Some("2026-10-25T00:00:00Z"),
    subject: Some("subject"),
    from: Some([{ email: "a@example.test", name: None }]),
    preview: Some("preview"),
  }
  assert_true(complete.is_complete())
  let duplicate_keys = {
    ..complete,
    mailbox_ids: Some([
      { key: "inbox", value: true },
      { key: "inbox", value: false },
    ]),
  }
  assert_false(duplicate_keys.is_complete())
  let blank_address = { ..duplicate_keys, mailbox_ids: Some([]), from: Some([{ email: "", name: None }]) }
  assert_false(blank_address.is_complete())
  let blank_date = {
    ..complete,
    mailbox_ids: Some([]),
    from: Some([{ email: "a@example.test", name: None }]),
    received_at: Some(""),
  }
  assert_false(blank_date.is_complete())
  let false_membership = {
    ..duplicate_keys,
    mailbox_ids: Some([{ key: "inbox", value: false }]),
  }
  assert_false(false_membership.is_complete())
}
