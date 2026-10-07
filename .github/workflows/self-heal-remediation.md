---
description: >
  Single bounded remediation agent for the self-healing CI/CD demo. Given a
  scenario that has already been applied, built, measured, classified, and
  policy-approved by deterministic steps, proposes the smallest correct code
  change, validates it with the same deterministic tools used to judge it,
  and opens a draft pull request for human review. Never merges anything
  itself.
intent: >
  Demonstrate bounded, auditable AI remediation of a classified CI failure
  without ever bypassing human review or deterministic validation.
emoji: "🩹"
labels: ["self-heal", "demo"]

on:
  workflow_dispatch:
    inputs:
      scenario:
        description: "Which demo fixture to apply and attempt to remediate"
        required: true
        type: choice
        options:
          - easy-unit-test
          - medium-low-coverage
          - advanced-performance

permissions:
  contents: read
  issues: read
  pull-requests: read

concurrency:
  group: self-heal-remediation-${{ github.run_id }}

engine: copilot

network: defaults

timeout-minutes: 15

max-ai-credits: 300

# Deterministic pipeline: runs after checkout, before the AI engine starts.
# No AI reasoning happens in any of these steps -- every one is the same
# script a human could run locally via `make`.
steps:
  - name: Install build dependencies
    run: |
      sudo apt-get update
      sudo apt-get install -y cmake g++ gcovr lcov

  - name: Apply demo fixture
    id: fixture
    run: |
      set -euo pipefail
      SCENARIO="${{ github.event.inputs.scenario }}"
      echo "scenario=$SCENARIO" >> "$GITHUB_OUTPUT"
      python3 scripts/create_demo_failure.py "$SCENARIO"

  - name: Build (with coverage instrumentation)
    run: |
      set -euo pipefail
      cmake -S . -B build -DENABLE_COVERAGE=ON -DCMAKE_BUILD_TYPE=Debug
      cmake --build build -j 4

  - name: Collect evidence
    run: |
      set -euo pipefail
      python3 scripts/collect_evidence.py \
        --scenario "${{ steps.fixture.outputs.scenario }}" \
        --build-dir build --require-failure

  - name: Classify failure
    run: |
      set -euo pipefail
      python3 scripts/classify_failure.py \
        --evidence .evidence/evidence.json \
        --output .evidence/classification.json

  - name: Pre-check policy and skip the agent if denied
    id: policy
    run: |
      set -euo pipefail
      if python3 scripts/evaluate_policy.py \
          --evidence .evidence/evidence.json \
          --classification .evidence/classification.json \
          --output .evidence/policy-decision.json; then
        echo "decision=allow" >> "$GITHUB_OUTPUT"
      else
        echo "decision=deny" >> "$GITHUB_OUTPUT"
        {
          echo "### Self-heal remediation skipped"
          echo ""
          echo "The deterministic policy engine denied this run before any AI"
          echo "model was invoked (no AI Credits were spent). Decision:"
          echo ""
          echo '```json'
          cat .evidence/policy-decision.json
          echo '```'
        } >> "$GITHUB_STEP_SUMMARY"
        echo '{"type":"noop","message":"Policy denied remediation before any AI invocation; see job summary for the decision and reasons."}' >> "$GH_AW_SAFE_OUTPUTS"
      fi

  - name: Show evidence, classification, and policy decision
    run: |
      echo "## .evidence/evidence.json"; cat .evidence/evidence.json
      echo "## .evidence/classification.json"; cat .evidence/classification.json
      echo "## .evidence/policy-decision.json"; cat .evidence/policy-decision.json

tools:
  bash:
    - "cmake:*"
    - "ctest:*"
    - "python3:*"
    - "g++:*"
    - "make:*"
    - "git:*"
    - "./build/*"
    - "cat:*"
    - "echo:*"
    - "diff:*"
  edit:

safe-outputs:
  create-pull-request:
    draft: true
    labels: ["self-heal", "demo"]
    max: 1
  create-issue:
    title-prefix: "[self-heal] "
    labels: ["self-heal", "needs-human-review"]
    max: 1
---

# Self-Heal Remediation Agent

A deterministic pipeline has already applied the `${{ github.event.inputs.scenario }}`
demo fixture, built the project, collected evidence, classified the failure,
and evaluated policy for this run. The results are on disk at:

- `.evidence/evidence.json`
- `.evidence/classification.json`
- `.evidence/policy-decision.json`

**Read `AGENTS.md` in the repository root first.** It is the authoritative,
complete instruction set for this task: what you may and may not touch, the
exact validation command you must run before proposing any change, and what
to do if you cannot produce a validated fix. Follow it exactly.

In short: read the evidence and classification, make the smallest correct
fix within the permitted paths for this scenario, validate it with
`scripts/validate_change.py` using the profile named in the policy decision,
and only open a pull request once that validation passes. If you cannot
produce a validated fix within your one-attempt budget, open an issue
explaining what you observed instead of a pull request. Never touch a
globally forbidden path, never weaken a test or threshold, and never attempt
to merge anything yourself -- a human always reviews and merges.
