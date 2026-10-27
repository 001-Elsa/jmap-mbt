///|
/// Enumerate complete server lists independently of the implementation.
/// A legal delta may preserve any common ordered subsequence. The server's
/// complete new list, not a second cut implementation, is the oracle.
fn suffix_orders(
  prefix : Array[String],
  remaining : Array[String],
  out : Array[Array[String]],
) -> Unit {
  out.push(prefix.copy())
  for index, id in remaining {
    let next = prefix.copy()
    next.push(id)
    let rest = remaining.copy()
    let _ = rest.remove(index)
    suffix_orders(next, rest, out)
  }
}

///|
fn suffix_subsequence(items : Array[String], full : Array[String]) -> Bool {
  let mut at = 0
  for id in full {
    if at < items.length() && items[at] == id {
      at = at + 1
    }
  }
  at == items.length()
}

///|
fn suffix_result(result : @sync.Acceptance) -> @sync.EmailView raise {
  match result {
    @sync.Continue(value) => value.view
    @sync.Commit(value) => value.view
    @sync.Pending(value) => value.view
    @sync.NeedsRefresh(value) => fail(value.reason)
    @sync.ProtocolFailure(value) => fail(value.reason)
    @sync.Unsupported(value) => fail(value.reason)
    @sync.Dropped(value) => fail(value.reason)
  }
}

///|
test "server suffix reads preserve every legal four-ID query transition" {
  let orders : Array[Array[String]] = []
  suffix_orders([], ["a", "b", "c", "d"], orders)
  assert_eq(orders.length(), 65)
  let mut checked = 0
  let mut rereads = 0
  for old in orders {
    for current in orders {
      for kept in orders {
        if !suffix_subsequence(kept, old) || !suffix_subsequence(kept, current) {
          continue
        }
        let removed = old.filter(fn(id) { !kept.contains(id) })
        let added : Array[@sync.Added] = []
        for index, id in current {
          if !kept.contains(id) {
            added.push({ id, index, })
          }
        }
        for limit = 1; limit <= 4; limit = limit + 1 {
          let view = @sync.open_view(
            { service_identity: "suffix-oracle", account_id: "synthetic", },
            @email.Latest("inbox"),
            { ..@sync.default_limits(), prefix_limit: limit, },
            Some("e0"),
          )
          view.ordered_ids = Array::from_iter(old.iter().take(limit))
          view.total = old.length()
          view.query_state = Some("q0")
          view.query_valid = true
          view.query_required = true
          view.email_required = false
          let delta_ticket = @sync.plan(view).requests[0].ticket
          let after = suffix_result(
            @sync.accept_response(
              view,
              delta_ticket,
              @sync.QueryChangesResult({
                removed,
                added,
                total: current.length(),
                old_state: "q0",
                new_state: "q1",
                bytes: 1,
              }),
            ),
          )
          let known = after.ordered_ids.length()
          // Every retained slot must be a real leading server slot.
          assert_eq(
            after.ordered_ids,
            Array::from_iter(current.iter().take(known)),
          )
          let wanted = Array::from_iter(current.iter().take(limit))
          if known < wanted.length() {
            rereads = rereads + 1
            let request = @sync.plan(after).requests[0]
            assert_true(request.kind == @sync.Query)
            assert_eq(request.position, known)
            assert_eq(request.ticket.expected_query_state, Some("q1"))
            let tail : Array[String] = []
            for rank = request.position
                rank < current.length() && tail.length() < request.limit
                rank = rank + 1 {
              tail.push(current[rank])
            }
            let filled = suffix_result(
              @sync.accept_response(
                after,
                request.ticket,
                @sync.QueryResult({
                  ids: tail,
                  total: current.length(),
                  state: "q1",
                  bytes: 1,
                }),
              ),
            )
            assert_eq(filled.ordered_ids, wanted)
          } else {
            assert_eq(after.ordered_ids, wanted)
          }
          checked = checked + 1
        }
      }
    }
  }
  println("server suffix exhaustive transitions=\{checked}, rereads=\{rereads}")
}
