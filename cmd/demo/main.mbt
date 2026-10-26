///|
/// A synthetic response replay through the public MoonBit API, without network.
fn main {
  let account : @sync.AccountScope = {
    service_identity: "https://jmap.example.test",
    account_id: "demo-account",
  }
  let before = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    None,
  )
  let query = @sync.plan(before).requests[0]
  println("1. Email/query: position=\{query.position}, limit=\{query.limit}")
  let next = match
    @sync.accept_response(
      before,
      query.ticket,
      @sync.ServerResponse::QueryResult({
        ids: ["b", "a"],
        total: 2,
        state: "q0",
        bytes: 40,
      }),
    ) {
    @sync.Acceptance::Continue(next) => next
    _ => abort("expected Email/get after initial query")
  }
  // Without an existing Email state, the engine first requests an empty get
  // to establish its object-state baseline, then fetches the visible IDs.
  let next = match
    @sync.accept_response(
      next.view,
      next.plan.requests[0].ticket,
      @sync.ServerResponse::GetResult({
        list: [],
        not_found: [],
        state: "e0",
        bytes: 20,
      }),
    ) {
    @sync.Acceptance::Continue(next) => next
    _ => abort("expected visible object fetch after baseline")
  }
  let get = next.plan.requests[0]
  let objects = ["a", "b"].map(id => {
    let record : @email.EmailRecord = {
      id,
      thread_id: "thread-" + id,
      mailbox_ids: Some([{ key: "inbox", value: true, }]),
      keywords: Some([]),
      received_at: Some("2026-10-26T00:00:00Z"),
      subject: Some("Synthetic " + id),
      from: Some([{ email: "sender@example.test", name: None, }]),
      preview: Some("Synthetic demo message"),
    }
    record
  })
  println("2. Email/get: response objects arrive in [a, b] order")
  // Response acceptance updates the view. Keep an independent before-state
  // for the certificate instead of passing the already-updated object twice.
  let before_get = @sync.restore_checkpoint(
    @sync.checkpoint(next.view),
    @sync.default_limits(),
  ).unwrap()
  let acceptance = @sync.accept_response(
    next.view,
    get.ticket,
    @sync.ServerResponse::GetResult({
      list: objects,
      not_found: [],
      state: "e0",
      bytes: 400,
    }),
  )
  match acceptance {
    @sync.Acceptance::Commit(done) => {
      guard done.view.ordered_ids == ["b", "a"] else {
        abort("query order must survive object reordering")
      }
      guard done.view.completeness == @sync.Completeness::Ready else {
        abort("complete initial view should be Ready")
      }
      let proof = @sync.certificate_from_acceptance(before_get, acceptance).unwrap()
      @sync.verify_jmap_email_prefix_certificate(proof).unwrap()
      println("3. Ready: ordered_ids=[b, a], queryState=q0, emailState=e0")
      println("4. JMAP email prefix certificate verified")
    }
    _ => abort("expected a complete committed view")
  }
}
