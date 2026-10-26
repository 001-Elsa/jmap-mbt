#!/usr/bin/env python3
"""Print the three planning-document demonstrations with their expected trace."""

from __future__ import annotations

import json
from pathlib import Path

from replay_vectors import replay_case


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "tests" / "vectors" / "incremental_cases.json").read_text(encoding="utf-8"))
wanted = {"C01", "C02", "C05"}
for case in data["cases"]:
    if case["id"] not in wanted:
        continue
    actual, errors = replay_case(case)
    print(f"## {case['id']} {case['title']}")
    print(json.dumps({"actual": actual, "expected": case["expected"], "errors": errors}, ensure_ascii=False, indent=2))

