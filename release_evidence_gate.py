#!/usr/bin/env python3
"""Audit release evidence for parity failures and misleading green summaries.

The tool uses only the Python standard library.  It is deliberately tolerant of
the evidence files that existed for TransformerLens v2.16.0: the acceptance
result is JSON, the issue queue is CSV, and post-release context is in Markdown
triage notes.

Exit codes:
  0  acceptance evidence is within its threshold and no reconciliation conflict
     is found.
  1  the acceptance evidence itself fails its declared logit-delta gate.
  2  a clean acceptance result is contradicted by a matching post-release
     correctness regression.
  3  input/format error.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def read_acceptance(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    required = {"release", "threshold_abs_logit_delta", "results", "summary"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"{path}: missing acceptance field(s): {', '.join(sorted(missing))}")
    if not isinstance(data["results"], list):
        raise ValueError(f"{path}: results must be a list")
    return data


def acceptance_findings(data: dict) -> list[Finding]:
    threshold = float(data["threshold_abs_logit_delta"])
    findings: list[Finding] = []
    for result in data["results"]:
        family = result.get("family", "<unknown>")
        delta = result.get("max_logit_delta")
        passed = result.get("pass")
        if not isinstance(delta, (int, float)):
            findings.append(Finding("INVALID_RESULT", f"{family}: max_logit_delta is missing or non-numeric"))
            continue
        if delta > threshold or passed is not True:
            findings.append(
                Finding(
                    "LOGIT_GATE_FAILED",
                    f"{family}: max_logit_delta={delta:.8g}; threshold={threshold:.8g}; pass={passed!r}",
                )
            )
    summary = data["summary"]
    if summary.get("failed", 0) != len(findings):
        findings.append(
            Finding(
                "SUMMARY_MISMATCH",
                f"summary.failed={summary.get('failed')!r}; calculated failing results={len(findings)}",
            )
        )
    return findings


def read_issue_numbers(queue: Path | None) -> set[str]:
    if queue is None:
        return set()
    with queue.open(newline="", encoding="utf-8") as handle:
        return {row["issue"].strip() for row in csv.DictReader(handle) if row.get("issue")}


def markdown_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.glob("*.md"))
        elif path.suffix.lower() in {".md", ".markdown", ".txt"}:
            yield path


def regression_findings(release: str, issue_numbers: set[str], evidence_paths: Iterable[Path]) -> list[Finding]:
    """Find post-release adapter/correctness regressions tied to ``release``.

    The match is intentionally evidence based, not filename based: the note must
    name the release, name an issue, and use a correctness-regression signal.
    """
    version = re.escape(release)
    release_pattern = re.compile(rf"(?<![\w.])v?{version}(?![\w.])", re.IGNORECASE)
    issue_pattern = re.compile(r"(?:issue\s*#|#)(\d+)", re.IGNORECASE)
    regression_pattern = re.compile(
        r"\b(regression|logits?\s+do\s+not\s+match|correctness\s+(?:bug|regression)|over\s+the\s+\d)",
        re.IGNORECASE,
    )
    findings: list[Finding] = []
    for path in markdown_files(evidence_paths):
        text = path.read_text(encoding="utf-8")
        if not release_pattern.search(text) or not regression_pattern.search(text):
            continue
        issue_ids = sorted(set(issue_pattern.findall(text)))
        if issue_numbers:
            issue_ids = [issue for issue in issue_ids if issue in issue_numbers]
        if issue_ids:
            findings.append(
                Finding(
                    "POST_RELEASE_REGRESSION",
                    f"{path.name}: issue(s) #{', #'.join(issue_ids)} record a correctness regression affecting v{release}",
                )
            )
    return findings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, required=True, help="acceptance_test_output_<version>.json")
    parser.add_argument("--triage", type=Path, help="issue_triage_queue.csv")
    parser.add_argument(
        "--evidence",
        type=Path,
        action="append",
        default=[],
        help="Markdown triage note or directory to scan; repeatable",
    )
    parser.add_argument("--release", help="release to audit; defaults to the acceptance JSON's release field")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        acceptance = read_acceptance(args.acceptance)
        release = args.release or str(acceptance["release"])
        issue_numbers = read_issue_numbers(args.triage)
        logit_failures = acceptance_findings(acceptance)
        regressions = regression_findings(release, issue_numbers, args.evidence)
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as error:
        print(f"INPUT_ERROR: {error}", file=sys.stderr)
        return 3

    print(f"release={release} threshold_abs_logit_delta={acceptance['threshold_abs_logit_delta']}")
    print(f"acceptance: total={acceptance['summary'].get('total')} passed={acceptance['summary'].get('passed')} failed={acceptance['summary'].get('failed')}")
    for finding in logit_failures:
        print(f"FAIL {finding.code}: {finding.message}")
    for finding in regressions:
        print(f"FAIL RECONCILIATION_CONFLICT: acceptance is green, but {finding.message}")

    if logit_failures:
        return 1
    if regressions:
        return 2
    print("PASS: logit gate is satisfied and no contradictory post-release regression was found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
