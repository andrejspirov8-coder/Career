"""Ollama client wrapper (langchain-ollama) for recruiter LLM agents."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_CHAT_MODEL = "qwen3.5:35b-a3b-fast"

_OLLAMA_FAIL_COUNT = 0
_OLLAMA_CIRCUIT_OPEN = False
_CIRCUIT_THRESHOLD = 3


def reset_circuit_breaker() -> None:
    global _OLLAMA_FAIL_COUNT, _OLLAMA_CIRCUIT_OPEN
    _OLLAMA_FAIL_COUNT = 0
    _OLLAMA_CIRCUIT_OPEN = False


def circuit_breaker_open() -> bool:
    return _OLLAMA_CIRCUIT_OPEN


def _record_ollama_failure(full_cfg: dict[str, Any], error: str) -> None:
    global _OLLAMA_FAIL_COUNT, _OLLAMA_CIRCUIT_OPEN
    if not bool(llm_cfg(full_cfg).get("retry_enabled", True)):
        return
    _OLLAMA_FAIL_COUNT += 1
    threshold = int(
        llm_cfg(full_cfg).get("circuit_breaker_threshold") or _CIRCUIT_THRESHOLD
    )
    if _OLLAMA_FAIL_COUNT >= threshold:
        _OLLAMA_CIRCUIT_OPEN = True
        try:
            from career_job_search.recruiters.llm_trace import emit_event

            emit_event(
                full_cfg,
                kind="circuit_breaker",
                message="Ollama circuit open — rules-only for rest of run",
                error=error,
                meta={"fail_count": _OLLAMA_FAIL_COUNT},
            )
        except Exception:
            pass


def _record_ollama_success() -> None:
    global _OLLAMA_FAIL_COUNT
    _OLLAMA_FAIL_COUNT = 0


def _is_timeout_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if "Timeout" in name or "timeout" in str(exc).lower():
        return True
    try:
        import httpx

        if isinstance(
            exc, httpx.ReadTimeout | httpx.ConnectTimeout | httpx.ConnectError
        ):
            return True
    except ImportError:
        pass
    return isinstance(exc, TimeoutError | urllib.error.URLError)


def _should_trip_circuit(exc: BaseException) -> bool:
    """Only infrastructure failures should open the rules-only circuit breaker."""
    if _is_timeout_error(exc):
        return True
    name = type(exc).__name__
    if name in {"ConnectionError", "ConnectError", "ReadError", "OSError"}:
        return True
    try:
        import httpx

        if isinstance(exc, httpx.HTTPError):
            return True
    except ImportError:
        pass
    return isinstance(exc, urllib.error.URLError)


def llm_cfg(full_cfg: dict[str, Any]) -> dict[str, Any]:
    block = full_cfg.get("llm") or {}
    return block if isinstance(block, dict) else {}


def llm_enabled(full_cfg: dict[str, Any]) -> bool:
    return bool(llm_cfg(full_cfg).get("enabled", False))


def merge_llm_runtime_flags(
    full_cfg: dict[str, Any],
    *,
    no_llm: bool = False,
    verbose_llm: bool = False,
) -> dict[str, Any]:
    llm = {**(llm_cfg(full_cfg))}
    if no_llm:
        llm["enabled"] = False
    if verbose_llm:
        llm["verbose"] = True
        llm["trace"] = True
    return {**full_cfg, "llm": llm}


def agent_cfg(full_cfg: dict[str, Any], agent_name: str) -> dict[str, Any]:
    agents = llm_cfg(full_cfg).get("agents") or {}
    block = agents.get(agent_name) or {}
    return block if isinstance(block, dict) else {}


def agent_enabled(full_cfg: dict[str, Any], agent_name: str) -> bool:
    if _OLLAMA_CIRCUIT_OPEN and bool(llm_cfg(full_cfg).get("retry_enabled", True)):
        return False
    if not llm_enabled(full_cfg):
        return False
    block = agent_cfg(full_cfg, agent_name)
    return bool(block.get("enabled", True))


def agent_uses_tools(full_cfg: dict[str, Any], agent_name: str) -> bool:
    return bool(agent_cfg(full_cfg, agent_name).get("use_tools", False))


def resolve_chat_model(full_cfg: dict[str, Any], agent_name: str) -> str:
    block = agent_cfg(full_cfg, agent_name)
    if block.get("model"):
        return str(block["model"])
    default = llm_cfg(full_cfg).get("default_chat_model")
    if default:
        return str(default)
    profile = str(llm_cfg(full_cfg).get("profile") or "balanced")
    profiles = llm_cfg(full_cfg).get("profiles") or {}
    if isinstance(profiles, dict) and profiles.get(profile):
        return str(profiles[profile])
    return DEFAULT_CHAT_MODEL


def prompt_version(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:8]


def health_check(base_url: str = DEFAULT_BASE_URL) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in raw.get("models") or []]
        return True, f"ollama ok ({len(models)} model(s))"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, str(exc)


def _client_timeout_kwargs(full_cfg: dict[str, Any]) -> dict[str, Any]:
    seconds = float(llm_cfg(full_cfg).get("timeout_seconds") or 120)
    return {"timeout": seconds}


def _chat_ollama(full_cfg: dict[str, Any], agent_name: str):
    from langchain_ollama import ChatOllama

    cfg = llm_cfg(full_cfg)
    reasoning = cfg.get("reasoning")
    return ChatOllama(
        model=resolve_chat_model(full_cfg, agent_name),
        base_url=str(cfg.get("base_url") or DEFAULT_BASE_URL),
        temperature=float(cfg.get("temperature", 0.2)),
        num_predict=int(cfg.get("num_predict", 512)),
        keep_alive=str(cfg.get("keep_alive") or "30m"),
        reasoning=False if reasoning is None else bool(reasoning),
        client_kwargs=_client_timeout_kwargs(full_cfg),
    )


def _invoke_with_retry(fn, *, full_cfg: dict[str, Any]):
    try:
        result = fn()
        _record_ollama_success()
        return result
    except Exception as exc:
        if bool(llm_cfg(full_cfg).get("retry_enabled", True)) and _is_timeout_error(
            exc
        ):
            try:
                result = fn()
                _record_ollama_success()
                return result
            except Exception as retry_exc:
                if _should_trip_circuit(retry_exc):
                    _record_ollama_failure(full_cfg, str(retry_exc))
                raise retry_exc from exc
        if bool(llm_cfg(full_cfg).get("retry_enabled", True)) and _should_trip_circuit(
            exc
        ):
            _record_ollama_failure(full_cfg, str(exc))
        raise


def invoke_structured(
    full_cfg: dict[str, Any],
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
    few_shot: list[dict[str, str]] | None = None,
) -> T | None:
    """Call Ollama with structured output; return None on failure if fallback enabled.

    ``few_shot``: optional list of ``{"role": "user", "content": "…"}`` /
    ``{"role": "assistant", "content": "…"}`` pairs injected between
    the system prompt and the real user payload.
    """
    if not agent_enabled(full_cfg, agent_name):
        return None

    model = resolve_chat_model(full_cfg, agent_name)
    from career_job_search.recruiters.llm_trace import AgentCallTrace

    pv = prompt_version(system_prompt)
    with AgentCallTrace(
        full_cfg,
        agent=agent_name,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        meta={"prompt_version": pv},
    ) as trace:
        try:
            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt},
            ]
            if few_shot:
                messages.extend(few_shot)
            messages.append({"role": "user", "content": user_prompt})

            def _call():
                llm = _chat_ollama(full_cfg, agent_name)
                structured = llm.with_structured_output(schema)
                return structured.invoke(messages)

            result = _invoke_with_retry(_call, full_cfg=full_cfg)
            if result is None:
                if not bool(llm_cfg(full_cfg).get("fallback_to_rules", True)):
                    trace.failure("structured output returned None")
                    return None
                fallback = _invoke_structured_fallback(
                    full_cfg, agent_name, system_prompt, user_prompt, schema
                )
                if fallback is None:
                    trace.failure("structured output and fallback returned None")
                else:
                    trace.success(fallback)
                return fallback
            trace.success(result)
            return result
        except Exception as exc:
            if not bool(llm_cfg(full_cfg).get("fallback_to_rules", True)):
                trace.failure(str(exc))
                raise
            fallback = _invoke_structured_fallback(
                full_cfg, agent_name, system_prompt, user_prompt, schema
            )
            if fallback is None:
                trace.failure(str(exc))
            else:
                trace.success(fallback)
            return fallback


def invoke_with_tools(
    full_cfg: dict[str, Any],
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
    tools: list[Any],
    *,
    max_turns: int | None = None,
    few_shot: list[dict[str, str]] | None = None,
) -> T | None:
    """Tool-calling loop; falls back to invoke_structured on bind_tools failure."""
    if not agent_enabled(full_cfg, agent_name) or not tools:
        return invoke_structured(
            full_cfg,
            agent_name,
            system_prompt,
            user_prompt,
            schema,
            few_shot=few_shot,
        )
    block = agent_cfg(full_cfg, agent_name)
    turns = int(max_turns or block.get("max_tool_turns") or 3)
    model = resolve_chat_model(full_cfg, agent_name)
    from career_job_search.recruiters.agent_tools import dispatch_tool_call
    from career_job_search.recruiters.llm_trace import AgentCallTrace, emit_event

    pv = prompt_version(system_prompt)
    try:
        llm = _chat_ollama(full_cfg, agent_name).bind_tools(tools)
    except Exception:
        return invoke_structured(
            full_cfg,
            agent_name,
            system_prompt,
            user_prompt,
            schema,
            few_shot=few_shot,
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    if few_shot:
        messages.extend(few_shot)
    messages.append({"role": "user", "content": user_prompt})
    with AgentCallTrace(
        full_cfg,
        agent=agent_name,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        meta={"prompt_version": pv, "use_tools": True},
    ) as trace:
        try:
            for _ in range(turns):
                resp = _invoke_with_retry(
                    lambda: llm.invoke(messages), full_cfg=full_cfg
                )
                tool_calls = getattr(resp, "tool_calls", None) or []
                if not tool_calls:
                    messages.append(
                        {"role": "assistant", "content": resp.content or ""}
                    )
                    break
                messages.append(resp)
                for call in tool_calls:
                    call_dict = (
                        call
                        if isinstance(call, dict)
                        else {
                            "name": getattr(call, "name", ""),
                            "args": getattr(call, "args", {}),
                            "id": getattr(call, "id", ""),
                        }
                    )
                    result = dispatch_tool_call(call_dict, tools)
                    emit_event(
                        full_cfg,
                        kind="tool_call",
                        agent=agent_name,
                        message=str(call_dict.get("name") or ""),
                        output=result,
                        meta={"prompt_version": pv},
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_dict.get("id") or "",
                            "content": result,
                        }
                    )
                # After collecting tool results, move directly to the structured
                # final call. This keeps the control flow deterministic and avoids
                # an extra tool-model turn when the final schema call is sufficient.
                break
            structured = _chat_ollama(full_cfg, agent_name).with_structured_output(
                schema
            )

            def _final():
                return structured.invoke(messages)

            result = _invoke_with_retry(_final, full_cfg=full_cfg)
            if result is None:
                trace.failure("tool loop structured output None")
                return None
            trace.success(result)
            return result
        except Exception as exc:
            trace.failure(str(exc))
            if bool(llm_cfg(full_cfg).get("fallback_to_rules", True)):
                return invoke_structured(
                    full_cfg, agent_name, system_prompt, user_prompt, schema
                )
            raise


def _invoke_structured_fallback(
    full_cfg: dict[str, Any],
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
) -> T | None:
    try:
        llm = _chat_ollama(full_cfg, agent_name)
        raw = llm.invoke(
            [
                {
                    "role": "system",
                    "content": system_prompt + "\nReply with JSON only.",
                },
                {"role": "user", "content": user_prompt},
            ]
        )
        text = raw.content if hasattr(raw, "content") else str(raw)
        blob = _extract_json_object(text)
        if not blob:
            return None
        return schema.model_validate(json.loads(blob))
    except Exception:
        return None


def _extract_json_object(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def embeddings_client(full_cfg: dict[str, Any]):
    from langchain_ollama import OllamaEmbeddings

    cfg = llm_cfg(full_cfg)
    embed = cfg.get("embed") or {}
    return OllamaEmbeddings(
        model=str(embed.get("model") or "nomic-embed-text:latest"),
        base_url=str(cfg.get("base_url") or DEFAULT_BASE_URL),
        client_kwargs=_client_timeout_kwargs(full_cfg),
    )


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Ollama health check for recruiter LLM stack"
    )
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = ap.parse_args()
    ok, msg = health_check(args.base_url)
    print(f"{'OK' if ok else 'FAIL'}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
