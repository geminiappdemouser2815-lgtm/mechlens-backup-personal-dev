"""pytest coverage for the release-evidence command-line gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_evidence_gate as gate


def write_file(directory: Path, name: str, contents: str) -> Path:
    path = directory / name
    path.write_text(contents, encoding="utf-8")
    return path


def write_acceptance(directory: Path, delta: float = 0.000039) -> Path:
    passed = delta <= 0.0001
    return write_file(
        directory,
        "acceptance.json",
        json.dumps(
            {
                "release": "2.16.0",
                "threshold_abs_logit_delta": 0.0001,
                "results": [{"family": "gemma-3", "max_logit_delta": delta, "pass": passed}],
                "summary": {"total": 1, "passed": int(passed), "failed": int(not passed)},
            }
        ),
    )


def test_fails_when_a_recorded_delta_exceeds_the_declared_gate(tmp_path: Path, capsys) -> None:
    exit_code = gate.main(["--acceptance", str(write_acceptance(tmp_path, 0.00011))])

    assert exit_code == 1
    assert "FAIL LOGIT_GATE_FAILED" in capsys.readouterr().out


def test_flags_a_green_result_contradicted_by_matching_triage(tmp_path: Path, capsys) -> None:
    acceptance = write_acceptance(tmp_path)
    queue = write_file(tmp_path, "issues.csv", "issue,title,status\n1121,Gemma-3 mismatch,closed\n")
    note = write_file(
        tmp_path,
        "triage_1121.md",
        "Issue #1121: correctness regression after v2.16.0; logits do not match HF.",
    )

    exit_code = gate.main(
        ["--acceptance", str(acceptance), "--triage", str(queue), "--evidence", str(note)]
    )

    assert exit_code == 2
    assert "FAIL RECONCILIATION_CONFLICT" in capsys.readouterr().out


def test_passes_when_acceptance_is_green_and_no_regression_evidence_exists(tmp_path: Path, capsys) -> None:
    exit_code = gate.main(["--acceptance", str(write_acceptance(tmp_path))])

    assert exit_code == 0
    assert "PASS: logit gate is satisfied" in capsys.readouterr().out
