---
description: >
  Single bounded remediation agent for the self-healing CI/CD demo. Triggered
  automatically when the deterministic `CI` workflow fails on a real
  developer pull request, it downloads and verifies the evidence that CI
  job produced, deterministically classifies the failure and evaluates
  policy, posts a concise diagnosis and plan on the original pull request,
  then makes one bounded attempt at the smallest correct fix, validates it
  with the same deterministic tools used to judge it, and opens a draft
  **stacked** pull request targeting the developer's own branch (not
  `main`) for human review. Never merges anything itself.
intent: >
  Demonstrate bounded, auditable AI remediation of a real CI failure on a
  real pull request without ever bypassing human review or deterministic
  validation, and without creating a self-triggering loop.
emoji: "🩹"
labels: ["self-heal", "demo"]

# Triggered by the deterministic CI workflow's own completion, not by a
# human/workflow_dispatch choice of scenario -- this is the PR-driven
# redesign of this demo: CI fails on a real change, this workflow reacts.
# `branches:` is intentionally omitted: CI runs (and can fail) on any
# developer branch via its `pull_request:` trigger, and this workflow must
# be able to react to a failure on any of them, including a previous
# remediation's own stacked fix PR branch (which the loop guards below
# then refuse to act on). gh-aw's compiler injects repository-ID and
# fork checks automatically for `workflow_run:` triggers -- see
# docs/architecture.md for the full guard sequence this workflow adds on
# top of that.
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    conclusion: [failure]

permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read

concurrency:
  group: self-heal-remediation-${{ github.event.workflow_run.pull_requests[0].number }}-${{ github.event.workflow_run.head_sha }}
  cancel-in-progress: false

engine: copilot

network: defaults

timeout-minutes: 10

max-ai-credits: 300

