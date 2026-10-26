///|
/// This oracle deliberately uses RFC remove/insert/truncate, independently
/// of the production final-rank merge. None of these IDs or states is real.
fn rank_test_splice(
  cached : Array[String],
  removed : Array[String],
  added : Array[@sync.Added],
  total : Int32,
  limit : Int32,
) -> Array[String]? {
  let mut ids = cached.copy()
  for gone in removed {
    ids = ids.filter(fn(id) { id != gone })
  }
  for addition in added {
    if addition.index > ids.length() {
      return None
    }
    ids.insert(addition.index, addition.id)
  }
  while ids.length() > total || ids.length() > limit {
    let _ = ids.remove(ids.length() - 1)
  }
  Some(ids)
}

///|
fn rank_test_ordered_subsets(
  prefix : Array[String],
  remaining : Array[String],
  output : Array[Array[String]],
) -> Unit {
  output.push(prefix.copy())
  for index, id in remaining {
    let next = prefix.copy()
    next.push(id)
    let rest = remaining.copy()
    let _ = rest.remove(index)
    rank_test_ordered_subsets(next, rest, output)
  }
}

///|
fn rank_test_view(
  cached : Array[String],
  old_total : Int32,
  limit : Int32,
) -> @sync.EmailView {
  let view = @sync.open_view(
    { service_identity: "rank-service", account_id: "rank-account", },
    @email.Latest("inbox"),
    { ..@sync.default_limits(), prefix_limit: limit, },
    Some("e0"),
  )
  view.ordered_ids = cached.copy()
  view.total = old_total
  view.query_state = Some("q0")
  view.query_valid = true
  view.query_required = true
  view.email_valid = true
  view.email_required = false
  view
}

///|
fn rank_test_check(
  cached : Array[String],
  old_total : Int32,
  limit : Int32,
  removed : Array[String],
  added : Array[@sync.Added],
  total : Int32,
) -> Bool raise {
  let view = rank_test_view(cached, old_total, limit)
  let request = @sync.plan(view).requests[0]
  assert_true(request.kind == @sync.RequestKind::QueryChanges)
  let expected = rank_test_splice(cached, removed, added, total, limit)
  let actual = @sync.accept_response(
    view,
    request.ticket,
    @sync.ServerResponse::QueryChangesResult({
      removed,
      added,
      total,
      old_state: "q0",
      new_state: "q1",
      bytes: 1,
    }),
  )
  match expected {
    None => {
      match actual {
        @sync.Acceptance::NeedsRefresh(failed) => {
          assert_true(failed.reason.contains("outside the cached prefix"))
          assert_eq(failed.view.ordered_ids, cached)
          assert_false(failed.view.query_valid)
          assert_eq(failed.view.query_state, None)
        }
        _ => fail("an unknown predecessor rank must require a fresh query")
      }
      false
    }
    Some(ids) => {
      let next = match actual {
        @sync.Acceptance::Continue(next) => next.view
        @sync.Acceptance::Commit(next) => next.view
        _ => fail("a provable JMAP rank merge must retain its known prefix")
      }
      assert_eq(next.ordered_ids, ids)
      assert_eq(next.total, total)
      assert_eq(next.query_state, Some("q1"))
      assert_false(next.query_required)
      assert_eq(next.query_fill_position, ids.length())
      assert_eq(
        next.query_fill_required,
        ids.length() < total && ids.length() < limit,
      )
      assert_eq(next.email_state, Some("e0"))
      true
    }
  }
}

///|
test "JMAP final-rank merge matches independent splice over bounded ordered prefixes" {
  let prefixes : Array[Array[String]] = []
  rank_test_ordered_subsets([], ["a", "b", "c"], prefixes)
  assert_eq(prefixes.length(), 16)
  let addition_orders : Array[Array[String]] = []
  rank_test_ordered_subsets([], ["a", "b", "c", "x"], addition_orders)
  let removal_orders : Array[Array[String]] = []
  rank_test_ordered_subsets([], ["a", "b", "c"], removal_orders)
  // Only the canonical alphabetical representative of each removed set is
  // needed: RFC removals have no relative-order meaning.
  let removal_sets = removal_orders.filter(fn(ids) {
    let mut ordered = true
    for index = 1; index < ids.length(); index = index + 1 {
      if ids[index - 1] > ids[index] {
        ordered = false
      }
    }
    ordered
  })
  assert_eq(removal_sets.length(), 8)
  let mut checked = 0
  let mut proven = 0
  let mut unknown = 0
  for cached in prefixes {
    for removed in removal_sets {
      for addition_order in addition_orders {
        if addition_order.length() > 2 {
          continue
        }
        let allowed = addition_order.all(fn(id) {
          !cached.contains(id) || removed.contains(id)
        })
        if !allowed {
          continue
        }
        for total = 0; total <= 5; total = total + 1 {
          let additions : Array[Array[@sync.Added]] = []
          match addition_order.length() {
            0 => additions.push([])
            1 =>
              for rank = 0; rank < total; rank = rank + 1 {
                additions.push([{ id: addition_order[0], index: rank, }])
              }
            2 =>
              for first = 0; first < total; first = first + 1 {
                for second = first + 1; second < total; second = second + 1 {
                  additions.push([
                    { id: addition_order[0], index: first, },
                    { id: addition_order[1], index: second, },
                  ])
                }
              }
            _ => ()
          }
          for added in additions {
            // A complete old result and an old result with an unknown tail;
            // both a tight prefix limit and one with room for a new tail ID.
            for tail = 0; tail <= 2; tail = tail + 2 {
              for extra = 0; extra <= 1; extra = extra + 1 {
                let limit = if cached.length() + extra == 0 {
                  1
                } else {
                  cached.length() + extra
                }
                if rank_test_check(
                    cached,
                    cached.length() + tail,
                    limit,
                    removed,
                    added,
                    total,
                  ) {
                  proven = proven + 1
                } else {
                  unknown = unknown + 1
                }
                checked = checked + 1
              }
            }
          }
        }
      }
    }
  }
  assert_eq(checked, 93072)
  assert_eq(proven, 39256)
  assert_eq(unknown, 53816)
  println(
    "rank merge exhaustive cases=\{checked}, proven=\{proven}, unknown-rank=\{unknown}",
  )
}

///|
test "rank outside a bounded output still cannot be clamped past unknown predecessors" {
  assert_false(rank_test_check(["a"], 4, 1, [], [{ id: "x", index: 3, }], 5))
}

///|
test "rank merge keeps appended and removed-readded IDs and supports changed totals" {
  assert_true(rank_test_check(["a"], 1, 3, [], [{ id: "b", index: 1, }], 2))
  assert_true(
    rank_test_check(["a", "b"], 2, 3, ["a"], [{ id: "a", index: 1, }], 2),
  )
  assert_true(rank_test_check(["a", "b", "c"], 3, 3, ["b"], [], 1))
  assert_true(
    rank_test_check(
      ["a", "b"],
      4,
      3,
      ["a", "not-cached"],
      [{ id: "x", index: 1, }],
      4,
    ),
  )
}
