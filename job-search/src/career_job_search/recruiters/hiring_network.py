#!/usr/bin/env python3
"""Agentic hiring-network workflow for LinkedIn outreach.

The workflow keeps analysis deterministic and structured. Agent-like nodes
classify, match, rank, and write notes; the existing Playwright dispatcher is
the only component that can click LinkedIn controls.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from career_job_search.cvs.matching import PROFILES_PATH, load_profiles
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    DEFAULT_LINKEDIN_CONFIG,
    HIRING_NETWORK_RUN_STATE_JSON,
    RECRUITERS_CSV,
)
from career_job_search.recruiters import hiring_ranking as _hiring_ranking
from career_job_search.recruiters.discovery_csv import read_validated_rows
from career_job_search.recruiters.hiring_config import (
    _DISCOVERY_PERSONA_PRESERVED,
    VISION_ALLOWED_LABELS,
    _load_full_linkedin_cfg,
    candidate_from_scout_record,
    classify_persona,
    deep_merge,
    default_hiring_network_config,
    industry_hit,
    load_workflow_config,
    resolve_persona,
)
from career_job_search.recruiters.hiring_models import (
    CvMatchDecision,
    Decision,
    HistorySignals,
    PersonaDecision,
    ProfileCandidate,
    RankedInvite,
    RunState,
    ScreenState,
    SendTier,
)
from career_job_search.recruiters.hiring_ranking import (
    _parse_company_relevance_score,
    apply_validation_rank_adjustments,
    build_ranked_invite,
    compact_evidence,
    company_sector_score,
    cv_focus_label,
    first_name,
    geo_label,
    geography_score,
    match_candidate_to_cv,
    note_evidence_is_generic,
    personalization_score,
    write_personalized_note,
)
from career_job_search.recruiters.policy import (
    can_attempt_live_dispatch,
    current_send_mode,
    validate_live_dispatch_max,
)
from career_job_search.recruiters.repository import DEFAULT_STATE_DB, require_approvals

try:
    from career_job_search.integrations.linkedin import campaign as bot
except ModuleNotFoundError:
    bot = None

__all__ = (
    "VISION_ALLOWED_LABELS",
    "_DISCOVERY_PERSONA_PRESERVED",
    "CvMatchDecision",
    "Decision",
    "HistorySignals",
    "PersonaDecision",
    "ProfileCandidate",
    "RankedInvite",
    "RunState",
    "ScreenState",
    "SendTier",
    "apply_validation_rank_adjustments",
    "build_ranked_invite",
    "candidate_from_scout_record",
    "classify_persona",
    "compact_evidence",
    "company_sector_score",
    "cv_focus_label",
    "deep_merge",
    "default_hiring_network_config",
    "first_name",
    "geo_label",
    "geography_score",
    "industry_hit",
    "load_workflow_config",
    "match_candidate_to_cv",
    "note_evidence_is_generic",
    "personalization_score",
    "rank_candidate",
    "resolve_persona",
    "write_personalized_note",
)


def rank_candidate(
    candidate: ProfileCandidate,
    persona: PersonaDecision,
    cv: CvMatchDecision,
    cfg: dict[str, Any],
    history: HistorySignals,
    *,
    validated_company_score: float | None = None,
) -> float:
    """Compatibility entrypoint that preserves patchable config loading."""
    return _hiring_ranking.rank_candidate(
        candidate,
        persona,
        cv,
        cfg,
        history,
        validated_company_score=validated_company_score,
        _full_cfg=_load_full_linkedin_cfg(),
    )


def read_action_plan_records(path: Path) -> list[dict[str, Any]]:
    """Read either true JSONL or a legacy JSON array saved with .jsonl suffix."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history_by_variant(
    csv_path: Path = RECRUITERS_CSV,
) -> dict[str, HistorySignals]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    if not csv_path.exists():
        return {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            variant = (row.get("variant_slug") or "").strip()
            if not variant:
                continue
            if (row.get("status") or "").strip() == "sent":
                buckets[variant]["sent"] += 1
            if (row.get("accepted_at") or "").strip():
                buckets[variant]["accepted"] += 1
            if (row.get("reply_at") or "").strip():
                buckets[variant]["reply"] += 1
            if (row.get("interview_at") or "").strip():
                buckets[variant]["interview"] += 1
    return {
        variant: HistorySignals(
            sent_count=counts["sent"],
            accepted_count=counts["accepted"],
            reply_count=counts["reply"],
            interview_count=counts["interview"],
        )
        for variant, counts in buckets.items()
    }


def read_contacted_urls(csv_path: Path = RECRUITERS_CSV) -> set[str]:
    if not csv_path.exists():
        return set()
    contacted: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "").strip()
            if status not in {"sent", "skipped_pending"}:
                continue
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if canon:
                contacted.add(canon)
    return contacted


