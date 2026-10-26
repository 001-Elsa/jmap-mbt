#!/usr/bin/env python3
"""Build a reproducible local-vector evidence record.

The report intentionally calls out what was *not* tested.  This keeps a local
fixture run from being mistaken for a live JMAP interoperability result.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import re
import subprocess
import sys
import os
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
fixture = ROOT / "tests" / "vectors" / "incremental_cases.json"
runner = ROOT / "examples" / "replay_vectors.py"
oracle_runner = ROOT / "tests" / "verify.py"
metrics_runner = ROOT / "scripts" / "benchmark_metrics.py"
differential_runner = ROOT / "scripts" / "run_differential.py"
metrics_output = ROOT / "outputs" / "metrics" / "metrics.json"
differential_output = ROOT / "outputs" / "MoonJMAP-跨实现逐步对拍-2026-10-25.json"
output = ROOT / "outputs" / "MoonJMAP-本地向量验收报告-2026-10-25.json"
MOON = Path(os.environ.get("MOON") or shutil.which("moon") or Path.home() / ".moon" / "bin" / "moon")


def inherited_env() -> dict[str, str]:
    """Return the caller environment unchanged for direct evidence."""
    return dict(os.environ)


def bundled_node_env() -> tuple[dict[str, str] | None, str | None]:
    """Find the desktop-bundled Node runtime without hiding PATH failures.

    The report records both executions: the direct inherited-PATH result and,
    when available, a separately labelled bundled-runtime result.  This keeps
    a missing system ``node`` observable while still proving that the JS
    target can run in the Codex desktop runtime used for delivery.
    """
    if shutil.which("node", path=os.environ.get("PATH")):
        return None, None
    candidates = sorted((Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            env = dict(os.environ)
            env["PATH"] = str(candidate.parent) + os.pathsep + env.get("PATH", "")
            return env, str(candidate)
    return None, None


def run_moon_test(target: str, env: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        [str(MOON), "test", "--target", target],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    output_text = result.stdout + result.stderr
    return {
        "returncode": result.returncode,
        "summary": [line for line in output_text.splitlines() if "Total tests:" in line or "passed:" in line or "failed:" in line],
        "tail": output_text.splitlines()[-5:],
    }


def run_python_wire_tests() -> dict[str, object]:
    """Run the fixed JMAP wire regression suite and record its count.

    This is intentionally a separate evidence stream from the language-neutral
    vector replay and the independent state-machine oracle.  Keeping the
    command here makes the machine-readable report fail visibly if the wire
    adapter tests are missing, malformed, or no longer discoverable.
    """

    env = dict(os.environ)
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_jmap_wire.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    output_text = result.stdout + result.stderr
    match = re.search(r"Ran (\d+) tests?", output_text)
    count = int(match.group(1)) if match else None
    passed = count if result.returncode == 0 and count is not None else 0
    return {
        "command": "PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_jmap_wire.py'",
        "returncode": result.returncode,
        "tests": count,
        "passed": passed,
        "tail": output_text.splitlines()[-8:],
    }


def main() -> int:
    completed = subprocess.run([sys.executable, str(runner)], cwd=ROOT, text=True, capture_output=True)
    oracle = subprocess.run([sys.executable, str(oracle_runner), "--strict-structure"], cwd=ROOT, text=True, capture_output=True)
    wire_tests = run_python_wire_tests()
    metrics = subprocess.run(
        [sys.executable, str(metrics_runner)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    differential = subprocess.run(
        [sys.executable, str(differential_runner)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    moon_checks: dict[str, dict[str, object]] = {}
    if MOON.exists():
        for target in ("native", "js", "wasm-gc"):
            check = subprocess.run([str(MOON), "check", "--target", target], cwd=ROOT, text=True, capture_output=True)
            output_text = check.stdout + check.stderr
            output_tail = output_text.splitlines()[-3:]
            match = re.search(r"\((\d+) warnings, (\d+) errors\)", output_text)
            item: dict[str, object] = {"returncode": check.returncode, "tail": output_tail}
            if match:
                item["warnings"] = int(match.group(1))
                item["errors"] = int(match.group(2))
            moon_checks[target] = item
        direct_env = inherited_env()
        moon_tests: dict[str, object] = {}
        for target in ("wasm", "wasm-gc", "js", "native"):
            moon_tests[target] = run_moon_test(target, direct_env)
        bundled_env, bundled_node = bundled_node_env()
        bundled_tests: dict[str, object] = {}
        if bundled_env is not None:
            bundled_tests["js"] = run_moon_test("js", bundled_env)
    else:
        moon_tests = {"available": False}
        bundled_tests = {}
        bundled_node = None
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    lines = [line for line in completed.stdout.splitlines() if line.startswith(("PASS ", "FAIL "))]
    passed = sum(line.startswith("PASS ") for line in lines)
    failed = sum(line.startswith("FAIL ") for line in lines)
    report = {
        "report_type": "synthetic_vector_replay",
        "generated_on": str(date.today()),
        "fixture": str(fixture.relative_to(ROOT)),
        "fixture_sha256": fixture_sha,
        "cases": len(lines),
        "passed": passed,
        "failed": failed,
        "command": "python3 examples/replay_vectors.py",
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "independent_oracle": {
            "command": "python3 tests/verify.py --strict-structure",
            "returncode": oracle.returncode,
            "stdout": oracle.stdout,
            "stderr": oracle.stderr,
        },
        "python_wire_tests": wire_tests,
        "synthetic_view_metrics": {
            "command": "python3 scripts/benchmark_metrics.py",
            "returncode": metrics.returncode,
            "report": str(metrics_output.relative_to(ROOT)),
            "stdout": metrics.stdout,
            "stderr": metrics.stderr,
            "performance_claim": False,
            "live_server": False,
        },
        "cross_implementation_differential": {
            "command": "python3 scripts/run_differential.py",
            "returncode": differential.returncode,
            "report": str(differential_output.relative_to(ROOT)),
            "stdout": differential.stdout,
            "stderr": differential.stderr,
            "comparison_scope": "bounded common projection and next-plan contract",
            "full_equivalence_claim": False,
            "real_server": False,
        },
        "evidence_boundary": {
            "real_server_interop": False,
            "moonbit_cli_verified": bool(moon_checks) and all(item["returncode"] == 0 for item in moon_checks.values()),
            "moonbit_check": moon_checks,
            "moonbit_tests": moon_tests,
            "moonbit_tests_with_bundled_runtime": bundled_tests,
            "bundled_node": bundled_node,
            "moonbit_test_runtime_note": "Direct results preserve the inherited PATH. If the system PATH lacks node, a separately labelled Codex bundled Node run is recorded under moonbit_tests_with_bundled_runtime; it must not be confused with the direct JS result. Native linking is reported separately.",
            "network_or_authentication_tested": False,
            "performance_claim": False,
        },
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(f"{passed}/{len(lines)} vector cases passed; sha256={fixture_sha}")
    return 0 if all(
        result == 0
        for result in (completed.returncode, oracle.returncode, int(wire_tests["returncode"]), metrics.returncode, differential.returncode)
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

