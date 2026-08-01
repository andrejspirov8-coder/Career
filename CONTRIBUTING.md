# Contributing

This is a private job-search workspace, but contributions, suggestions, and
improvements are welcome. Development uses Python 3.11, Node.js 22, and `uv`
for dependency management.

## Before starting

1. Open an issue or discussion for significant changes before writing code.
2. Run `make doctor` from `job-search/` to check the current workspace state.
3. Read `docs/ARCHITECTURE.md` and `docs/OPERATIONS_RUNBOOK.md` for context.

## Development setup

```bash
cd job-search
make bootstrap     # install all dependencies
make preflight     # verify the workspace
```

## Code conventions

- Python: Ruff linting (`make lint`) and formatting (`make format`).
  - Line length: 88 characters.
  - Target: Python 3.11.
  - Every public function and method should have a type annotation.
- TypeScript: ESLint + strict TypeScript type checking.
  - Run `npm run lint && npm run typecheck` from `dashboard/`.
- Shell scripts: `set -euo pipefail`, LF line endings.
- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`,
  `test:`, `ci:`, `style:`.

## Before submitting

```bash
cd job-search
make lint          # ruff check
make test          # pytest
make smoke         # full smoke test
make verify-patch  # focused pre-submit checks
```

If you modified the dashboard, also run:

```bash
cd dashboard
npm run lint
npm run typecheck
npm test
npm run build
```

## Architecture rules

- Python owns domain rules, persistence, analytics, and fixed automation.
- TypeScript owns the dashboard and Raycast interfaces.
- Shell / Make orchestrates deterministic commands only.
- Domain code must not import dashboard or CLI modules.
- Dependency direction: `domain -> services -> integrations -> adapters`.

## Security

- Never commit `.env`, `.env.*`, browser profiles, tokens, or personal data.
- Live LinkedIn dispatch requires multiple gates — see `SECURITY.md`.
- Run `make audit-runtime` to check Python dependencies for vulnerabilities.
