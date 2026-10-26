"""Wire-model regression tests independent of the sync oracle.

These tests pin the JMAP tuple shape and the failure behaviour that protects
checkpoints from malformed or stale responses.  They use only the standard
library and run on Python 3.9+, the same versions used by the fixture runner.
"""

from __future__ import annotations

import unittest

from jmap import (
    EmailGetRequest,
    EmailGetResponse,
    EmailObject,
    EmailQueryChangesResponse,
    EmailQueryRequest,
    JmapRequest,
    JmapResponse,
    InvalidJmapInput,
    MethodCall,
    MethodResponse,
    ProtocolFailure,
    ResultReference,
    decode_request,
    decode_request_calls,
    decode_typed_method_response,
    encode_request,
)


class JmapWireTests(unittest.TestCase):
    def test_query_get_reference_is_fixed_and_in_batch(self) -> None:
        query = EmailQueryRequest("u1", {"inMailbox": "inbox"}, limit=3, call_id="q1")
        get = EmailGetRequest("u1", ResultReference("q1"), call_id="g1")
        request = JmapRequest((query.to_method_call(), get.to_method_call()))
        wire = request.to_wire()
        self.assertEqual(wire["methodCalls"][1][1]["#ids"]["path"], "/ids")
        self.assertEqual(wire["methodCalls"][1][1]["#ids"]["resultOf"], "q1")
        self.assertIn('"methodCalls"', encode_request(request))
        with self.assertRaises(InvalidJmapInput):
            JmapRequest((get.to_method_call(), query.to_method_call()))
        with self.assertRaises(InvalidJmapInput):
            JmapRequest((get.to_method_call(),))

    def test_query_changes_removed_are_string_ids(self) -> None:
        response = EmailQueryChangesResponse(
            "u1", "q0", "q1", removed=("b",), added=(), total=2
        )
        self.assertEqual(response.to_arguments()["removed"], ["b"])
        decoded = decode_typed_method_response(
            '["Email/queryChanges", {"accountId":"u1","oldQueryState":"q0",'
            '"newQueryState":"q1","removed":["b"],"added":[],"total":2},"qc1"]'
        )
        self.assertEqual(decoded.removed, ("b",))

    def test_get_reorders_by_id_and_rejects_duplicate(self) -> None:
        response = EmailGetResponse.from_arguments(
            {
                "accountId": "u1",
                "state": "e1",
                "list": [{"id": "b"}, {"id": "a"}],
                "notFound": [],
            }
        )
        self.assertEqual([obj.id for obj in response.list], ["b", "a"])
        self.assertEqual(list(response.by_id()), ["b", "a"])
        with self.assertRaises(ProtocolFailure):
            EmailGetResponse.from_arguments(
                {
                    "accountId": "u1",
                    "state": "e1",
                    "list": [{"id": "a"}, {"id": "a"}],
                    "notFound": [],
                }
            )

    def test_method_error_preserves_unknown_arguments(self) -> None:
        error = decode_typed_method_response(
            '["error", {"type":"cannotCalculateChanges", "retryAfter":3}, "c1"]'
        )
        self.assertEqual(error.type, "cannotCalculateChanges")
        self.assertEqual(error.raw["retryAfter"], 3)

    def test_index_equal_total_is_rejected(self) -> None:
        with self.assertRaises(ProtocolFailure):
            EmailQueryChangesResponse.from_arguments(
                {
                    "accountId": "u1",
                    "oldQueryState": "q0",
                    "newQueryState": "q1",
                    "removed": [],
                    "added": [{"id": "x", "index": 2}],
                    "total": 2,
                }
            )

    def test_query_changes_total_is_optional_per_rfc8620(self) -> None:
        response = EmailQueryChangesResponse.from_arguments(
            {
                "accountId": "u1",
                "oldQueryState": "q0",
                "newQueryState": "q1",
                "removed": [],
                "added": [],
            }
        )
        self.assertIsNone(response.total)
        self.assertNotIn("total", response.to_arguments())

    def test_query_page_cannot_extend_beyond_total(self) -> None:
        with self.assertRaises(ProtocolFailure):
            decode_typed_method_response(
                '["Email/query", {"accountId":"u1","queryState":"q1",'
                '"ids":["a"],"position":2,"total":2},"q1"]'
            )

    def test_query_requires_calculate_total(self) -> None:
        with self.assertRaises(InvalidJmapInput):
            EmailQueryRequest("u1", {"inMailbox": "inbox"}, calculate_total=False)
        with self.assertRaises(ProtocolFailure):
            decode_request_calls(decode_request(
                '{"using":["urn:ietf:params:jmap:core","urn:ietf:params:jmap:mail"],'
                '"methodCalls":[["Email/query",{"accountId":"u1",'
                '"filter":{"inMailbox":"inbox"},"sort":[{"property":"receivedAt",'
                '"isAscending":false}],"position":0,"calculateTotal":false},"q1"]]}'
            ))

    def test_present_null_is_not_treated_as_absent(self) -> None:
        with self.assertRaises(ProtocolFailure):
            decode_typed_method_response(
                '["Email/query", {"accountId":"u1","queryState":"q1",'
                '"ids":[],"position":0,"total":0,"canCalculateChanges":null},"q1"]'
            )

    def test_unread_filter_is_encoded_as_an_and_operator(self) -> None:
        request = EmailQueryRequest(
            "u1",
            {"inMailbox": "inbox", "notKeyword": "$seen"},
            call_id="q-unread",
        )
        self.assertEqual(
            request.to_arguments()["filter"],
            {
                "operator": "AND",
                "conditions": [
                    {"inMailbox": "inbox"},
                    {"notKeyword": "$seen"},
                ],
            },
        )
        decoded = EmailQueryRequest(
            "u1",
            {
                "operator": "AND",
                "conditions": [
                    {"notKeyword": "$seen"},
                    {"inMailbox": "inbox"},
                ],
            },
        )
        self.assertEqual(decoded.to_arguments()["filter"]["conditions"][0], {"inMailbox": "inbox"})

    def test_unread_filter_rejects_partial_or_generic_operator(self) -> None:
        with self.assertRaises(InvalidJmapInput):
            EmailQueryRequest("u1", {"operator": "OR", "conditions": []})
        with self.assertRaises(InvalidJmapInput):
            EmailQueryRequest("u1", {"inMailbox": "inbox", "notKeyword": "$flag"})

    def test_fixed_arrays_reject_mappings_and_explicit_null_ids(self) -> None:
        # A Python mapping is iterable, but it is not a JSON array.  The
        # adapter must reject it instead of accidentally treating its keys as
        # message IDs/properties.
        with self.assertRaises(InvalidJmapInput):
            EmailGetRequest("u1", {"a": 1})
        with self.assertRaises(InvalidJmapInput):
            EmailGetRequest("u1", ["a"], properties={"id": True})
        with self.assertRaises(InvalidJmapInput):
            EmailObject("a", {"id": None})

    def test_json_object_keys_and_response_containers_are_strict(self) -> None:
        with self.assertRaises(InvalidJmapInput):
            EmailObject("a", {1: "invalid JSON member name"})
        with self.assertRaises(ProtocolFailure):
            decode_request(
                {
                    "using": [
                        "urn:ietf:params:jmap:core",
                        "urn:ietf:params:jmap:mail",
                    ],
                    "methodCalls": [
                        [
                            "Email/query",
                            {
                                "accountId": "u1",
                                "filter": {1: "not a JSON object member"},
                                "sort": [{"property": "receivedAt", "isAscending": False}],
                            },
                            "q1",
                        ]
                    ],
                }
            )
        call = MethodCall("Email/query", {}, "q1")
        with self.assertRaises(InvalidJmapInput):
            JmapRequest(None)
        with self.assertRaises(InvalidJmapInput):
            JmapResponse([call])
        with self.assertRaises(InvalidJmapInput):
            JmapResponse([MethodResponse("Email/query", {}, "q1"), 1])

    def test_changes_and_get_response_arrays_are_required(self) -> None:
        # RFC 8620 §5.1/§5.2 define these as required Id[] response members;
        # an empty array is valid, while an omitted member is malformed.
        get_without_not_found = {
            "accountId": "u1",
            "state": "e1",
            "list": [],
        }
        with self.assertRaises(ProtocolFailure):
            EmailGetResponse.from_arguments(get_without_not_found)

        changes = {
            "accountId": "u1",
            "oldState": "e0",
            "newState": "e1",
            "hasMoreChanges": False,
            "created": [],
            "updated": [],
            "destroyed": [],
        }
        for omitted in ("created", "updated", "destroyed"):
            response = dict(changes)
            del response[omitted]
            with self.subTest(omitted=omitted):
                with self.assertRaises(ProtocolFailure):
                    decode_typed_method_response(["Email/changes", response, "c1"])


if __name__ == "__main__":
    unittest.main()

