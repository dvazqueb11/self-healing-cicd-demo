# Demo Guide

This walks through exercising each failure category end to end, both
locally (fast feedback loop, no AI, no GitHub required) and via the real,
PR-driven GitHub Agentic Workflow.

The live demo is **always** driven by a real pull request. Fixtures
(`fixtures/<scenario>/`) are an optional convenience for repeatably
producing a real commit that CI will genuinely fail on — the remediation
workflow itself never applies a fixture and never knows fixtures exist; it
only ever reacts to a real CI failure on a real pull request, regardless of
how that failure was introduced.

## Prerequisites

- `cmake`, a C++17 compiler (g++ or clang++), `gcovr` or `lcov`, Python 3.9+.
- To run the agentic workflow: a GitHub repository with Actions enabled and
  Copilot coding agent / Copilot Premium Requests enabled for the engine
  (`engine: copilot`), since `self-heal-remediation.md` invokes the Copilot
  engine. See the top-level `README.md` "Repository setup" section for the
  exact settings.
- A repository Actions secret named `COPILOT_GITHUB_TOKEN` containing a
  user-owned
  [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new?name=COPILOT_GITHUB_TOKEN&description=GitHub+Agentic+Workflows+-+Copilot+engine+authentication&user_copilot_requests=read)
  with **Account permissions → Copilot Requests → Read**. Set and verify it
  before the first run:

  ```sh
  gh secret set COPILOT_GITHUB_TOKEN
  gh secret list --app actions
  ```

  The command securely prompts for the `github_pat_...` value. OAuth
  (`gho_...`) and classic (`ghp_...`) tokens are not accepted, and the secret
  name is case-sensitive.
- [`gh`](https://cli.github.com/) with the
  [`gh-aw`](https://github.com/githubnext/gh-aw) extension installed, only
  if you intend to edit and recompile the workflow
  (`gh extension install githubnext/gh-aw`).

## Running a failure category locally (no AI, no GitHub involved)

This is the fastest way to see the deterministic half of the pipeline work,
using the exact same scripts the real CI and remediation workflows run.

```sh
# 1. Confirm the baseline is healthy
make test        # 11/11 pass
make coverage     # 100% line coverage
make benchmark    # well under the 200ms threshold

# 2. Apply a fixture to the local working tree (pick one)
make apply-easy        # or apply-medium / apply-advanced

# 3. Observe the expected, classified failure
make test          # easy-unit-test: one test now fails
make coverage       # medium-low-coverage: coverage drops below 95%
make benchmark      # advanced-performance: benchmark now exceeds 200ms

# 4. Run the same evidence/classify/policy pipeline a real CI + remediation
#    run would produce, using the current commit as a stand-in head/base
HEAD_SHA=$(git rev-parse HEAD)
python3 scripts/collect_evidence.py \
    --repository you/self-healing-cicd-demo --pr-number 1 \
    --base-branch main --base-sha "$HEAD_SHA" \
    --head-branch demo --head-sha "$HEAD_SHA" --workflow-run-id 1 \
    --build-dir build
python3 scripts/classify_failure.py --evidence .evidence/evidence.json
python3 scripts/evaluate_policy.py --evidence .evidence/evidence.json \
    --classification .evidence/classification.json

# 5. Make a fix by hand, inside permitted_paths, commit it, then validate
#    (validate_change.py diffs your commit against evidence.json's head_sha,
#    so the fix must actually be committed, not just edited on disk)
git add -A && git commit -m "fix: ..."
python3 scripts/validate_change.py --profile unit-test-remediation --build-dir build

# 6. Reset back to a clean baseline
git reset --soft HEAD~1   # undo the local test commit from step 5
make reset SCENARIO=easy-unit-test
```

Swap `easy-unit-test` for `medium-low-coverage` (profile
`coverage-remediation`) or `advanced-performance` (profile
`performance-remediation`) to walk through the other two categories. Each
fixture's `metadata.json` documents exactly what it changes and which
deterministic check it is expected to trip.

## Running the real, PR-driven agentic demo

1. Push this repository to GitHub (public, per project requirements) with
   Actions enabled, and complete the prerequisites above.
2. Open a real pull request that CI will fail. The easiest repeatable way is
   the demo helper, which creates a normal branch, commit, and pull request
   from a fixture via the `gh` CLI:

   ```sh
   make demo-pr-easy        # or demo-pr-medium / demo-pr-advanced
   ```

   This is equivalent to writing a real bug by hand and opening a PR for it
   — the remediation workflow cannot tell the difference, and does not try
   to.
3. Watch `ci.yml` run on the pull request. It configures and builds once,
   runs all three deterministic checks, and — because this PR is expected
   to fail — always collects and normalizes evidence and uploads it as a
   workflow artifact before failing the job.
4. `self-heal-remediation` triggers automatically via `workflow_run` once
   `ci.yml` completes with conclusion `failure`. Watch its job log, which
   shows, in order:
   - loop-prevention guard evaluation (fork / stale head / branch / duplicate)
   - evidence download and re-verification (schema, signature, live
     provenance cross-checks against the GitHub API)
   - classification (`.evidence/classification.json` printed to the log)
   - policy decision printed to the log
   - if any guard or the policy denies: a `noop` safe-output and the run
     ends — no evidence download (guard denial) or no AI engine invocation
     (policy denial), so no AI Credits are spent
   - if everything allows: a concise diagnosis and plan comment is posted
     to the **original pull request**, then the Copilot engine starts,
     reads `AGENTS.md`, the evidence/classification/policy JSON, and the
     category's permitted paths, and attempts the smallest correct fix
5. If the agent produces a change that passes `validate_change.py`, it opens
   a **draft pull request stacked on top of your demo branch** (never
   `main`), labeled `self-heal` and `demo`, with a title of the form
   `[self-heal:<category>] ...` and a body summarizing the failure, the
   fix, and the evidence used.
6. Review the fix PR like any other. `ci.yml` runs automatically on it too
   (it targets your demo branch, and `ci.yml`'s `pull_request:` trigger has
   no branch filter) — this is the real, final gate (see
   `docs/architecture.md`). Merge it once you're satisfied, exactly like a
   human-authored PR. Merging it updates your original demo branch, which
   reruns `ci.yml` on your **original** pull request and turns it green.
7. If the agent cannot produce a validated fix, it opens an **issue**
   instead (labeled `self-heal`, `needs-human-review`) referencing your
   original pull request and describing what it tried and why it
   stopped — no PR is opened in that case.
8. Clean up by closing the demo pull request and deleting its branch, or
   leave it as a reference — demo PRs don't need any special reset step
   since nothing was ever applied to `main` directly.

## What "repeatable" means here

Every fixture is a plain git patch applied as a normal commit on a normal
branch, every deterministic check is scripted and produces the same
evidence given the same inputs, and the policy engine's decision is pure
data (no network calls, no non-determinism). Running the same fixture twice
in a row (as two separate demo pull requests) produces the same
classification and the same policy decision every time; the only
non-deterministic part of the whole loop is the AI engine's actual code
suggestion, which is exactly the part this architecture is designed to
bound and re-validate rather than trust blindly.
