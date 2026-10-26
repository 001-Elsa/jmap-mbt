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
