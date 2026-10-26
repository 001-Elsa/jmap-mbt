#!/usr/bin/env python3
"""Build a fixed Email/query request and decode its RFC-shaped response.

The example uses the repository's narrow ``src/jmap`` codec, but never opens a
socket.  It demonstrates the wire boundary that a transport adapter would
call; synchronization decisions remain in ``src/sync``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jmap import EmailQueryRequest, JmapRequest, decode_method_response, decode_typed_method_response, encode_request, encode_method_response  # noqa: E402


def main() -> int:
    vectors = json.loads((ROOT / "tests/vectors/rfc8621_vectors.json").read_text(encoding="utf-8"))
    query = next(item for item in vectors["vectors"] if item["id"] == "RFC-Q-001")
    args = query["arguments"]
    request = JmapRequest(
        (
            EmailQueryRequest(
                account_id=args["accountId"],
                filter=args["filter"],
                sort=args["sort"],
                collapse_threads=args["collapseThreads"],
                position=args["position"],
                limit=args["limit"],
                calculate_total=True,
                call_id="q1",
            ).to_call(),
        )
    )
    print("request:")
    print(encode_request(request))

    response = next(item for item in vectors["vectors"] if item["id"] == "RFC-Q-001")
    typed = decode_typed_method_response(["Email/query", response["response"], "q1"])
    print("decoded:")
    print(type(typed).__name__, typed)

    # A response can be encoded again without changing method tuple shape.
    print("response tuple:")
    method_response = decode_method_response(["Email/query", response["response"], "q1"])
    print(encode_method_response(method_response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