def build_ranked_plan_from_records(
    records: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
    contacted_urls: set[str] | None = None,
    history_by_variant: dict[str, HistorySignals] | None = None,
) -> list[RankedInvite]:
    contacted = contacted_urls or set()
    history_map = history_by_variant or {}
    latest_by_url: dict[str, dict[str, Any]] = {}
    for record in records:
        try:
            candidate = candidate_from_scout_record(record)
        except ValueError:
            continue
        latest_by_url[candidate.profile_url] = record

    invites: list[RankedInvite] = []
    for record in latest_by_url.values():
        candidate = candidate_from_scout_record(record)
        hist = history_map.get(candidate.search_variant_slug) or HistorySignals()
        invite = build_ranked_invite(
            candidate,
            cfg=cfg,
            history=hist,
            already_contacted=candidate.profile_url in contacted,
            pending_visible=str(record.get("status") or "") == "skipped_pending",
            validation_status=str(record.get("validation_status") or ""),
            company_relevance_score=_parse_company_relevance_score(
                record.get("company_relevance_score")
            ),
            discovery_persona=str(record.get("discovery_persona") or ""),
            company_flags=str(record.get("company_flags") or ""),
        )
        invites.append(invite)

    invites.sort(
        key=lambda x: (-x.rank_score, x.candidate.name.lower(), x.candidate.profile_url)
    )
    return invites


def classify_screen_state_from_text(text: str) -> ScreenState:
    blob = text.lower()
    if "captcha" in blob or "prove you're human" in blob or "prove youre human" in blob:
        return "captcha"
    if (
        "checkpoint" in blob
        or "security verification" in blob
        or "verify your identity" in blob
    ):
        return "checkpoint"
    if "unusual activity" in blob or "temporarily restricted" in blob:
        return "unusual_activity"
    if ("sign in" in blob and "password" in blob) or "login" in blob:
        return "login_wall"
    if "pending" in blob and "invitation" in blob:
        return "pending_visible"
    if "invite" in blob and "connect" in blob:
        return "connect_visible"
    if "profile" in blob or "experience" in blob or "about" in blob:
        return "profile_loaded"
    return "unknown"


def dependency_status() -> dict[str, bool]:
    deps = {
        "pydantic": True,
        "langgraph": importlib.util.find_spec("langgraph") is not None,
        "playwright": importlib.util.find_spec("playwright") is not None,
        "yaml": importlib.util.find_spec("yaml") is not None,
    }
    return deps


def build_langgraph_workflow(stage: str = "all") -> Any:
    """Build the LangGraph workflow for the three-agent pipeline."""
    from importlib import import_module

    build_graph = import_module(
        "career_job_search.recruiters.graph_workflow"
    ).build_langgraph_workflow

    return build_graph(stage)  # type: ignore[arg-type]


