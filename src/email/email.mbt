///|
/// The two intentionally small query projections supported by MoonJMAP v0.1.
/// This package only describes the projection. It does not perform filtering,
/// sorting, JSON encoding, or network I/O.
pub(all) enum ViewSpec {
  Latest(String)
  Unread(String)
} derive(Eq)

///|
pub extend ViewSpec with Eq::{not_equal, equal}

///|
/// The finite filter projection emitted by the sync planner.  Keeping this
/// as a closed type prevents a caller from accidentally treating the
/// human-readable canonical string returned by `ViewSpec::filter` as JMAP
/// wire JSON.  An adapter can map the two cases to the RFC filter objects.
pub(all) enum FilterSpec {
  InMailbox(String)
  UnreadInMailbox(String)
} derive(Eq)

///|
pub extend FilterSpec with Eq::{not_equal, equal}

///|
/// The only sort projection supported by v0.1.  The wire adapter maps this to
/// `[{
///   "property": "receivedAt",
///   "isAscending": false
/// }]`.
pub(all) enum SortSpec {
  ReceivedAtDescending
} derive(Eq)

///|
pub extend SortSpec with Eq::{not_equal, equal}

///|
/// Fixed presentation properties. The order is stable so callers can use it
/// as the `Email/get` properties array without constructing a generic schema.
pub(all) enum Property {
  Id
  ThreadId
  MailboxIds
  Keywords
  ReceivedAt
  Subject
  From
  Preview
} derive(Eq)

///|
pub extend Property with Eq::{not_equal, equal}

///|
pub fn ViewSpec::filter(self : ViewSpec) -> String {
  match self {
    Latest(mailbox_id) => "inMailbox:" + mailbox_id
    Unread(mailbox_id) => "and(inMailbox:" + mailbox_id + ",notKeyword:$seen)"
  }
}

///|
pub fn ViewSpec::filter_spec(self : ViewSpec) -> FilterSpec {
  match self {
    Latest(mailbox_id) => FilterSpec::InMailbox(mailbox_id)
    Unread(mailbox_id) => FilterSpec::UnreadInMailbox(mailbox_id)
  }
}

///|
pub fn ViewSpec::sort(self : ViewSpec) -> String {
  match self {
    Latest(_) | Unread(_) => "receivedAt:desc"
  }
}

///|
pub fn ViewSpec::sort_spec(_self : ViewSpec) -> SortSpec {
  ReceivedAtDescending
}

///|
pub fn FilterSpec::canonical(self : FilterSpec) -> String {
  match self {
    InMailbox(mailbox_id) => "inMailbox:" + mailbox_id
    UnreadInMailbox(mailbox_id) =>
      "and(inMailbox:" + mailbox_id + ",notKeyword:$seen)"
  }
}

///|
pub fn SortSpec::canonical(self : SortSpec) -> String {
  match self {
    ReceivedAtDescending => "receivedAt:desc"
  }
}

///|
pub fn ViewSpec::name(self : ViewSpec) -> String {
  match self {
    Latest(_) => "latest"
    Unread(_) => "unread"
  }
}

///|
pub fn property_name(property : Property) -> String {
  match property {
    Id => "id"
    ThreadId => "threadId"
    MailboxIds => "mailboxIds"
    Keywords => "keywords"
    ReceivedAt => "receivedAt"
    Subject => "subject"
    From => "from"
    Preview => "preview"
  }
}

///|
pub fn default_properties() -> Array[String] {
  [
    "id", "threadId", "mailboxIds", "keywords", "receivedAt", "subject", "from",
    "preview",
  ]
}

///|
/// A single entry from the RFC `Id[Boolean]` maps used by `mailboxIds` and
/// `keywords`.  MoonBit has no structural JSON object type in this package's
/// public contract, so adapters keep the key and boolean together instead of
/// silently reducing the map to an array of strings.  A `false` value is
/// retained so a decoder can diagnose a malformed server response rather than
/// losing information while building a view.
pub(all) struct BooleanEntry {
  key : String
  value : Bool
} derive(Eq)

///|
pub extend BooleanEntry with Eq::{not_equal, equal}

///|
/// The RFC `EmailAddress` projection used by the `from` property.  The name
/// is nullable on the wire; an absent name is represented by `None`, not by a
/// fabricated empty string.
pub(all) struct EmailAddress {
  email : String
  name : String?
} derive(Eq)

///|
pub extend EmailAddress with Eq::{not_equal, equal}

///|
/// A bounded object projection.  The collection-valued fields mirror the
/// JMAP wire shapes: `mailboxIds` and `keywords` are objects, and `from` is an
/// array of address objects.  The object-valued fields are optional so an
/// adapter can distinguish a valid empty object (`Some([])`) from an omitted
/// or null property (`None`).  `receivedAt`, `subject`, `from`, and `preview`
/// are options because the transport adapter must preserve a missing or null
/// value long enough for the sync core to reject an incomplete Ready commit.
/// The v0.1 adapter is expected to construct `Some(...)` only when the field
/// was present with the supported value; it must not turn null/missing into an
/// empty string.
pub(all) struct EmailRecord {
  id : String
  thread_id : String
  mailbox_ids : Array[BooleanEntry]?
  keywords : Array[BooleanEntry]?
  received_at : String?
  subject : String?
  from : Array[EmailAddress]?
  preview : String?
} derive(Eq)

///|
pub extend EmailRecord with Eq::{not_equal, equal}

///|
pub fn EmailRecord::empty(id : String) -> EmailRecord {
  {
    id,
    thread_id: "",
    mailbox_ids: None,
    keywords: None,
    received_at: None,
    subject: None,
    from: None,
    preview: None,
  }
}

///|
pub fn EmailRecord::has_id(self : EmailRecord, id : String) -> Bool {
  self.id == id
}

///|
/// Return whether the fixed v0.1 presentation projection is complete enough
/// for a Ready checkpoint.  Empty mailbox/keyword maps are valid projections;
/// the optional display fields are required to be present because this core
/// deliberately does not invent values for missing or null wire properties.
pub fn EmailRecord::is_complete(self : EmailRecord) -> Bool {
  self.id != "" &&
  self.thread_id != "" &&
  self.mailbox_ids is Some(mailboxes) &&
  unique_boolean_keys(mailboxes) &&
  self.keywords is Some(keywords) &&
  unique_boolean_keys(keywords) &&
  self.received_at is Some(received_at) &&
  received_at != "" &&
  self.subject is Some(_) &&
  self.from is Some(addresses) &&
  valid_addresses(addresses) &&
  self.preview is Some(_)
}

///|
fn unique_boolean_keys(entries : Array[BooleanEntry]) -> Bool {
  let seen : Array[String] = []
  for entry in entries {
    // RFC 8621's Id[Boolean] and String[Boolean] maps use true as the
    // membership marker.  Keep the original value in BooleanEntry so an
    // adapter can report a malformed false entry, but never publish it as a
    // complete projection.
    if entry.key == "" || !entry.value || seen.contains(entry.key) {
      return false
    }
    seen.push(entry.key)
  }
  true
}

///|
fn valid_addresses(addresses : Array[EmailAddress]) -> Bool {
  for address in addresses {
    if address.email == "" {
      return false
    }
  }
  true
}
