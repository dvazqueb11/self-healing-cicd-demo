# Extension Guide

## Adding a fourth demo fixture

Policy and classification in this repository are **category-driven**
(`unit-test-failure` / `coverage-gap` / `performance-regression`), not
scenario-driven — a real developer pull request can touch any file, and the
policy/classifier/validator only need to know which category applies, not
which (if any) demo fixture produced it. Adding a new demo fixture therefore
never touches the shared framework, only `fixtures/`:

1. **Pick one of the three existing failure categories.** All three
   categories already have a policy block, a classifier mapping, and a
   `validate_change.py` profile; a new fixture just needs to trip the same
   kind of deterministic check in a new, realistic way. (Adding an entirely
   new *category* is a much bigger change — see below.)

2. **Write the fixture** as a plain unified diff against a clean `main`:

   ```sh
   # make your change by hand in a scratch branch, then:
   git diff main > fixtures/<new-scenario>/fixture.patch
   ```

   Write `fixtures/<new-scenario>/metadata.json` describing the scenario id,
   the expected failure category, and a one-line human description. Follow
   the shape of the three existing `metadata.json` files exactly, and add
   the new scenario id to `KNOWN_SCENARIOS` in
   `scripts/create_demo_failure.py`, `scripts/reset_demo.py`,
   `scripts/demo_submit_pr.py`, and to `SCENARIOS` in
   `framework/schemas/evidence_lib.py` (provenance-only; never used for
   classification).

3. **Verify the fixture in isolation**: apply it
   (`python3 scripts/create_demo_failure.py <new-scenario>`), confirm it
   trips exactly one deterministic check and no others, then reset
   (`python3 scripts/reset_demo.py <new-scenario>`). Then exercise the full
   local loop from `docs/demo-guide.md` against it.

4. **Write automation tests** covering the new fixture, following the
   pattern in `tests/automation/test_fixtures.py`.

5. Optionally, exercise it against the real agentic workflow with
   `python3 scripts/demo_submit_pr.py <new-scenario>` (see
   `docs/demo-guide.md`).

## Adding a new failure category

This is a larger change, since it touches the shared, category-driven
framework rather than just `fixtures/`:

1. Add the category to `FAILURE_CATEGORIES` in
   `framework/schemas/evidence_lib.py` and to the companion
   `framework/schemas/evidence-schema-v1.json`.
2. Add a `REQUIRED_MEASUREMENT_KEYS` entry and a
   `VALIDATION_PROFILE_BY_CATEGORY` entry in `scripts/classify_failure.py`,
   plus a `_category_is_consistent_with_measurements` branch re-deriving the
   category from raw measurement numbers (defense in depth, independent of
   however `collect_evidence.py` picked it).
3. Add a `determine_category` branch (with the right priority relative to
   the existing categories) in `scripts/collect_evidence.py`, plus whatever
   new deterministic check produces its measurements.
4. **Add a policy block** to `.github/policies/self-heal-policy.yml` under
   `categories:` — this *is* a change to a globally forbidden path, so it
   must be made by a human maintainer directly, never by the remediation
   agent. Set `permitted_paths` as narrowly as the fix genuinely requires,
   `max_changed_files`/`max_inserted_lines`/`max_deleted_lines` generously
   enough for a real fix but not so wide that an unrelated rewrite would
   pass, and `required_validation_profile` to a new or existing profile
   name in `scripts/validate_change.py`.
5. **Add a validation profile** to `scripts/validate_change.py` (a
   `profile_<name>` function plus a `--profile` choice) if the new
   category's "is it actually fixed?" check isn't already one of the
   existing profiles (`unit-test-remediation`, `coverage-remediation`,
   `performance-remediation`).
6. Update `AGENTS.md` to describe what the new category permits.
7. **Write automation tests** covering the new category in
   `test_evidence_schema.py`, `test_classifier.py`, and
   `test_policy_engine.py`, following the existing per-category test
   pattern.

## Important constraint: `CMakeLists.txt` is globally forbidden

Because registering a brand-new CTest test case requires editing
`CMakeLists.txt`, and that file is on the global forbidden-path list (it's
shared build configuration, not application logic), any `coverage-gap`-style
fixture or fix must be designed so it **extends the body of an existing test
case** (adding assertions/branches it already covers) rather than
registering a new test. This is exactly how `medium-low-coverage` works
today — look at `tests/job_processor_tests.cpp` and
`fixtures/medium-low-coverage/` for the pattern to copy.

## Adding an external event adapter (not implemented — interface only)

This repository intentionally does **not** implement adapters that pull
failure signals from external systems (a paging tool, a ticketing system, a
chat-ops bot, etc.) — see `docs/architecture.md#why-no-external-adapters`
for the reasoning. If you want to build one as a follow-on project, the
integration point is narrow and well-defined:

- An adapter's only job is to produce a valid, signed
  `framework/schemas/evidence-schema-v1.json` document with real PR
  provenance (`repository`, `pr_number`, `base_branch`/`base_sha`,
  `head_branch`/`head_sha`, `workflow_run_id`) — nothing downstream of
  `collect_evidence.py` needs to know or care where the evidence came from.
- `scripts/collect_evidence.py` is the current, sole implementation of
  "produce evidence from this repository's own build/test/coverage output
  for a given pull request." A new adapter would be a sibling script (e.g.
  `scripts/collect_evidence_from_<source>.py`) that gathers whatever signal
  it has access to and writes the same schema, validated and signed via
  `framework/schemas/evidence_lib.py`.
- Everything downstream — `classify_failure.py`, `evaluate_policy.py`, the
  agent, `validate_change.py` — is already adapter-agnostic: it only ever
  reads `.evidence/evidence.json` and does not know or care which collector
  produced it.
- You would also need a way to *trigger* the remediation workflow from that
  external system's event (e.g. a `repository_dispatch` event instead of
  `workflow_run`), a way to re-derive the loop-prevention context
  (`scripts/check_remediation_guards.py`'s `evaluate_guards()` is a pure
  function; only the context-gathering steps that call it are GitHub
  Actions-specific), and you would need to decide how to authenticate that
  external system to your repository — this is genuinely new attack surface
  and deserves its own security review; it is explicitly out of scope for
  this demo.

Do not build this inside this repository without a clear, separate reason
to do so — the whole point of this project is that the core loop works
end-to-end, driven by nothing but real GitHub pull requests, with zero
external dependencies beyond GitHub itself.
