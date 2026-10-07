# The Evidence Contract

Every deterministic check in this repository (unit tests, coverage,
benchmark) ultimately gets normalized into one JSON document called
**evidence**. Evidence is the only thing the remediation agent, the
classifier, and the policy engine ever read to decide what happened and
whether to act. None of them parse raw tool output directly.

Schema: `framework/schemas/evidence-schema-v1.json` (JSON Schema draft-07).
Validator: `framework/schemas/evidence_lib.py` (dependency-free; no
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

## Fields

| Field | Meaning |
|---|---|
| `schema_version` | Always `"1.0"` for this contract version. |
| `scenario` | One of `easy-unit-test`, `medium-low-coverage`, `advanced-performance`. |
| `event_source` | Identifier of the collector that produced this evidence (currently always `scripts/collect_evidence.py`). |
| `repository`, `branch`, `triggering_sha`, `workflow_run` | Provenance: where and on what commit this evidence was collected. |
| `changed_files`, `diff_file` | The fixture's change, normalized and size-limited. |
| `failure_category` | `unit-test-failure`, `coverage-gap`, `performance-regression`, or `unsupported`. |
| `failed_command` | The exact deterministic command that failed (e.g. `ctest --output-on-failure`). |
| `failure_signature` | A stable string used for de-duplication/escalation grouping. |
| `concise_log_file` | Path to a size-limited log excerpt. Full raw logs are never handed to the agent. |
| `relevant_files` | The minimal file set the agent should even be looking at. |
| `measurements` | Scenario-specific structured numbers: passed/failed test names, coverage percent and uncovered lines, benchmark medians in milliseconds. |
| `runtime_budget` | `target_minutes` (from policy) and `elapsed_minutes` (measured). |
| `attempt_number` | Always `1` in this demo; the policy engine rejects anything greater. |

## Who produces and consumes evidence

```
scripts/collect_evidence.py   → .evidence/evidence.json       (schema-checked)
scripts/classify_failure.py   → .evidence/classification.json  (reads evidence.json)
scripts/evaluate_policy.py    → policy decision (reads evidence.json + classification.json)
scripts/validate_change.py    → re-derives base_branch from evidence.json's triggering_sha
remediation agent              → reads all three JSON files as its only input
```

## Null measurements are treated as missing evidence

An earlier version of `classify_failure.py` only checked whether a
measurement *key* was present, not whether its *value* was `null`. A
coverage run that failed to produce real numbers (for example, because
`ctest` hadn't been run yet, so no `.gcda` coverage data existed) could pass
a classifier check with `"coverage_percent": null` — technically "present".
`classify_failure.py` now explicitly treats `None` the same as a missing
key: any required measurement that is `null` makes the evidence
`"unsupported"`, failing closed rather than producing a confident-looking
but meaningless classification. `collect_evidence.py` was also fixed to run
`ctest` (so the coverage instrumentation actually has data) before invoking
`scripts/measure_coverage.py`.

## Patch-scope diffing uses the failure commit, not `main`

`scripts/validate_change.py` diffs the remediation against
`evidence.triggering_sha` by default, not literal `main`. This matters
because a scenario's *fixture* may itself touch files that would be
forbidden for the *remediation* to re-touch — diffing against `main` would
incorrectly blame the agent for the fixture's own pre-existing change. See
`docs/architecture.md` for more on this.
