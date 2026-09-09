# Release-readiness evidence

## Principle

**A green result from a past release tells us nothing about the release we are
cutting now. Evidence we have not collected yet is _pending_, not passing.**

Do not convert missing acceptance output, a missing demo sweep, or absent CI
confirmation into a green status by carrying forward an earlier result. A
release is ready only when its own required evidence is present and green.

## Run the evidence gate

Run the gate from the repository root, supplying the release's acceptance JSON,
the triage queue, and the directory or note files that contain triage evidence:

```bash
python3 release_evidence_gate.py \
  --acceptance Adapters/acceptance_test_output_v2.16.0.json \
  --triage Notes/issue_triage_queue.csv \
  --evidence Notes/triage_1121_gemma3_logits.md
```

The paths above are repository-relative. `--evidence` may be supplied more than
once; if it names a directory, the gate scans its Markdown triage notes.

Exit codes:

| Code | Meaning | Release action |
|---:|---|---|
| `0` | The recorded logit gate passes and no matching post-release regression was found. | Continue to the other release gates. |
| `1` | A declared logit threshold failed, a result is invalid, or the acceptance summary contradicts its rows. | Block the release. |
| `2` | A green acceptance record is contradicted by a matching post-release correctness regression. | Do not call the release clean; investigate and record the outcome. |
| `3` | Input is missing or malformed. | Treat the evidence as pending; fix or collect it. |

## Gate states in the audit

| State | Meaning | Maintainer action |
|---|---|---|
| `green` | The current release's required evidence is present and passed. | Retain the artifact and proceed. |
| `do_not_ship` | One or more release blockers remain. | Do not tag. |
| `stale` | Configuration or evidence refers to an old/non-current cut. | Reconcile the version/date before using it. |
| `not_recorded` | No evidence for this release has been provided. | Collect it; this is pending, not green. |
| `needs_decision` | An open item has no explicit release-impact disposition. | Mark it fixed, deferred/non-blocking, or release-blocking. |

## Regenerate the review artifacts

The audit and dashboard are intentionally static, reviewable artifacts. Update
both from the same current-release evidence after running the gate:

1. Run `release_evidence_gate.py` for the target release and retain its output
   and exit code.
2. Update `release_readiness_audit.json` with the target release, the decision,
   every gate state, blockers, measurements, and relative input paths. A missing
   artifact must remain `not_recorded`; do not inherit a prior release's pass.
3. Update `release_readiness_dashboard.html` to mirror the audit exactly:
   decision, gate states, open items, measurements, and the same relative
   source paths. Keep it self-contained: no CDN, external fonts, scripts, or
   network requests.
4. Validate the artifacts before committing:

   ```bash
   python3 -m json.tool release_readiness_audit.json >/dev/null
   python3 - <<'PY'
   from html.parser import HTMLParser
   from pathlib import Path
   HTMLParser().feed(Path("release_readiness_dashboard.html").read_text())
   print("dashboard HTML parsed")
   PY
   ```

## Verify tests with uv

In the repository, use its declared development dependencies:

```bash
uv run pytest -q tests/test_release_evidence_gate.py
```

For a standalone checkout that does not yet declare pytest, use:

```bash
uv run --with pytest pytest -q tests/test_release_evidence_gate.py
```

The tests cover the three required outcomes: direct logit-gate failure, a
green-result/triage reconciliation conflict, and a clean passing case.
