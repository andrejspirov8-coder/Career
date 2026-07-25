# Required checks for `main`

Configure the private GitHub repository's branch protection or ruleset so pull requests cannot merge until these checks pass:

- `Python / lock, lint, tests, PDFs, audit`
- `Dashboard / unit, build, browser, audit`
- `Raycast / typecheck, lint, tests, build, audit`
- `Repository smoke test`
- `CodeQL / Analyze (python)`
- `CodeQL / Analyze (javascript-typescript)`

Also require pull requests, require the branch to be up to date before merging, and block force pushes and branch deletion.

This file documents the intended rule. Enabling the GitHub ruleset is an external repository-setting change and must be done only after the consolidated private repository is pushed and separately approved.

GitHub must also support rulesets and private-repository code scanning for the account that owns this repository. If GitHub asks for an account upgrade, keep the repository private and upgrade or transfer it to a plan that supports these controls; do not make it public as a workaround.


## Current mandatory commands

The CI workflow (`.github/workflows/ci.yml`) defines these job names — use them in
branch-protection rulesets:

- `python-lint`
- `python-test`
- `dashboard-build`

> **NOTE:** There is no Raycast CI job. The Raycast extension
> (`raycast-job-search-hub/`) is not wired into the CI workflow. If Raycast checks
> should block merging, add a job to `.github/workflows/ci.yml` and include its
> name here. Until then, run `make raycast-check` locally.
