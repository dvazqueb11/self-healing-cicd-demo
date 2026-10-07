# Contributing

This repository exists to demonstrate a simple, reliable, repeatable pattern
for combining deterministic CI/CD with bounded AI remediation. Contributions
that keep that goal intact are welcome.

## Local setup

```sh
git clone <this repo>
cd self-healing-cicd-demo
make build
make test
make coverage
make benchmark
make automation-test
```

See `README.md` for a full walkthrough and `docs/demo-guide.md` for how to
run the three demo scenarios end to end.

## Making changes

1. Open an issue or pull request describing the change.
2. Run `make test`, `make coverage`, `make benchmark`, and
   `make automation-test` locally before pushing — these are the same
   checks `.github/workflows/ci.yml` runs.
3. If you change anything under `.github/workflows/self-heal-remediation.md`,
   run `gh aw compile` and commit the regenerated `.lock.yml` in the same
   commit.
4. If you touch `.github/policies/self-heal-policy.yml`, update
   `docs/evidence-contract.md` and the relevant fixture's
   `fixtures/<scenario>/metadata.json` if the change affects what that
   scenario is allowed to do.
5. Run `make public-check` before pushing if you've added any new files —
   it scans for secrets, non-placeholder emails, and internal references.

## Adding a fourth scenario

See `docs/extension-guide.md` for a step-by-step guide to adding a new
fixture/scenario pair without touching the shared framework code.

## Code of conduct

Participation in this project is governed by `CODE_OF_CONDUCT.md`.
