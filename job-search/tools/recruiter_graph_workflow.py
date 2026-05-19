"""LangGraph orchestration for the three-agent recruiter pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal, TypedDict

from recruiter_discovery_bridge import (
    append_scout_records,
    rows_for_bridge,
    validated_to_scout_records,
)
from recruiter_discovery_csv import read_validated_rows
from recruiter_linkedin_paths import (
    ACTION_PLAN_JSONL,
    CANDIDATES_DISCOVERY_CSV,
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
    HIRING_NETWORK_ACTION_PLAN_JSONL,
)

GraphStage = Literal["all", "discovery", "validate", "rank", "dispatch"]


class WorkflowState(TypedDict, total=False):
    config_path: str
    discovery_csv: str
    validated_csv: str
    action_plan_jsonl: str
    hiring_network_jsonl: str
    stage: str
    dry_run: bool
    auto_approve_review: bool
    headed: bool
    max_dispatch: int
    backend: str
    blockers: list[str]
    errors: list[str]
    discovery_count: int
    validated_count: int
    needs_linkedin_url_count: int
    bridged_count: int
    interrupt: str
    finished: bool
    no_llm: bool
    full_auto: bool
    verbose_llm: bool
    no_cache: bool
    no_merge_mcp: bool
    fresh_run: bool
    enriched_count: int
    no_enrich: bool
    enrich_browser: bool
    only_new: bool | None


def _cfg_path(state: WorkflowState) -> Path:
    return Path(state.get("config_path") or DEFAULT_LINKEDIN_CONFIG)


def node_preflight(state: WorkflowState) -> WorkflowState:
    import hiring_network_workflow as hn

    args = argparse.Namespace(
        config=_cfg_path(state),
        source_action_plan=ACTION_PLAN_JSONL,
    )
    rc = hn.cmd_preflight(args)
    out = dict(state)
    if rc != 0:
        out.setdefault("blockers", []).append("preflight_failed")
    return out


def _full_cfg(state: WorkflowState) -> dict[str, Any]:
    import yaml

    with _cfg_path(state).open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    llm = {**(cfg.get("llm") or {})}
    if state.get("no_llm"):
        llm["enabled"] = False
    if state.get("verbose_llm"):
        llm["verbose"] = True
        llm["trace"] = True
    if llm:
        cfg = {**cfg, "llm": llm}
    return cfg


def _trace_node(
    state: WorkflowState, node: str, *, message: str = "", **meta: Any
) -> None:
    from recruiter_llm_trace import trace_graph_node

    trace_graph_node(_full_cfg(state), node, message=message, meta=meta or None)


def node_web_discover(state: WorkflowState) -> WorkflowState:
    from recruiter_web_discover import run_discovery

    _trace_node(state, "web_discover", message="start")
    out = dict(state)
    discovery_csv = Path(state.get("discovery_csv") or CANDIDATES_DISCOVERY_CSV)
    rows, errors = run_discovery(
        cfg_path=_cfg_path(state),
        output_path=discovery_csv,
        backend=str(state.get("backend") or "auto"),
        merge_mcp=not bool(state.get("no_merge_mcp")),
        no_llm=bool(state.get("no_llm")),
        verbose_llm=bool(state.get("verbose_llm")),
        use_cache=not bool(state.get("no_cache")),
    )
    out["discovery_count"] = len(rows)
    out["needs_linkedin_url_count"] = sum(
        1 for r in rows if (r.get("needs_linkedin_url") or "").lower() == "true"
    )
    if errors:
        out.setdefault("errors", []).extend(errors)
    if out.get("needs_linkedin_url_count", 0) > 0:
        out["interrupt"] = "missing_linkedin_urls"
    _trace_node(
        state,
        "web_discover",
        message="done",
        discovery_count=len(rows),
        needs_linkedin_url=out.get("needs_linkedin_url_count", 0),
    )
    return out


def node_linkedin_resolve(state: WorkflowState) -> WorkflowState:
    """MCP merge happens inside web_discover.run_discovery."""
    return dict(state)


def node_company_validator(state: WorkflowState) -> WorkflowState:
    from recruiter_company_validate import run_validation

    _trace_node(state, "company_validator", message="start")
    out = dict(state)
    validated_csv = Path(state.get("validated_csv") or CANDIDATES_VALIDATED_CSV)
    discovery_csv = Path(state.get("discovery_csv") or CANDIDATES_DISCOVERY_CSV)
    rows = run_validation(
        input_path=discovery_csv,
        output_path=validated_csv,
        cfg_path=_cfg_path(state),
        backend=str(state.get("backend") or "auto"),
        no_llm=bool(state.get("no_llm")),
        verbose_llm=bool(state.get("verbose_llm")),
    )
    out["validated_count"] = len(rows)
    if not state.get("auto_approve_review"):
        review = sum(1 for r in rows if r.get("validation_status") == "review")
        if review:
            out["interrupt"] = "manual_validation_review"
    _trace_node(
        state,
        "company_validator",
        message="done",
        validated_count=len(rows),
        review_count=sum(1 for r in rows if r.get("validation_status") == "review"),
    )
    return out


def node_supervisor_agent(state: WorkflowState) -> WorkflowState:
    from recruiter_discovery_csv import read_validated_rows, write_validated_rows
    from recruiter_ollama_agents import supervise_row
    from recruiter_ollama_client import agent_cfg, agent_enabled

    out = dict(state)
    full_cfg = _full_cfg(state)
    _trace_node(state, "supervisor_agent", message="start")
    if not agent_enabled(full_cfg, "supervisor"):
        return out

    validated_csv = Path(state.get("validated_csv") or CANDIDATES_VALIDATED_CSV)
    rows = read_validated_rows(validated_csv)
    review_indices = [
        i for i, r in enumerate(rows) if r.get("validation_status") == "review"
    ]
    if not review_indices:
        return out

    sup_cfg = agent_cfg(full_cfg, "supervisor")
    cv_block = full_cfg.get("company_validation") or {}
    approve_threshold = float(cv_block.get("approve_threshold") or 60)
    persona_boost = float(cv_block.get("persona_cross_sector_boost") or 0)
    # Cross-sector personas get a lowered effective approve threshold equal
    # to the same boost applied during validation. Without this, the LLM
    # supervisor would never flip a boosted "review" row to "approved" and
    # auto-send is impossible for HR recruiters at non-retail companies.
    cross_sector_personas = {
        "recruiter_hr",
        "talent_acquisition",
        "executive_search",
        "hiring_manager",
    }
    hard_flags = {"outreach_exclude_term", "wrong_sector", "staffing_only"}
    heavy_limit = 5
    heavy_used = 0
    unresolved = 0

    for idx in review_indices:
        row = dict(rows[idx])
        if heavy_used < heavy_limit and sup_cfg.get("heavy_model"):
            row["_use_heavy_supervisor"] = "true"
            heavy_used += 1
        decision = supervise_row(row, full_cfg=full_cfg)
        if not decision:
            unresolved += 1
            continue
        flags = {
            x.strip()
            for x in str(row.get("company_flags") or "").split(",")
            if x.strip()
        }
        score = float(row.get("company_relevance_score") or 0)
        persona = (row.get("persona") or "").strip().lower()
        effective_threshold = approve_threshold
        if persona in cross_sector_personas and persona_boost > 0:
            effective_threshold = max(approve_threshold - persona_boost, 35.0)
        if decision.action == "approved" and score >= effective_threshold:
            if not flags.intersection(hard_flags):
                rows[idx]["validation_status"] = "approved"
                continue
        if decision.action == "reject" and not flags.intersection(hard_flags):
            rows[idx]["validation_status"] = "reject"
            continue
        unresolved += 1

    write_validated_rows(rows, validated_csv)
    if unresolved and not state.get("auto_approve_review"):
        out["interrupt"] = "supervisor_review"
    _trace_node(
        state,
        "supervisor_agent",
        message="done",
        review_rows=len(review_indices),
        unresolved=unresolved,
    )
    return out


def node_profile_enrich(state: WorkflowState) -> WorkflowState:
    from recruiter_discovery_csv import write_validated_rows
    from recruiter_profile_enrich import enrich_validated_rows, load_full_cfg

    _trace_node(state, "profile_enrich", message="start")
    out = dict(state)
    if state.get("no_enrich"):
        _trace_node(state, "profile_enrich", message="skipped")
        return out

    validated_csv = Path(state.get("validated_csv") or CANDIDATES_VALIDATED_CSV)
    rows = read_validated_rows(validated_csv)
    full_cfg = load_full_cfg(_cfg_path(state))
    enriched, errors = enrich_validated_rows(
        rows,
        full_cfg=full_cfg,
        backend=str(state.get("backend") or "auto"),
        use_browser=bool(state.get("enrich_browser")),
        headed=bool(state.get("headed", True)),
    )
    write_validated_rows(enriched, validated_csv)
    out["enriched_count"] = sum(
        1 for row in enriched if (row.get("enriched_at") or "").strip()
    )
    if errors:
        out.setdefault("errors", []).extend(errors[:5])
    _trace_node(
        state,
        "profile_enrich",
        message="done",
        enriched_count=out.get("enriched_count", 0),
    )
    return out


def node_bridge_to_scout(state: WorkflowState) -> WorkflowState:
    import yaml

    out = dict(state)
    validated_csv = Path(state.get("validated_csv") or CANDIDATES_VALIDATED_CSV)
    action_plan = Path(state.get("action_plan_jsonl") or ACTION_PLAN_JSONL)
    rows = read_validated_rows(validated_csv)
    bridged = rows_for_bridge(
        rows, include_review=bool(state.get("auto_approve_review"))
    )
    with _cfg_path(state).open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    records = validated_to_scout_records(bridged, cfg=cfg)
    out["bridged_count"] = len(records)
    if records:
        append_scout_records(records, action_plan)
    return out


def node_rank(state: WorkflowState) -> WorkflowState:
    import hiring_network_workflow as hn

    out = dict(state)
    args = argparse.Namespace(
        config=_cfg_path(state),
        source_action_plan=Path(state.get("action_plan_jsonl") or ACTION_PLAN_JSONL),
        output=Path(
            state.get("hiring_network_jsonl") or HIRING_NETWORK_ACTION_PLAN_JSONL
        ),
    )
    rc = hn.cmd_rank(args)
    if rc != 0:
        out.setdefault("blockers", []).append("rank_failed")
    return out


def node_dispatcher(state: WorkflowState) -> WorkflowState:
    import hiring_network_workflow as hn

    out = dict(state)
    full_cfg = hn._load_full_linkedin_cfg()
    tier = "full_auto" if state.get("full_auto") else "auto_send"
    only_new = state.get("only_new")
    if only_new is None:
        only_new = hn._resolve_only_new(None, tier=tier, full_cfg=full_cfg)
    args = argparse.Namespace(
        config=_cfg_path(state),
        output=Path(
            state.get("hiring_network_jsonl") or HIRING_NETWORK_ACTION_PLAN_JSONL
        ),
        headed=bool(state.get("headed", True)),
        dry_run=bool(state.get("dry_run", True)),
        tier=tier,
        max=state.get("max_dispatch"),
        browser_channel=None,
        only_new=only_new,
    )
    try:
        rc = hn.cmd_dispatch(args)
    except SystemExit as exc:
        out.setdefault("blockers", []).append(str(exc))
        rc = 1
    if rc != 0:
        out.setdefault("blockers", []).append("dispatch_failed")
    out["finished"] = True
    return out


def node_followup_learner(state: WorkflowState) -> WorkflowState:
    out = dict(state)
    if state.get("dry_run"):
        return out
    cli = [
        sys.executable,
        str(Path(__file__).resolve().parent / "linkedin_followup.py"),
        "--headed" if state.get("headed") else "--no-headed",
    ]
    subprocess.call(cli)
    out["finished"] = True
    return out


def build_langgraph_workflow(stage: GraphStage = "all") -> Any:
    try:
        from langgraph.graph import END, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Run: pip install -r requirements.txt"
        ) from exc

    graph = StateGraph(WorkflowState)
    graph.add_node("preflight", node_preflight)
    graph.add_node("web_discover", node_web_discover)
    graph.add_node("linkedin_resolve", node_linkedin_resolve)
    graph.add_node("company_validator", node_company_validator)
    graph.add_node("supervisor_agent", node_supervisor_agent)
    graph.add_node("profile_enrich", node_profile_enrich)
    graph.add_node("bridge_to_scout", node_bridge_to_scout)
    graph.add_node("ranker", node_rank)
    graph.add_node("dispatcher", node_dispatcher)
    graph.add_node("followup_learner", node_followup_learner)

    graph.set_entry_point("preflight")

    # NOTE: profile_enrich runs BEFORE supervisor_agent so the supervisor LLM
    # makes its approve/reject decision on enriched profile text rather than
    # the thin discovery snippet. Without this, HR personas at non-retail
    # companies (correctly flagged "review") never get auto-approved.
    if stage == "discovery":
        graph.add_edge("preflight", "web_discover")
        graph.add_edge("web_discover", "linkedin_resolve")
        graph.add_edge("linkedin_resolve", END)
    elif stage == "validate":
        graph.add_edge("preflight", "company_validator")
        graph.add_edge("company_validator", "profile_enrich")
        graph.add_edge("profile_enrich", "supervisor_agent")
        graph.add_edge("supervisor_agent", END)
    elif stage == "rank":
        graph.add_edge("preflight", "profile_enrich")
        graph.add_edge("profile_enrich", "bridge_to_scout")
        graph.add_edge("bridge_to_scout", "ranker")
        graph.add_edge("ranker", END)
    elif stage == "dispatch":
        graph.add_edge("preflight", "dispatcher")
        graph.add_edge("dispatcher", "followup_learner")
        graph.add_edge("followup_learner", END)
    else:
        graph.add_edge("preflight", "web_discover")
        graph.add_edge("web_discover", "linkedin_resolve")
        graph.add_edge("linkedin_resolve", "company_validator")
        graph.add_edge("company_validator", "profile_enrich")
        graph.add_edge("profile_enrich", "supervisor_agent")
        graph.add_edge("supervisor_agent", "bridge_to_scout")
        graph.add_edge("bridge_to_scout", "ranker")
        graph.add_edge("ranker", "dispatcher")
        graph.add_edge("dispatcher", "followup_learner")
        graph.add_edge("followup_learner", END)

    return graph.compile()


def initial_state(args: argparse.Namespace) -> WorkflowState:
    return WorkflowState(
        config_path=str(args.config),
        discovery_csv=str(args.discovery_csv),
        validated_csv=str(args.validated_csv),
        action_plan_jsonl=str(args.action_plan),
        hiring_network_jsonl=str(args.output),
        stage=args.stage,
        dry_run=bool(args.dry_run),
        auto_approve_review=bool(args.auto_approve_review),
        headed=bool(args.headed),
        max_dispatch=args.max,
        backend=str(args.backend),
        blockers=[],
        errors=[],
        no_llm=bool(getattr(args, "no_llm", False)),
        full_auto=bool(getattr(args, "full_auto", False)),
        verbose_llm=bool(getattr(args, "verbose_llm", False)),
        no_cache=bool(getattr(args, "no_cache", False)),
        no_merge_mcp=bool(getattr(args, "no_merge_mcp", False)),
        fresh_run=bool(getattr(args, "fresh_run", False)),
        no_enrich=bool(getattr(args, "no_enrich", False)),
        enrich_browser=bool(getattr(args, "enrich_browser", False)),
        only_new=getattr(args, "only_new", None),
    )


def cmd_graph_run(args: argparse.Namespace) -> int:
    if getattr(args, "fresh_run", False):
        from recruiter_linkedin_paths import clear_fresh_run_artifacts

        cleared = clear_fresh_run_artifacts()
        print("Fresh run: cleared " + ", ".join(p.name for p in cleared))
    if getattr(args, "verbose_llm", False):
        import yaml
        from recruiter_llm_trace import trace_enabled, trace_path, verbose_enabled

        with Path(args.config).open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        cfg = {
            **cfg,
            "llm": {
                **(cfg.get("llm") or {}),
                "verbose": True,
                "trace": True,
            },
        }
        if verbose_enabled(cfg) or trace_enabled(cfg):
            print(f"LLM trace file: {trace_path(cfg)}", file=sys.stderr)
    if getattr(args, "full_auto", False) and not args.dry_run:
        print(
            "FULL AUTO: live LinkedIn sends with LLM-personalized notes "
            f"(max={args.max}). Playwright clicks Connect — stop on CAPTCHA/login wall."
        )
    workflow = build_langgraph_workflow(args.stage)
    state = initial_state(args)
    result = workflow.invoke(state)

    print("LangGraph pipeline finished")
    for key in (
        "discovery_count",
        "needs_linkedin_url_count",
        "validated_count",
        "enriched_count",
        "bridged_count",
        "interrupt",
    ):
        if key in result and result[key] not in (None, "", 0):
            print(f"  {key}: {result[key]}")
    if result.get("blockers"):
        print(f"  blockers: {result['blockers']}")
    if result.get("errors"):
        for err in result["errors"][:5]:
            print(f"  error: {err}")
    if result.get("interrupt") and not args.auto_approve_review:
        print(f"  paused: {result['interrupt']} — review CSV before continuing")
        return 0
    return 1 if result.get("blockers") else 0