def cmd_preflight(args: argparse.Namespace) -> int:
    deps = dependency_status()
    print("Hiring-network preflight")
    for name, ok in deps.items():
        print(f"{name}: {'ok' if ok else 'missing'}")
    try:
        _ = load_profiles(PROFILES_PATH)
        print(f"CV profiles: ok ({PROFILES_PATH})")
    except Exception as exc:
        print(f"CV profiles: error ({exc})")
    legacy_records = read_action_plan_records(Path(args.source_action_plan))
    print(f"Source action plan readable records: {len(legacy_records)}")
    if bot is not None:
        try:
            limits = {}
            if yaml is not None and DEFAULT_LINKEDIN_CONFIG.exists():
                raw = (
                    yaml.safe_load(DEFAULT_LINKEDIN_CONFIG.read_text(encoding="utf-8"))
                    or {}
                )
                limits = raw.get("limits") or {}
            print(f"Effective invite cap: {bot.effective_daily_invite_cap(limits)}")
        except Exception as exc:
            print(f"Effective invite cap: unavailable ({exc})")
    try:
        from career_job_search.recruiters.ollama_client import health_check, llm_enabled

        full = _load_full_linkedin_cfg()
        if llm_enabled(full):
            ok, msg = health_check(str((full.get("llm") or {}).get("base_url") or ""))
            print(f"Ollama: {'ok' if ok else 'warn'} ({msg})")
    except Exception as exc:
        print(f"Ollama: unavailable ({exc})")
    return 0 if all(deps.values()) else 2