# Deterministic pipeline: runs after checkout, before the AI engine starts.
# No AI reasoning happens in any of these steps -- every one is the same
# script a human could run locally via `make`.
steps:
  - name: Checkout trusted guard/policy scripts from the default branch
    # Deliberately no `ref:` override. `workflow_run` always runs this
    # workflow's own job steps using the repository's default branch
    # content (a GitHub Actions platform guarantee specifically to
    # prevent a malicious fork/PR from rewriting the workflow or its
    # guard logic to grant itself elevated permissions), so a plain
    # checkout here gives us a trusted copy of
    # check_remediation_guards.py/evaluate_policy.py and the policy
    # file *before* guards decide whether the potentially-untrusted
    # failing commit should be checked out at all. The failing commit
    # itself is only checked out later, once guards have passed.
    uses: actions/checkout@v7
    with:
      fetch-depth: 1
      persist-credentials: false

  - name: Evaluate loop-prevention guards (fork / stale head / branch / duplicate)
    id: guards
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      PR_NUMBER="${{ github.event.workflow_run.pull_requests[0].number }}"
      if [ -z "$PR_NUMBER" ]; then
        echo "decision=deny" >> "$GITHUB_OUTPUT"
        echo "reasons=no same-repository pull request is associated with this workflow run" >> "$GITHUB_OUTPUT"
      else
        PR_JSON="$(gh pr view "$PR_NUMBER" --repo "${{ github.repository }}" --json headRefOid,headRefName,baseRefName)"
        CURRENT_HEAD_SHA="$(echo "$PR_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['headRefOid'])")"
        HEAD_BRANCH="$(echo "$PR_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['headRefName'])")"
        BASE_BRANCH="$(echo "$PR_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['baseRefName'])")"
        SHORT_SHA="$(echo "${{ github.event.workflow_run.head_sha }}" | cut -c1-12)"
        BRANCH_PREFIX="self-heal/$SHORT_SHA"
        EXISTING="$(gh pr list --repo "${{ github.repository }}" --state open --json headRefName \
          -q "[.[] | select(.headRefName | startswith(\"$BRANCH_PREFIX\"))] | length")"
        python3 - "$PR_NUMBER" "$CURRENT_HEAD_SHA" "$EXISTING" "$HEAD_BRANCH" "$BASE_BRANCH" <<'PYEOF'
      import json, sys
      sys.path.insert(0, "scripts")
      import check_remediation_guards as g
      import evaluate_policy

      pr_number, current_head_sha, existing, head_branch_live, base_branch_live = sys.argv[1:6]
      context = {
          "workflow_run": {
              "event": "${{ github.event.workflow_run.event }}",
              "conclusion": "${{ github.event.workflow_run.conclusion }}",
              "head_sha": "${{ github.event.workflow_run.head_sha }}",
              "head_branch": "${{ github.event.workflow_run.head_branch }}",
              "repository_full_name": "${{ github.event.workflow_run.repository.full_name }}",
              "head_repository_full_name": "${{ github.event.workflow_run.head_repository.full_name }}",
              "pull_requests": [{"number": int(pr_number), "base_ref": base_branch_live}] if pr_number else [],
          },
          "current_pr_head_sha": current_head_sha,
          "existing_remediation_branch_exists": existing.strip() not in ("0", ""),
      }
      policy = evaluate_policy.load_policy()
      decision = g.evaluate_guards(policy, context)
      # Prefer the live-looked-up head branch name (exact casing/value from the
      # PR itself) over the workflow_run payload's copy for downstream outputs.
      decision["head_branch"] = decision["head_branch"] or head_branch_live
      with open(".evidence-guard-decision.json", "w") as fh:
          json.dump(decision, fh, indent=2)
      print(json.dumps(decision, indent=2))
      PYEOF
        DECISION_JSON=".evidence-guard-decision.json"
        DECISION="$(python3 -c "import json; print(json.load(open('$DECISION_JSON'))['decision'])")"
        REASONS="$(python3 -c "import json; print('; '.join(json.load(open('$DECISION_JSON'))['reasons']))")"
        echo "decision=$DECISION" >> "$GITHUB_OUTPUT"
        echo "reasons=$REASONS" >> "$GITHUB_OUTPUT"
        echo "pr_number=$PR_NUMBER" >> "$GITHUB_OUTPUT"
        echo "head_branch=$HEAD_BRANCH" >> "$GITHUB_OUTPUT"
        echo "base_branch=$BASE_BRANCH" >> "$GITHUB_OUTPUT"
        echo "short_sha=$SHORT_SHA" >> "$GITHUB_OUTPUT"
      fi

  - name: Stop here if guards denied (no AI invocation, no evidence download)
    if: steps.guards.outputs.decision == 'deny'
    env:
      # gh-aw only auto-wires this env var into its own generated
      # steps; a user-defined deterministic step writing directly to
      # $GH_AW_SAFE_OUTPUTS must declare it itself or the shell's
      # `set -u` (implied by gh-aw's strict mode) fails with
      # "unbound variable".
      GH_AW_SAFE_OUTPUTS: ${{ steps.set-runtime-paths.outputs.GH_AW_SAFE_OUTPUTS }}
    run: |
      {
        echo "### Self-heal remediation skipped before evidence download"
        echo ""
        echo "Loop-prevention guards denied this run: ${{ steps.guards.outputs.reasons }}"
      } >> "$GITHUB_STEP_SUMMARY"
      echo '{"type":"noop","message":"Loop-prevention guards denied this run before evidence was downloaded or any AI model was invoked: ${{ steps.guards.outputs.reasons }}"}' >> "$GH_AW_SAFE_OUTPUTS"

  - name: Checkout the exact failing commit
    if: steps.guards.outputs.decision == 'allow'
    uses: actions/checkout@v7
    with:
      ref: ${{ github.event.workflow_run.head_sha }}
      fetch-depth: 0
      persist-credentials: false

  - name: Install build dependencies
    if: steps.guards.outputs.decision == 'allow'
    run: |
      sudo apt-get update
      sudo apt-get install -y cmake g++ gcovr lcov

  - name: Download the CI run's evidence artifact
    id: evidence
    if: steps.guards.outputs.decision == 'allow'
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      rm -rf .evidence
      gh run download ${{ github.event.workflow_run.id }} \
        --repo "${{ github.repository }}" --name self-heal-evidence --dir .evidence
      test -f .evidence/evidence.json

  - name: Write remediation context file for the agent prompt
    # Deliberately runs *after* evidence download, which does
    # `rm -rf .evidence` before unpacking the downloaded artifact --
    # writing this file any earlier would have it silently wiped out.
    if: steps.guards.outputs.decision == 'allow'
    run: |
      cat > .evidence/remediation-context.md <<EOF
      - Original pull request: #${{ steps.guards.outputs.pr_number }}
      - Head branch (developer's branch, the pull request base for your fix): ${{ steps.guards.outputs.head_branch }}
      - Base branch of the original pull request: ${{ steps.guards.outputs.base_branch }}
      - Failing commit short SHA: ${{ steps.guards.outputs.short_sha }}
      - Suggested remediation branch name: self-heal/${{ steps.guards.outputs.short_sha }}-<category>
      EOF
      cat .evidence/remediation-context.md

  - name: Verify evidence provenance against the live PR (anti-tamper)
    id: verify
    if: steps.guards.outputs.decision == 'allow'
    run: |
      set -euo pipefail
      python3 - <<'PYEOF'
      import json, sys
      sys.path.insert(0, "framework/schemas")
      import evidence_lib

      evidence = json.loads(open(".evidence/evidence.json").read())
      errors = evidence_lib.validate_evidence(evidence)

      expected = {
          "repository": "${{ github.repository }}",
          "pr_number": int("${{ steps.guards.outputs.pr_number }}"),
          "head_sha": "${{ github.event.workflow_run.head_sha }}",
          "workflow_run_id": "${{ github.event.workflow_run.id }}",
      }
      for field, want in expected.items():
          got = evidence.get(field)
          if got != want:
              errors.append(f"evidence.{field} = {got!r} does not match live context {want!r}")

      decision = "allow" if not errors else "deny"
      with open(".evidence-verify-decision.json", "w") as fh:
          json.dump({"decision": decision, "reasons": errors}, fh, indent=2)
      print(json.dumps({"decision": decision, "reasons": errors}, indent=2))
      PYEOF
      DECISION="$(python3 -c "import json; print(json.load(open('.evidence-verify-decision.json'))['decision'])")"
      REASONS="$(python3 -c "import json; print('; '.join(json.load(open('.evidence-verify-decision.json'))['reasons']))")"
      echo "decision=$DECISION" >> "$GITHUB_OUTPUT"
      echo "reasons=$REASONS" >> "$GITHUB_OUTPUT"

  - name: Stop here if evidence verification failed
    if: steps.guards.outputs.decision == 'allow' && steps.verify.outputs.decision == 'deny'
    env:
      GH_AW_SAFE_OUTPUTS: ${{ steps.set-runtime-paths.outputs.GH_AW_SAFE_OUTPUTS }}
    run: |
      {
        echo "### Self-heal remediation skipped: evidence verification failed"
        echo ""
        echo "${{ steps.verify.outputs.reasons }}"
      } >> "$GITHUB_STEP_SUMMARY"
      echo '{"type":"noop","message":"Evidence failed schema/signature/provenance verification: ${{ steps.verify.outputs.reasons }}"}' >> "$GH_AW_SAFE_OUTPUTS"

  - name: Classify failure
    if: steps.guards.outputs.decision == 'allow' && steps.verify.outputs.decision == 'allow'
    run: |
      set -euo pipefail
      python3 scripts/classify_failure.py \
        --evidence .evidence/evidence.json \
        --output .evidence/classification.json

  - name: Pre-check policy and skip the agent if denied
    id: policy
    if: steps.guards.outputs.decision == 'allow' && steps.verify.outputs.decision == 'allow'
    env:
      GH_AW_SAFE_OUTPUTS: ${{ steps.set-runtime-paths.outputs.GH_AW_SAFE_OUTPUTS }}
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

  - name: Post diagnosis and plan to the original pull request
    if: steps.guards.outputs.decision == 'allow' && steps.verify.outputs.decision == 'allow' && steps.policy.outputs.decision == 'allow'
    env:
      GH_AW_SAFE_OUTPUTS: ${{ steps.set-runtime-paths.outputs.GH_AW_SAFE_OUTPUTS }}
    run: |
      set -euo pipefail
      python3 - <<'PYEOF' > .evidence/diagnosis-comment.md
      import json

      evidence = json.loads(open(".evidence/evidence.json").read())
      classification = json.loads(open(".evidence/classification.json").read())
      decision = json.loads(open(".evidence/policy-decision.json").read())
      m = evidence["measurements"]
      category = evidence["failure_category"]

      lines = [
          f"## 🩹 Self-heal remediation starting",
          "",
          f"CI failed on this pull request's head commit `{evidence['head_sha'][:12]}` "
          f"with failure category **{category}**.",
          "",
          "**Evidence summary:**",
      ]
      if category == "unit-test-failure":
          lines.append(f"- Failing tests: `{', '.join(m.get('failing_tests') or [])}`")
      elif category == "coverage-gap":
          lines.append(f"- Coverage: {m.get('coverage_percent')}% (threshold {m.get('threshold_percent')}%)")
          clc = m.get("changed_line_coverage") or {}
          if clc.get("violations"):
              lines.append(f"- Uncovered changed lines: `{clc['violations']}`")
      elif category == "performance-regression":
          lines.append(f"- Benchmark median: {m.get('median_ms')}ms (threshold {m.get('threshold_ms')}ms)")

      lines += [
          "",
          f"**Plan:** a single bounded AI remediation attempt will try the smallest "
          f"correct fix within `{decision['permitted_paths']}`, validated with the "
          f"`{decision['required_validation_profile']}` profile "
          f"(budget: {decision['runtime_budget_minutes']} minutes, 1 attempt).",
          "",
          "If a validated fix is produced, a **draft pull request targeting this "
          f"branch (`{evidence['head_branch']}`)** will be opened for review. If not, "
          "an issue will be opened describing what was observed instead.",
      ]
      open(".evidence/diagnosis-comment.md", "w").write("\n".join(lines))
      PYEOF
      BODY="$(cat .evidence/diagnosis-comment.md)"
      python3 -c "
      import json
      body = open('.evidence/diagnosis-comment.md').read()
      print(json.dumps({'type': 'add_comment', 'item_number': ${{ steps.guards.outputs.pr_number }}, 'body': body}))
      " >> "$GH_AW_SAFE_OUTPUTS"

  - name: Show evidence, classification, and policy decision
    if: steps.guards.outputs.decision == 'allow' && steps.verify.outputs.decision == 'allow'
    run: |
      echo "## .evidence/evidence.json"; cat .evidence/evidence.json
      echo "## .evidence/classification.json"; cat .evidence/classification.json || true
      echo "## .evidence/policy-decision.json"; cat .evidence/policy-decision.json || true

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
  add-comment:
    target: "*"
    max: 2
  create-pull-request:
    draft: true
    labels: ["self-heal", "demo"]
    max: 1
    base-branch: "${{ github.event.workflow_run.pull_requests[0].head.ref }}"
    preserve-branch-name: true
  create-issue:
    title-prefix: "[self-heal] "
    labels: ["self-heal", "needs-human-review"]
    max: 1
---

# Self-Heal Remediation Agent

A deterministic pipeline has already resolved the original pull request,
checked out its exact failing commit, applied loop-prevention guards,
downloaded and verified that commit's CI evidence, classified the failure,
evaluated policy, and -- if allowed -- already posted a concise diagnosis
and plan comment on that pull request. The results are on disk at:

- `.evidence/remediation-context.md` -- original PR number, head/base
  branch names, failing commit short SHA, and the suggested remediation
  branch name. **Read this file first and use its exact values** (do not
  guess or reconstruct them from anywhere else).
- `.evidence/evidence.json`
- `.evidence/classification.json`
- `.evidence/policy-decision.json`

**Read `AGENTS.md` in the repository root next.** It is the authoritative,
complete instruction set for this task: what you may and may not touch, the
exact validation command you must run before proposing any change, the
branch-naming convention for your pull request, and what to do if you
cannot produce a validated fix. Follow it exactly.

In short: read the evidence and classification, make the smallest correct
fix within the permitted paths for this failure category, validate it with
`scripts/validate_change.py` using the profile named in the policy decision,
and only open a pull request once that validation passes. Your pull request
must be a **stacked** pull request targeting the head branch named in
`.evidence/remediation-context.md` (the developer's own branch), use the
suggested remediation branch name from that same file (replacing
`<category>` with the classified failure category), and must never target
`main` directly. If you cannot produce a validated fix within your
one-attempt budget, open an issue referencing the original pull request
number from `.evidence/remediation-context.md`, explaining what you observed
instead of a pull request. Never touch a globally forbidden path, never
weaken a test or threshold, and never attempt to merge anything yourself --
a human always reviews and merges. Merging your pull request into the
developer's branch is what turns the original pull request green again.
