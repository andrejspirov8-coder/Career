PY ?= uv run python
DASHBOARD_PORT ?= $(if $(CAREER_DASHBOARD_PORT),$(CAREER_DASHBOARD_PORT),3001)

.PHONY: bootstrap lock test test-coverage coverage-ratchet coverage-baseline-update lint format typecheck preflight doctor scout plan approve-session check-approvals dispatch-dry daily-dry daily-queue weekly-review rebuild-cvs smoke verify-patch verify-release dashboard-dev dashboard-build dashboard-start dashboard-open dashboard-worker dashboard-status dashboard-backup dashboard-restore dashboard-test dashboard-e2e generate-types contracts-drift audit-runtime remember save precommit-setup handoff

bootstrap:
	./scripts/bootstrap.sh

lock:
	uv lock

test:
	uv run --group dev python -m pytest

test-coverage:
	uv run --group dev python -m pytest --cov --cov-report=term-missing

coverage-ratchet:
	uv run --group dev python scripts/coverage_ratchet.py

coverage-baseline-update:
	uv run --group dev python scripts/coverage_ratchet.py --update

lint:
	uv run ruff check src mcp tools cv tests

format:
	uv run ruff format src mcp tools cv tests
	uv run ruff check --fix src mcp tools cv tests

typecheck:
	uv run pyright

preflight:
	$(PY) -m career_job_search.recruiters.orchestrator preflight

doctor:
	uv lock --check
	uv run ruff check src mcp tools cv tests
	uv run --group dev python -m pytest
	$(PY) -m career_job_search.recruiters.orchestrator preflight --browse-status

scout:
	$(PY) -m career_job_search.recruiters.orchestrator scout --headed

plan:
	$(PY) -m career_job_search.recruiters.orchestrator plan --tier tier_1

approve-session:
	$(PY) -m career_job_search.recruiters.approval approve-session --session pipeline/recruiter_session_state.json

check-approvals:
	$(PY) -m career_job_search.recruiters.approval check-session --session pipeline/recruiter_session_state.json

dispatch-dry:
	$(PY) -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --dry-run

daily-dry:
	$(PY) -m career_job_search.recruiters.orchestrator daily --headed --dry-run

daily-queue:
	$(PY) -m career_job_search.automation.control enqueue --kind daily_search --trigger make --spawn-worker
	@echo "The private worker started. If the dashboard is not already open, run: make dashboard-dev"

weekly-review:
	$(PY) -m career_job_search.opportunities.dashboard_adapter weekly-roi
	$(PY) -m career_job_search.cvs.performance
	$(PY) -m career_job_search.cvs.performance --by source
	$(PY) -m career_job_search.cvs.performance --roi
	$(PY) -m career_job_search.recruiters.hiring_network report
	$(PY) -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml report --summary

rebuild-cvs:
	$(PY) cv/build_cv_pdf.py --all

smoke:
	./scripts/smoke_repo.sh

audit-runtime:
	uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file /tmp/job-search-runtime-requirements.txt > /dev/null
	uvx pip-audit -r /tmp/job-search-runtime-requirements.txt

dashboard-dev:
	$(PY) -m career_job_search.workspace.dashboard_service --mode dev --port "$(DASHBOARD_PORT)"

dashboard-build:
	cd dashboard && npm run build

dashboard-start: dashboard-build
	$(PY) -m career_job_search.workspace.dashboard_service --mode production --port "$(DASHBOARD_PORT)"

dashboard-open:
	open "http://127.0.0.1:$(DASHBOARD_PORT)"

dashboard-worker:
	$(PY) -m career_job_search.workspace.dashboard_service --mode worker

dashboard-status:
	$(PY) -m career_job_search.workspace.control status

dashboard-backup:
	$(PY) -m career_job_search.workspace.control backup-create-interactive

dashboard-restore:
	@test -n "$(BACKUP)" || (echo "Use: make dashboard-restore BACKUP=career-backup-YYYYMMDDTHHMMSSZ-abcdef.career-backup" && exit 2)
	$(PY) -m career_job_search.workspace.control backup-restore-interactive --filename "$(BACKUP)"

dashboard-test:
	cd dashboard && npm test && npm run typecheck

generate-types:
	uv run python scripts/generate-contracts.py
	cd dashboard && npm run typecheck

contracts-drift:
	uv run python scripts/generate-contracts.py
	git diff --exit-code -- dashboard/lib/generated

dashboard-e2e:
	cd dashboard && CAREER_DASHBOARD_TOKEN=local-e2e-token npm run e2e

precommit-setup:
	cd "$(shell git rev-parse --show-toplevel)" && pre-commit install

remember:
	@test -n "$(TOPIC)" || (echo "Use: make remember TOPIC=<topic> MSG=<message>" && exit 2)
	./scripts/remember.sh "$(TOPIC)" "$(MSG)"

save:
	@test -n "$(TOPIC)" || (echo "Use: echo 'did X' | make save TOPIC=<topic>" && exit 2)
	./scripts/remember.sh "$(TOPIC)"

handoff:
	@test -n "$(GOAL)" || (echo "Use: make handoff GOAL=... DONE='item1|item2' NEXT='step1|step2' BLOCKERS='b1|b2'" && exit 2)
	./scripts/handoff.sh

verify-release:
	./scripts/verify_release.sh

verify-patch:
	$(MAKE) test
	$(PY) -m career_job_search.recruiters.orchestrator preflight --browse-status