def cmd_rank(args: argparse.Namespace) -> int:
    cfg = load_workflow_config(Path(args.config))
    records = read_action_plan_records(Path(args.source_action_plan))
    invites = build_ranked_plan_from_records(
        records,
        cfg=cfg,
        contacted_urls=read_contacted_urls(RECRUITERS_CSV),
        history_by_variant=load_history_by_variant(RECRUITERS_CSV),
    )
    action_records = [invite.to_action_record() for invite in invites]
    write_jsonl(Path(args.output), action_records)
    state = RunState(queue=invites, audit_records=action_records[:50])
    HIRING_NETWORK_RUN_STATE_JSON.write_text(
        state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    counts = Counter(invite.send_tier for invite in invites)
    print(
        f"Wrote {args.output} with {len(invites)} ranked profile(s): "
        f"auto_send={counts['auto_send']} queue_review={counts['queue_review']} skip={counts['skip']}"
    )
    for invite in invites[: min(5, len(invites))]:
        print(
            f"- {invite.send_tier} score={invite.rank_score:.1f} "
            f"{invite.persona.persona} {invite.cv_match.best_cv_variant} "
            f"{invite.candidate.name or invite.candidate.profile_url}"
        )
    return 0


def _run_scout(args: argparse.Namespace) -> int:
    cli = [
        sys.executable,
        str(Path(__file__).resolve().parent / "recruiter_orchestrate.py"),
        "--config",
        str(args.config),
        "scout",
        "--headed" if args.headed else "--no-headed",
        "--action-plan",
        str(args.source_action_plan),
    ]
    if args.browser_channel:
        cli.extend(["--browser-channel", args.browser_channel])
    if args.variant:
        cli.extend(["--variant", args.variant])
    return subprocess.call(cli)


def cmd_daily(args: argparse.Namespace) -> int:
    if not args.dry_run and args.auto_send:
        args.max = validate_live_dispatch_max(
            getattr(args, "max", None),
            dry_run=False,
            option_name="--max",
        )
    if args.skip_scout:
        scout_rc = 0
    else:
        scout_rc = _run_scout(args)
    if scout_rc != 0:
        return scout_rc
    rank_rc = cmd_rank(args)
    if rank_rc != 0 or args.dry_run or not args.auto_send:
        return rank_rc
    return cmd_dispatch(args)


def automation_cfg(full_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = full_cfg if full_cfg is not None else _load_full_linkedin_cfg()
    block = cfg.get("automation") or {}
    return block if isinstance(block, dict) else {}


def apply_full_auto_graph_args(args: argparse.Namespace) -> None:
    """Turn on review-bypass settings only when explicitly acknowledged."""
    if not getattr(args, "full_auto", False):
        return
    if current_send_mode() == "manual":
        raise SystemExit(
            "--full-auto is unavailable while LINKEDIN_SEND_MODE=manual. Run "
            "with --dry-run, review the queue, then copy notes and record manual outcomes."
        )
    if not getattr(args, "allow_live_dispatch", False):
        raise SystemExit(
            "--full-auto requires --allow-live-dispatch after manual risk review."
        )
    args.dry_run = False
    args.auto_approve_review = True
    args.max = validate_live_dispatch_max(
        args.max,
        dry_run=False,
        option_name="--max",
    )
    if getattr(args, "only_new", None) is None:
        args.only_new = True
    if getattr(args, "fresh_run", None) is None:
        args.fresh_run = True


def _resolve_only_new(
    only_new: bool | None, *, tier: str, full_cfg: dict[str, Any]
) -> bool:
    if only_new is not None:
        return only_new
    if tier == "full_auto":
        return True
    return bool(automation_cfg(full_cfg).get("only_new", False))


def _polish_note_for_dispatch(row: dict[str, Any]) -> tuple[str, str]:
    """Last-mile LLM polish so every live send uses a personalized note."""
    note = re.sub(r"\s+", " ", str(row.get("note") or "")).strip()
    reason = str(row.get("note_reason") or "")
    if ":llm_note" in reason:
        return note[:280], reason

    full_cfg = _load_full_linkedin_cfg()
    try:
        from career_job_search.recruiters.ollama_agents import polish_outreach_note
        from career_job_search.recruiters.ollama_client import agent_enabled

        if not agent_enabled(full_cfg, "outreach_writer"):
            return note[:280], reason
        polished = polish_outreach_note(
            draft_note=note,
            name=str(row.get("name") or ""),
            headline=str(row.get("headline") or ""),
            company=str(row.get("company") or ""),
            persona=str(row.get("persona") or "hiring_manager"),
            cv_variant=str(row.get("cv_variant") or "luxury-retail"),
            full_cfg=full_cfg,
        )
        if not polished or not polished.note.strip():
            return note[:280], reason
        evidence = (polished.evidence_cited or "").strip()
        new_note = polished.note.strip()
        if len(new_note) > 280:
            new_note = new_note[:277].rstrip(" ,.;:") + "..."
        persona = str(row.get("persona") or "hiring_manager")
        cv = str(row.get("cv_variant") or "luxury-retail")
        return new_note, f"{persona}:{evidence or 'llm'}:{cv}:llm_note"
    except Exception:
        return note[:280], reason


def _approved_invites_from_plan(
    path: Path,
    *,
    tier: str,
    max_profiles: int | None,
    only_new: bool = False,
    apply_stub_guard: bool = True,
) -> list[dict[str, Any]]:
    from career_job_search.recruiters.dispatch_guard import (
        is_stub_or_empty_row,
        load_already_sent_urls,
    )

    rows = read_action_plan_records(path)
    full_cfg = _load_full_linkedin_cfg()
    auto = automation_cfg(full_cfg)
    include_queue = bool(auto.get("include_queue_review"))
    already_sent = load_already_sent_urls() if only_new else set()
    approved: list[dict[str, Any]] = []
    for row in rows:
        send_tier = str(row.get("send_tier") or "")
        decision = str(row.get("decision") or "")
        if tier == "full_auto":
            if send_tier == "auto_send" and decision == "approved":
                pass
            elif include_queue and send_tier == "queue_review":
                pass
            else:
                continue
        else:
            if decision != "approved":
                continue
            if tier and tier != "all" and send_tier != tier:
                continue
        if apply_stub_guard:
            skip, _reason = is_stub_or_empty_row(row)
            if skip:
                url = str(row.get("profile_url") or row.get("name") or "")
                print(f"Skipped (stub/empty): {url}")
                continue
        if only_new:
            url = lis.canonical_profile_url(row.get("profile_url") or "")
            if url and url in already_sent:
                print(f"Skipped (already sent): {url}")
                continue
        approved.append(row)
        if max_profiles is not None and len(approved) >= max_profiles:
            break
    return approved


def cmd_dispatch(args: argparse.Namespace) -> int:
    args.max = validate_live_dispatch_max(
        getattr(args, "max", None),
        dry_run=bool(getattr(args, "dry_run", False)),
        option_name="--max",
    )
    tier = str(getattr(args, "tier", "auto_send") or "auto_send")
    full_cfg = _load_full_linkedin_cfg()
    only_new = _resolve_only_new(
        getattr(args, "only_new", None), tier=tier, full_cfg=full_cfg
    )
    approved = _approved_invites_from_plan(
        Path(args.output),
        tier=tier,
        max_profiles=args.max,
        only_new=only_new,
    )
    if not approved:
        raise SystemExit("No approved invites to dispatch.")
    if getattr(args, "dry_run", False):
        print(
            f"DRY RUN: {len(approved)} approved invite(s) would be dispatched "
            f"from {Path(args.output)}"
        )
        for idx, row in enumerate(approved, start=1):
            note, _ = _polish_note_for_dispatch(row)
            print(
                f"{idx}. score={row.get('rank_score')} persona={row.get('persona')} "
                f"cv={row.get('cv_variant')} name={row.get('name') or row.get('profile_url')}"
            )
            print(f"   note: {note[:280]}")
        return 0

    send_mode = current_send_mode()
    if send_mode == "manual":
        raise SystemExit(
            "Manual LinkedIn send mode is active. Open each profile, copy the "
            "approved note, and record manual outcomes from the dashboard."
        )
    if not getattr(args, "allow_live_dispatch", False):
        raise SystemExit(
            "Live dispatch is blocked by default. Re-run with --dry-run for review "
            "or add --allow-live-dispatch after manually reviewing the queue."
        )
    if bot is None:
        raise SystemExit(
            "Playwright dispatcher unavailable: run uv sync --locked --all-groups first."
        )
    raw_cfg = bot.load_config(Path(args.config))
    queued: list[tuple[str, str]] = []
    planned: dict[str, dict[str, Any]] = {}
    auto = automation_cfg(_load_full_linkedin_cfg())
    full_cfg = _load_full_linkedin_cfg()
    try:
        from career_job_search.recruiters.ollama_client import (
            agent_enabled,
            llm_enabled,
        )

        llm_notes_required = bool(
            auto.get("require_llm_note")
            and llm_enabled(full_cfg)
            and agent_enabled(full_cfg, "outreach_writer")
        )
    except Exception:
        llm_notes_required = bool(auto.get("require_llm_note"))
    for row in approved:
        note, note_reason = _polish_note_for_dispatch(row)
        if llm_notes_required and ":llm_note" not in note_reason:
            print(
                f"Skipping (no LLM note): {row.get('name') or row.get('profile_url')}"
            )
            continue
        url = lis.canonical_profile_url(row.get("profile_url") or "")
        variant = str(row.get("cv_variant") or "")
        if not url or not variant:
            continue
        queued.append((url, variant))
        planned[url] = {
            "note": note,
            "persona": row.get("persona") or "",
            "rank_score": row.get("rank_score") or "",
            "profile_confidence": row.get("persona_confidence") or "",
            "safety_decision": row.get("decision") or "",
            "note_reason": note_reason,
        }
    if not queued:
        raise SystemExit("No dispatchable invites after LLM note polish.")
    invite_notes = [
        (url, planned.get(url, {}).get("note") or "") for url, _variant in queued
    ]
    gate = can_attempt_live_dispatch(
        invite_notes,
        allow_live_dispatch=getattr(args, "allow_live_dispatch", False),
        db_path=DEFAULT_STATE_DB,
        send_mode=send_mode,
    )
    approval_failures = require_approvals(invite_notes)
    if not gate.allowed:
        preview = "\n".join(
            f"- {f.reason}: {f.profile_url}" for f in approval_failures[:10]
        )
        more = (
            ""
            if len(approval_failures) <= 10
            else f"\n... {len(approval_failures) - 10} more"
        )
        raise SystemExit(
            "Live dispatch requires a matching SQLite approval ledger entry for "
            "each profile and exact note hash. Run:\n"
            f"  python3 -m career_job_search.recruiters.approval approve-session --session {Path(args.output)}\n"
            f"Gate reason: {gate.reason}\n"
            f"Missing approvals:\n{preview or '(none)'}{more}"
        )
    dispatch_args = argparse.Namespace(
        headed=args.headed,
        dry_run=getattr(args, "dry_run", False),
        scout_jsonl_only=False,
        config=Path(args.config),
        max_connections_override=args.max,
        variant_filter=None,
        browser_channel=args.browser_channel,
        allow_live_dispatch=getattr(args, "allow_live_dispatch", False),
    )
    return bot.run_linked_in_campaign_backend(
        dispatch_args,
        raw_cfg,
        queued_override=queued,
        skip_discovery=True,
        planned_invites=planned,
    )


def cmd_report(args: argparse.Namespace) -> int:
    if getattr(args, "persona_stats", False):
        from career_job_search.recruiters.persona_stats import write_persona_stats

        stats = write_persona_stats()
        print("Persona accept-rate stats (pipeline/persona_stats.json)")
        if not stats:
            print("  (no data yet — run followup after sends)")
            return 0
        print(f"{'Persona':<28} {'Sent':>6} {'Acc':>6} {'Rate':>7}")
        print("-" * 52)
        for persona in sorted(stats.keys()):
            block = stats[persona]
            print(
                f"{persona:<28} {block.get('sent', 0):>6} "
                f"{block.get('accepted', 0):>6} {block.get('rate', 0.0):>6.1%}"
            )
        return 0

    rows = read_action_plan_records(Path(args.output))
    counts = Counter(str(row.get("send_tier") or "") for row in rows)
    personas = Counter(str(row.get("persona") or "") for row in rows)
    skip_reasons: Counter[str] = Counter()
    for row in rows:
        flags = row.get("risk_flags")
        if isinstance(flags, list):
            for flag in flags:
                if flag:
                    skip_reasons[str(flag)] += 1
    print("Hiring-network ranked plan")
    print(f"records: {len(rows)}")
    print(f"tiers: {dict(counts)}")
    print(f"personas: {dict(personas)}")
    if skip_reasons:
        print(f"risk_flags: {dict(skip_reasons)}")
    for row in rows[:10]:
        print(
            f"- {row.get('send_tier')} score={row.get('rank_score')} "
            f"{row.get('persona')} {row.get('cv_variant')} {row.get('name')}"
        )
    perf = subprocess.call(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "recruiter_performance.py"),
            "--by-persona",
        ]
    )
    return 0 if perf == 0 else perf


