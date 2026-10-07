# Demo Guide

This walks through running each of the three scenarios end to end, both
locally (fast feedback loop while developing) and via the actual GitHub
Agentic Workflow (the real demo).

## Prerequisites

- `cmake`, a C++17 compiler (g++ or clang++), `gcovr` or `lcov`, Python 3.9+.
- To run the agentic workflow: a GitHub repository with Actions enabled and
  Copilot coding agent / Copilot Premium Requests enabled for the engine
  (`engine: copilot`), since `self-heal-remediation.md` invokes the Copilot
  engine. See the top-level `README.md` "Repository setup" section for the
  exact settings.
- [`gh`](https://cli.github.com/) with the
  [`gh-aw`](https://github.com/githubnext/gh-aw) extension installed, only
  if you intend to edit and recompile the workflow
  (`gh extension install githubnext/gh-aw`).

## Running a scenario locally (no AI involved)

This is the fastest way to see the deterministic half of the pipeline work.

```sh
# 1. Confirm the baseline is healthy
make test        # 11/11 pass
make coverage     # 100% line coverage
make benchmark    # well under the 200ms threshold

# 2. Apply a fixture (pick one)
make apply-easy        # or apply-medium / apply-advanced

# 3. Observe the expected, classified failure
make test          # easy-unit-test: one test now fails
make coverage       # medium-low-coverage: coverage drops below 95%
make benchmark      # advanced-performance: benchmark now exceeds 200ms

# 4. Run the same evidence/classify/policy pipeline the agent would see
python3 scripts/collect_evidence.py --scenario easy-unit-test --build-dir build
python3 scripts/classify_failure.py --evidence .evidence/evidence.json
python3 scripts/evaluate_policy.py --evidence .evidence/evidence.json \
    --classification .evidence/classification.json

# 5. Make a fix by hand, inside permitted_paths, then validate it
python3 scripts/validate_change.py --profile unit-test-remediation \
    --scenario easy-unit-test --build-dir build

# 6. Reset back to a clean baseline
make reset SCENARIO=easy-unit-test
```

Swap `easy-unit-test` for `medium-low-coverage` (profile
`coverage-remediation`) or `advanced-performance` (profile
`performance-remediation`) to walk through the other two scenarios. Each
fixture's `metadata.json` documents exactly what it changes and which
deterministic check it is expected to trip.

## Running the real agentic demo

1. Push this repository to GitHub (public, per project requirements) with
   Actions enabled.
2. Trigger the workflow manually:

   ```sh
   gh workflow run self-heal-remediation.lock.yml -f scenario=easy-unit-test
   ```

   or from the Actions tab: select **Self-Heal Remediation**, click **Run
   workflow**, choose a `scenario`, and run.

3. Watch the run. The job log shows, in order:
   - dependency install
   - fixture applied
   - build with coverage instrumentation
   - evidence collected (`.evidence/evidence.json` printed to the log)
   - classification (`.evidence/classification.json` printed to the log)
   - policy decision printed to the log
   - if policy denies: a `noop` safe-output and the run ends — no AI engine
     is invoked, so no AI Credits are spent
   - if policy allows: the Copilot engine starts, reads `AGENTS.md`, the
     evidence/classification/policy JSON, and the fixture's permitted paths,
     and attempts the smallest correct fix
4. If the agent produces a change that passes `validate_change.py`, it opens
   a **draft pull request** labeled `self-heal` and `demo`, with a title of
   the form `[self-heal:<scenario>] ...` and a body summarizing the failure,
   the fix, and the evidence used.
5. Review the PR like any other. `ci.yml` runs automatically on it,
   independently re-validating build/test/coverage/benchmark and the
   forbidden-path guard — this is the real, final gate (see
   `docs/architecture.md`). Merge it once you're satisfied, exactly like a
   human-authored PR.
6. If the agent cannot produce a validated fix, it opens an **issue**
   instead (labeled `self-heal`, `demo`, `escalation`) describing what it
   tried and why it stopped — no PR is opened in that case.
7. Reset the demo repository back to a clean `main` for a repeat run:

   ```sh
   make reset SCENARIO=easy-unit-test
   ```

   (or simply re-run the workflow against `main` with the fixture re-applied
   fresh each time — `create_demo_failure.py` always applies from a clean
   base).

## What "repeatable" means here

Every scenario is a plain git patch applied to a known-good `main`, every
deterministic check is scripted and produces the same evidence given the
same inputs, and the policy engine's decision is pure data (no network
calls, no non-determinism). Running the same scenario twice in a row
produces the same classification and the same policy decision every time;
the only non-deterministic part of the whole loop is the AI engine's actual
code suggestion, which is exactly the part this architecture is designed to
bound and re-validate rather than trust blindly.
