# Extension Guide

## Adding a fourth scenario

This demo is deliberately structured so adding a new scenario only touches
*scenario-specific* files, never the shared framework or any globally
forbidden path. Follow this order:

1. **Design one specific, classifiable defect.** It must map to exactly one
   `failure_category` already in `framework/schemas/evidence-schema-v1.json`
   (`unit-test-failure`, `coverage-gap`, `performance-regression`), or you'll
   need to extend the schema (see below) — pick an existing category if at
   all possible to keep the loop simple.

2. **Write the fixture** as a plain unified diff against a clean `main`:

   ```sh
   # make your change by hand in a scratch branch, then:
   git diff main > fixtures/<new-scenario>/fixture.patch
   ```

   Write `fixtures/<new-scenario>/metadata.json` describing the scenario id,
   the expected failure category, and a one-line human description. Follow
   the shape of the three existing `metadata.json` files exactly.

3. **Verify the fixture in isolation**: apply it
   (`python3 scripts/create_demo_failure.py <new-scenario>`), confirm it
   trips exactly one deterministic check and no others, then reset
   (`python3 scripts/reset_demo.py <new-scenario>`).

4. **Add a policy block** to
   `.github/policies/self-heal-policy.yml` under `scenarios:` — this *is* a
   change to a globally forbidden path, so it must be made by a human
   maintainer directly, never by the remediation agent. Set
   `permitted_paths` as narrowly as the fix genuinely requires,
   `max_changed_files`/`max_inserted_lines`/`max_deleted_lines` generously
   enough for a real fix but not so wide that an unrelated rewrite would
   pass, and `required_validation_profile` to a new or existing profile name
   in `scripts/validate_change.py`.

5. **Add a validation profile** to `scripts/validate_change.py` if the new
   scenario's "is it actually fixed?" check isn't already one of the
   existing profiles (`unit-test-remediation`, `coverage-remediation`,
   `performance-remediation`).

6. **Add the scenario to the `workflow_dispatch` input's `options`** in
   `.github/workflows/self-heal-remediation.md`, then recompile:

   ```sh
   gh aw compile
   git add .github/workflows/self-heal-remediation.md \
           .github/workflows/self-heal-remediation.lock.yml
   ```

7. **Write automation tests** covering the new fixture and policy block,
   following the pattern in `tests/automation/test_fixtures.py` and
   `test_policy_engine.py`.

8. **Important constraint: `CMakeLists.txt` is globally forbidden.**
   Because registering a brand-new CTest test case requires editing
   `CMakeLists.txt`, and that file is on the global forbidden-path list
   (it's shared build configuration, not application logic), any new
   coverage-style scenario must be designed so its fix **extends the body of
   an existing test case** (adding assertions/branches it already covers)
   rather than registering a new test. This is exactly how
   `medium-low-coverage` works today — look at
   `tests/job_processor_tests.cpp` and `fixtures/medium-low-coverage/` for
   the pattern to copy.

## Adding an external event adapter (not implemented — interface only)

This repository intentionally does **not** implement adapters that pull
failure signals from external systems (a paging tool, a ticketing system, a
chat-ops bot, etc.) — see `docs/architecture.md#why-no-external-adapters`
for the reasoning. If you want to build one as a follow-on project, the
integration point is narrow and well-defined:

- An adapter's only job is to produce a valid
  `framework/schemas/evidence-schema-v1.json` document — nothing downstream
  of `collect_evidence.py` needs to know or care where the evidence came
  from.
- `scripts/collect_evidence.py` is the current, sole implementation of
  "produce evidence from this repository's own build/test/coverage output."
  A new adapter would be a sibling script (e.g.
  `scripts/collect_evidence_from_<source>.py`) that gathers whatever signal
  it has access to and writes the same schema, validated by
  `framework/schemas/evidence_lib.py`.
- Everything downstream — `classify_failure.py`, `evaluate_policy.py`, the
  agent, `validate_change.py` — is already adapter-agnostic: it only ever
  reads `.evidence/evidence.json` and does not know or care which collector
  produced it.
- You would also need a way to *trigger* the workflow from that external
  system's event (e.g. a `repository_dispatch` event instead of
  `workflow_dispatch`), and you would need to decide how to authenticate
  that external system to your repository — this is genuinely new attack
  surface and deserves its own security review; it is explicitly out of
  scope for this demo.

Do not build this inside this repository without a clear, separate reason
to do so — the whole point of this project is that the core loop works
end-to-end with zero external dependencies beyond GitHub itself.