def build_parser() -> argparse.ArgumentParser:
    """Build the stable CLI parser from the dedicated adapter module."""
    from career_job_search.recruiters.hiring_cli import build_parser as _build_parser

    return _build_parser()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        return cmd_preflight(args)
    if args.cmd == "rank":
        return cmd_rank(args)
    if args.cmd == "daily":
        return cmd_daily(args)
    if args.cmd == "dispatch":
        return cmd_dispatch(args)
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "bridge":
        import yaml

        from career_job_search.recruiters.discovery_bridge import (
            append_scout_records,
            rows_for_bridge,
            validated_to_scout_records,
        )

        rows = read_validated_rows(args.validated_csv)
        bridged = rows_for_bridge(rows, include_review=not args.approved_only)
        cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        records = validated_to_scout_records(bridged, cfg=cfg)
        print(f"Bridgeable rows: {len(bridged)}")
        for record in records[:10]:
            print(
                f"- {record.get('profile_url')} variant={record.get('variant_slug_best')}"
            )
        if args.write_action_plan and not args.dry_run:
            append_scout_records(records, args.action_plan)
            print(f"Appended {len(records)} scout row(s) to {args.action_plan}")
        return 0
    if args.cmd == "graph":
        from importlib import import_module

        cmd_graph_run = import_module(
            "career_job_search.recruiters.graph_workflow"
        ).cmd_graph_run

        if args.graph_cmd == "run":
            apply_full_auto_graph_args(args)
            return cmd_graph_run(args)
        raise SystemExit(f"Unknown graph command {args.graph_cmd!r}")
    raise SystemExit(f"Unknown command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
