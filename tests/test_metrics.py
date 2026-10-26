#!/usr/bin/env python3
"""Deterministic invariants for the synthetic JMAP view metric harness."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_metrics import DEFAULT_FIXTURE, run


class MetricsHarnessTest(unittest.TestCase):
    def _run(self, directory: str):
        return run(DEFAULT_FIXTURE, Path(directory) / "metrics")

    def test_replay_is_deterministic_and_explicitly_local(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = self._run(first)
            right = self._run(second)
        # Output paths are relative to the repository, so a rerun can be
        # compared as a semantic JSON document without timestamps.
        self.assertEqual(left, right)
        self.assertEqual(left["scenario_count"], 15)
        self.assertEqual(left["evidence"], "synthetic-local")
        self.assertFalse(left["live_server"])
        self.assertFalse(left["performance_claim"])
        self.assertEqual(left["trace_version"], 2)
        self.assertTrue(left["run_id"].startswith("synthetic-"))
        expected_sha = hashlib.sha256(DEFAULT_FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(left["fixture_sha256"], expected_sha)

    def test_trace_and_counter_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self._run(directory)
            for scenario in report["scenarios"]:
                metrics = scenario["metrics"]
                trace_path = Path(directory) / "metrics" / "traces" / f"{scenario['scenario_id']}.json"
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
                events = trace["events"]
                controls = trace["controls"]
                self.assertEqual(metrics["responses_total"], len(events), scenario["scenario_id"])
                self.assertEqual(metrics["control_events"], len(controls), scenario["scenario_id"])
                self.assertEqual(trace["run_id"], report["run_id"])
                self.assertEqual(metrics["requests_attempted"], metrics["responses_total"])
                self.assertEqual(sum(item.get("responses", 0) for item in metrics["requests_by_method"].values()), len(events))
                self.assertEqual(metrics["response_bytes"], None)
                self.assertFalse(metrics["response_bytes_available"])
                self.assertEqual(trace["fixture_sha256"], report["fixture_sha256"])
                self.assertIn("account_scope_hash", trace)
                self.assertIn("query_key_hash", trace)
                for control in controls:
                    self.assertIn("before", control)
                    self.assertIn("after", control)
                    self.assertIn("ordered_ids_hash", control["before"])
                    self.assertIn("ordered_ids_hash", control["after"])
                    self.assertNotIn("ordered_ids", control["before"])
                    self.assertNotIn("objects", control["before"])
                for event in events:
                    self.assertEqual(event["fixture_sha256"], report["fixture_sha256"])
                    self.assertIn("before", event)
                    self.assertIn("after", event)
                    self.assertIn("ordered_ids_hash", event["before"])
                    self.assertIn("ordered_ids_hash", event["after"])
                    self.assertNotIn("ordered_ids", event["before"])
                    self.assertNotIn("objects", event["before"])
                    # A dropped old-generation response has zero state delta.
                    if event["decision"] == "Dropped":
                        self.assertEqual(event["before"]["state_hash"], event["after"]["state_hash"])
                        self.assertEqual(event["reason_code"], "stale_response_discarded")
                    if event["decision"] in {"Pending", "NeedsRefresh"}:
                        self.assertTrue(event["after"]["pending_work"], scenario["scenario_id"])
                    # Trace responses never carry fixture object payloads.
                    payload = json.dumps(event, ensure_ascii=False)
                    self.assertNotIn("example.test", payload)
                    self.assertNotIn('"subject"', payload)

    def test_budget_and_recovery_scenarios_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self._run(directory)
        by_id = {item["scenario_id"]: item for item in report["scenarios"]}
        self.assertEqual(by_id["C12"]["metrics"]["budget_termination"]["reason"], "call_budget_exhausted")
        self.assertEqual(by_id["C14"]["metrics"]["budget_termination"]["reason"], "round_budget_exhausted")
        self.assertEqual(by_id["C06"]["metrics"]["email_rebuilds"], 1)
        self.assertEqual(by_id["C07"]["metrics"]["query_rebuilds"], 1)
        self.assertEqual(by_id["C10"]["metrics"]["stale_responses_dropped"], 1)
        self.assertEqual(by_id["C10"]["metrics"]["final"]["status"], "Ready")
        self.assertEqual(by_id["C11"]["metrics"]["requests_planned_by_method"], {"Email/get": 1, "Email/query": 1})
        self.assertEqual(by_id["C12"]["metrics"]["requests_planned_by_method"], {"Email/get": 2})
        with tempfile.TemporaryDirectory() as directory:
            report = self._run(directory)
            by_trace = {
                item["scenario_id"]: json.loads((Path(directory) / "metrics" / "traces" / f"{item['scenario_id']}.json").read_text(encoding="utf-8"))
                for item in report["scenarios"]
            }
        self.assertEqual(by_trace["C10"]["controls"][0]["kind"], "generation_switch")
        self.assertEqual(by_trace["C12"]["final"]["pending_work"][0], "budget:call")
        self.assertTrue(by_trace["C12"]["final"]["pending_work"][1].startswith("get_hash:"))


if __name__ == "__main__":
    unittest.main()
