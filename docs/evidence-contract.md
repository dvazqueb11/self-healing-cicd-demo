# The Evidence Contract

Every deterministic check in this repository (unit tests, coverage,
benchmark) ultimately gets normalized into one JSON document called
**evidence**, produced once per CI run, for a real pull request's real head
commit. Evidence is the only thing the remediation agent, the classifier,
and the policy engine ever read to decide what happened and whether to act.
None of them parse raw tool output directly, and none of them key any
decision on *which pull request* this is beyond the provenance fields
below — a real developer PR touching any file at all produces evidence in
exactly the same shape.

Schema: `framework/schemas/evidence-schema-v1.json` (JSON Schema draft-07,
`schema_version: "2.0"` — the filename is kept for path stability even
though its content is now version 2.0; see the file's own `description`
field). Validator: `framework/schemas/evidence_lib.py` (dependency-free; no
`jsonschema` package required).

## Why a contract, not raw logs

- **Determinism**: the classifier and policy engine must behave the same way
  every time given the same evidence. Parsing ad hoc log text is fragile and
  silently drifts as tool output changes; a schema-checked JSON document
  does not.
- **Boundedness**: the agent is handed a small, structured, size-limited
  document instead of unbounded raw CI logs — cheaper, safer, and far less
  likely to accidentally leak something sensitive into the model's context.
- **Auditability**: every decision after evidence collection (classification,
  policy, validation) is pure, inspectable code that runs identically outside
  of CI. `tests/automation/test_evidence_schema.py` and
  `test_classifier.py` exercise this directly.
- **Trustworthy provenance**: evidence carries enough information
  (`repository`, `pr_number`, `base_branch`/`base_sha`, `head_branch`/
  `head_sha`, `workflow_run_id`, `signature`) that the remediation workflow
  can cross-check it against the live GitHub API before trusting it at all
  — see "Provenance and tamper-evidence" below.

## Fields

| Field | Meaning |
|---|---|
| `schema_version` | Always `"2.0"` for this contract version. |
| `scenario` | Optional, nullable. Only meaningful as provenance for evidence produced via the optional demo-fixture helper scripts (`scripts/create_demo_failure.py` / `scripts/demo_submit_pr.py`). Never used by the classifier, policy engine, or validator. |
| `event_source` | Identifier of the collector that produced this evidence (currently always `scripts/collect_evidence.py`). |
| `repository` | `owner/repo` of the pull request's repository. |
| `pr_number` | The real pull request number this evidence was collected for. |
| `base_branch`, `base_sha` | The pull request's base branch name and base commit SHA. |
| `head_branch`, `head_sha` | The pull request's head branch name and the exact commit CI built and tested. This is the SHA the remediation workflow checks out and diffs against — never `main`. |
| `workflow_run_id` | The CI workflow run id that produced this evidence, cross-checked by the remediation workflow against the triggering `workflow_run` event. |
| `changed_files`, `diff_file` | The pull request's own change (relative to `base_sha`), normalized and size-limited. |
| `failure_category` | `unit-test-failure`, `coverage-gap`, `performance-regression`, or `unsupported`. Determined from real measurements by priority (unit tests first, then coverage, then performance), never from a scenario id. |
| `failed_command` | The exact deterministic command that failed (e.g. `ctest --output-on-failure`). |
| `failure_signature` | A stable string used for de-duplication/escalation grouping. |
| `concise_log_file` | Path to a size-limited log excerpt. Full raw logs are never handed to the agent. |
| `relevant_files` | The minimal file set the agent should even be looking at. |
| `measurements` | Category-specific structured numbers: passed/failed test names, coverage percent, uncovered lines, changed-line coverage (added/changed executable lines and whether each is covered), benchmark medians in milliseconds. |
| `runtime_budget` | `target_minutes` (from policy) and `elapsed_minutes` (measured). |
| `attempt_number` | Starts at `1`; the policy engine rejects anything greater than the category's `max_attempts` (`1` for every category in this demo). |
| `signature` | A sha256 hex digest over every other field, computed by `collect_evidence.py`. See "Provenance and tamper-evidence" below. |

## Who produces and consumes evidence

```
scripts/collect_evidence.py   → .evidence/evidence.json        (schema-checked, signed)
                                  (CI uploads this as a workflow artifact)
check_remediation_guards.py   → loop-prevention decision        (runs before evidence is even downloaded)
remediation workflow           → downloads the artifact, re-verifies schema + signature + live provenance
scripts/classify_failure.py   → .evidence/classification.json   (reads evidence.json)
scripts/evaluate_policy.py    → policy decision                 (reads evidence.json + classification.json)
scripts/validate_change.py    → re-derives patch-scope base_branch from evidence.json's head_sha,
                                  and the coverage profile's changed-line-coverage base from base_sha
remediation agent              → reads evidence.json, classification.json, policy-decision.json,
                                  and remediation-context.md as its only input
```

## Provenance and tamper-evidence

`signature` is a sha256 digest over the canonical (sorted-key) JSON of every
other field, computed in the same trusted CI job that measured the failure.
`evidence_lib.verify_signature()` recomputes it and compares. This detects
accidental corruption/truncation of the artifact in transit and any attempt
to hand-edit `evidence.json` after collection without also recomputing a
matching signature — it is **tamper-evidence**, not a cryptographic
guarantee of authorship. The remediation workflow additionally
cross-checks `repository`, `pr_number`, `head_sha`, and `workflow_run_id`
against the live GitHub API (the triggering `workflow_run` event and the
pull request's current state) before trusting the evidence at all. Combined,
this is sufficient for this demo's documented threat model; see
`docs/architecture.md#known-limitations` for how a production system would
harden this further (a genuine cross-job trust boundary, evidence signed
with a key the remediation job does not hold).

## Two diff bases, used for different questions

`scripts/validate_change.py` diffs the remediation's patch scope and
anti-weakening checks against `evidence.head_sha` by default — the exact
failing commit, never `main` and never `evidence.base_sha`. This matters
because the developer's own pull request may itself touch files that would
be forbidden for the *remediation* to re-touch; diffing against anything
earlier than the failing commit would incorrectly blame the agent for the
developer's own changes. The `coverage-gap` category's changed-line-coverage
check is the deliberate exception: it diffs against `evidence.base_sha`
instead, because that check is asking "did the developer's own new
production code get covered," which is only answerable relative to the PR's
own base. See `docs/architecture.md` for the full rationale.

## Null measurements are treated as missing evidence

`classify_failure.py` explicitly treats `None` the same as a missing key:
any required measurement that is `null` makes the evidence `"unsupported"`,
failing closed rather than producing a confident-looking but meaningless
classification. `classify_failure.py` additionally re-derives, from the
measurements alone, whether the reported `failure_category` is actually
consistent with its own numbers (for example: a claimed `coverage-gap` where
`coverage_percent >= threshold_percent` is rejected as internally
inconsistent) — a defense-in-depth check independent of however
`collect_evidence.py` picked the category.
