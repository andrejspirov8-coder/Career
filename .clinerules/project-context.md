# Career Workspace Context

## Tech Stack
- Python 3.12+ with `uv` package manager
- TypeScript via Next.js for dashboard
- Ruff for linting + formatting
- pre-commit for local checks
- pytest with coverage for testing

## Key Conventions
- Run `make` before committing (runs lint + test)
- Use `uv` not `pip` for Python dependency management
- Python source in `job-search/src/career_job_search/`
- Tests in `job-search/tests/` using pytest
- Dashboard is in `job-search/dashboard/` (Next.js)
- CVs are markdown in `job-search/cv/`, built via `build_cv_pdf.py`
- Never commit to `job-search/inbox/` without review

## Critical Paths
- Pipeline: `job-search/pipeline/`
- Agent prompts: `job-search/linkedin/agent_prompts.yaml`
- CV variant config: `job-search/cv/variant_profiles.yaml`
- Recruiter config: `job-search/config/`
- MCP server: `job-search/mcp/`
- Architecture docs: `docs/context/`
