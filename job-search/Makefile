PY ?= uv run python
DASHBOARD_PORT ?= $(if $(CAREER_DASHBOARD_PORT),$(CAREER_DASHBOARD_PORT),3001)

.PHONY: bootstrap lock test lint format preflight doctor scout plan approve-session check-approvals dispatch-dry daily-dry daily-queue weekly-review rebuild-cvs smoke verify-patch verify-release dashboard-dev dashboard-build dashboard-start dashboard-open dashboard-worker dashboard-status dashboard-backup dashboard-restore dashboard-test dashboard-e2e audit-runtime dev-agent-doctor dev-agent-benchmark dev-agent-model-benchmark dev-agent-plan dev-agent-proposals dev-agent-proposal-approve dev-agent-proposal-reject dev-agent-autonomy dev-agent-service dev-agent-status dev-agent-run dev-agent-show dev-agent-verify dev-agent-approve dev-agent-apply dev-agent-cleanup remember save precommit-setup handoff

bootstrap:
	./scripts/bootstrap.sh

lock:
	uv lock

test:
	uv run --group dev python -m pytest

lint:
	uv run ruff check src mcp tools cv tests

format:
	uv run ruff format src mcp tools cv tests
	uv run ruff check --fix src mcp tools cv tests

preflight:
	$(PY) tools/recruiter_orchestrate.py preflight

doctor:
	uv lock --check
	uv run ruff check src mcp tools cv tests
	uv run --group dev python -m pytest
	$(PY) tools/recruiter_orchestrate.py preflight --browse-status

scout:
	$(PY) tools/recruiter_orchestrate.py scout --headed

plan:
	$(PY) tools/recruiter_orchestrate.py plan --tier tier_1

approve-session:
	$(PY) tools/recruiter_approval.py approve-session --session pipeline/recruiter_session_state.json

check-approvals:
	$(PY) tools/recruiter_approval.py check-session --session pipeline/recruiter_session_state.json

dispatch-dry:
	$(PY) tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run

daily-dry:
	$(PY) tools/recruiter_orchestrate.py daily --headed --dry-run

daily-queue:
	$(PY) tools/automation_control.py enqueue --kind daily_search --trigger make --spawn-worker
	@echo "The private worker started. If the dashboard is not already open, run: make dashboard-dev"

weekly-review:
	$(PY) tools/opportunity_dashboard.py weekly-roi
	$(PY) tools/variant_performance.py
	$(PY) tools/variant_performance.py --by source
	$(PY) tools/variant_performance.py --roi
	$(PY) tools/hiring_network_workflow.py report
	$(PY) tools/opportunity_orchestrate.py --config config/opportunities.example.yaml report --summary

rebuild-cvs:
	$(PY) cv/build_cv_pdf.py --all

smoke:
	./scripts/smoke_repo.sh

audit-runtime:
	uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file /tmp/job-search-runtime-requirements.txt > /dev/null
	uvx pip-audit -r /tmp/job-search-runtime-requirements.txt

dashboard-dev:
	$(PY) tools/dashboard_service.py --mode dev --port "$(DASHBOARD_PORT)"

dashboard-build:
	cd dashboard && npm run build

dashboard-start: dashboard-build
	$(PY) tools/dashboard_service.py --mode production --port "$(DASHBOARD_PORT)"

dashboard-open:
	open "http://127.0.0.1:$(DASHBOARD_PORT)"

dashboard-worker:
	$(PY) tools/dashboard_service.py --mode worker

dashboard-status:
	$(PY) tools/workspace_control.py status

dashboard-backup:
	$(PY) tools/workspace_control.py backup-create-interactive

dashboard-restore:
	@test -n "$(BACKUP)" || (echo "Use: make dashboard-restore BACKUP=career-backup-YYYYMMDDTHHMMSSZ-abcdef.career-backup" && exit 2)
	$(PY) tools/workspace_control.py backup-restore-interactive --filename "$(BACKUP)"

dashboard-test:
	cd dashboard && npm test && npm run typecheck

dashboard-e2e:
	cd dashboard && CAREER_DASHBOARD_TOKEN=local-e2e-token npm run e2e

dev-agent-doctor:
	$(PY) tools/local_dev_agents.py doctor

dev-agent-benchmark:
	$(PY) tools/local_dev_agents.py benchmark

dev-agent-model-benchmark:
	$(PY) tools/local_dev_agents.py model-benchmark --candidate qwen3.6:35b-a3b-coding-nvfp4

dev-agent-plan:
	$(PY) tools/local_dev_agents.py plan --trigger-source manual

dev-agent-proposals:
	$(PY) tools/local_dev_agents.py proposals

dev-agent-proposal-approve:
	@test -n "$(ID)" || (echo "Use: make dev-agent-proposal-approve ID=proposal_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py proposal-approve --proposal-id "$(ID)" --spawn-worker

dev-agent-proposal-reject:
	@test -n "$(ID)" || (echo "Use: make dev-agent-proposal-reject ID=proposal_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py proposal-reject --proposal-id "$(ID)"

dev-agent-autonomy:
	$(PY) tools/local_dev_agents.py autonomy

dev-agent-service:
	$(PY) tools/local_dev_agents.py service

dev-agent-status:
	$(PY) tools/local_dev_agents.py status

dev-agent-run:
	@test -n "$(TASK)" || (echo "Use: make dev-agent-run TASK=runtime/local-task.json" && exit 2)
	$(PY) tools/local_dev_agents.py run --task-file "$(TASK)"

dev-agent-show:
	@test -n "$(ID)" || (echo "Use: make dev-agent-show ID=agent_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py show --task-id "$(ID)"

dev-agent-verify:
	@test -n "$(ID)" || (echo "Use: make dev-agent-verify ID=agent_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py verify --task-id "$(ID)"

dev-agent-approve:
	@test -n "$(ID)" || (echo "Use: make dev-agent-approve ID=agent_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py approve --task-id "$(ID)" --reviewed-by main-codex

dev-agent-apply:
	@test -n "$(ID)" || (echo "Use: make dev-agent-apply ID=agent_<id>" && exit 2)
	$(PY) tools/local_dev_agents.py apply --task-id "$(ID)"

dev-agent-cleanup:
	$(PY) tools/local_dev_agents.py cleanup

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
	$(PY) tools/recruiter_orchestrate.py preflight --browse-status
