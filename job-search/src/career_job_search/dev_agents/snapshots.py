"""Git snapshot, patch validation, and worktree cleanup for local agents."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

from career_job_search.dev_agents.architecture import validate_architectural_boundaries
from career_job_search.dev_agents.common import (
    TASK_ID_PATTERN,
    CoordinatorError,
    CoordinatorPaths,
    PatchInfo,
    SnapshotInfo,
    atomic_write_json,
    utc_now_iso,
)
from career_job_search.dev_agents.models import (
    AgentTaskSpec,
    LocalAgentSettings,
    normalise_relative_path,
)
from career_job_search.dev_agents.policy import (
    is_snapshot_forbidden,
    is_write_forbidden,
    path_is_allowed,
)
from career_job_search.dev_agents.runs import validate_task_id


def _git(
    args: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["GIT_OPTIONAL_LOCKS"] = "0"
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git", *args],  # noqa: S603, S607  # git is a known-safe tool
        cwd=cwd,
        env=merged_env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        message = (
            result.stderr.strip() or result.stdout.strip() or "Git command failed."
        )
        raise CoordinatorError(message)
    return result


def _git_bytes(args: Sequence[str], *, cwd: Path) -> bytes:
    result = subprocess.run(
        ["git", *args],  # noqa: S603, S607  # git is a known-safe tool
        cwd=cwd,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoordinatorError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or "Git command failed."
        )
    return result.stdout


def _zlist(value: bytes) -> list[str]:
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in value.split(b"\0")
        if item
    ]


def _snapshot_candidates(repo_root: Path) -> list[str]:
    tracked = _zlist(_git_bytes(["ls-files", "-z"], cwd=repo_root))
    untracked = _zlist(
        _git_bytes(["ls-files", "-z", "--others", "--exclude-standard"], cwd=repo_root)
    )
    return sorted(set(tracked + untracked))


def _validate_snapshot_files(
    candidates: Iterable[str],
    *,
    settings: LocalAgentSettings,
    repo_root: Path,
) -> tuple[list[str], int]:
    excluded: list[str] = []
    total_bytes = 0
    repo_resolved = repo_root.resolve()
    for raw_path in candidates:
        path = normalise_relative_path(raw_path)
        source = repo_root / path
        if is_snapshot_forbidden(path, settings):
            excluded.append(path)
            continue
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink():
            try:
                target = source.resolve(strict=True)
            except OSError as exc:
                raise CoordinatorError(f"Broken snapshot symlink: {path}") from exc
            if not target.is_relative_to(repo_resolved):
                raise CoordinatorError(
                    f"Snapshot symlink leaves the repository: {path}"
                )
            size = len(os.readlink(source).encode("utf-8"))
        elif source.is_file():
            size = source.stat().st_size
        else:
            raise CoordinatorError(f"Unsupported snapshot file type: {path}")
        if size > settings.snapshot.max_file_bytes:
            raise CoordinatorError(
                f"Snapshot file exceeds {settings.snapshot.max_file_bytes} bytes: {path}"
            )
        total_bytes += size
        if total_bytes > settings.snapshot.max_total_bytes:
            raise CoordinatorError(
                f"Snapshot exceeds {settings.snapshot.max_total_bytes} bytes."
            )
    return excluded, total_bytes


def _copy_snapshot_files(
    candidates: Iterable[str],
    *,
    excluded: Iterable[str],
    project_root: Path,
    worktree: Path,
) -> None:
    excluded_paths = set(excluded)
    for raw_path in candidates:
        path = normalise_relative_path(raw_path)
        if path in excluded_paths:
            continue
        source = project_root / path
        if not source.exists() and not source.is_symlink():
            continue
        destination = worktree / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, destination, follow_symlinks=False)


def _parse_tree_manifest(raw: bytes) -> dict[str, dict[str, str]]:
    manifest: dict[str, dict[str, str]] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        path = raw_path.decode("utf-8", errors="surrogateescape")
        manifest[path] = {"mode": mode, "type": kind, "object_id": object_id}
    return manifest


def _link_dependencies(worktree: Path, repo_root: Path) -> None:
    links = (
        (repo_root / ".venv", worktree / ".venv"),
        (
            repo_root / "dashboard" / "node_modules",
            worktree / "dashboard" / "node_modules",
        ),
    )
    for source, target in links:
        if not source.is_dir() or target.exists() or target.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)


def _isolate_worktree_git(worktree: Path) -> str:
    """Create a private one-commit repository for the project-only snapshot."""

    git_marker = worktree / ".git"
    if git_marker.exists():
        raise CoordinatorError("Snapshot destination already contains Git metadata.")
    _git(["init", "-q"], cwd=worktree)
    _git(["config", "user.name", "Career Local Agent"], cwd=worktree)
    _git(["config", "user.email", "local-agent@localhost"], cwd=worktree)
    _git(["add", "-A", "-f", "--", "."], cwd=worktree)
    commit_env = {
        "GIT_AUTHOR_DATE": utc_now_iso(),
        "GIT_COMMITTER_DATE": utc_now_iso(),
    }
    _git(
        [
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-q",
            "--no-gpg-sign",
            "-m",
            "Isolated local-agent snapshot",
        ],
        cwd=worktree,
        env=commit_env,
    )
    return _git(["rev-parse", "HEAD"], cwd=worktree).stdout.strip()


def create_snapshot(
    task_id: str,
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> SnapshotInfo:
    clean_id = validate_task_id(task_id)
    project_root = paths.repo_root.resolve()
    git_root = Path(paths.git_root).resolve()
    run_dir = paths.runtime_root / "runs" / clean_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if project_root != git_root and not project_root.is_relative_to(git_root):
        raise CoordinatorError("Project root must be inside the configured Git root.")
    if project_root != git_root and (project_root / ".git").exists():
        raise CoordinatorError(
            "Nested Git metadata is not allowed inside the configured project root."
        )
    discovered_git_root = _git(
        ["rev-parse", "--show-toplevel"], cwd=project_root, check=False
    ).stdout.strip()
    if not discovered_git_root or Path(discovered_git_root).resolve() != git_root:
        raise CoordinatorError(
            "The configured Git root does not own the project workspace."
        )

    before_status = _git_bytes(
        ["status", "--porcelain=v2", "-z"], cwd=project_root
    )
    before_head = _git(["rev-parse", "HEAD"], cwd=git_root).stdout.strip()
    before_branch = _git(
        ["symbolic-ref", "--short", "-q", "HEAD"], cwd=git_root, check=False
    ).stdout.strip()

    candidates = _snapshot_candidates(project_root)
    excluded, _ = _validate_snapshot_files(
        candidates, settings=settings, repo_root=project_root
    )

    paths.worktree_root.mkdir(parents=True, exist_ok=True)
    paths.worktree_root.chmod(0o700)
    worktree = paths.worktree_root / clean_id
    if worktree.exists():
        raise CoordinatorError(f"Local-agent worktree already exists: {worktree}")
    worktree.mkdir()
    try:
        _copy_snapshot_files(
            candidates,
            excluded=excluded,
            project_root=project_root,
            worktree=worktree,
        )
        isolated_commit = _isolate_worktree_git(worktree)
        tree = _git(
            ["rev-parse", "HEAD^{tree}"], cwd=worktree
        ).stdout.strip()
        manifest = _parse_tree_manifest(
            _git_bytes(
                ["ls-tree", "-r", "-z", "--full-tree", isolated_commit],
                cwd=worktree,
            )
        )
        _link_dependencies(worktree, project_root)
        manifest_path = run_dir / "snapshot-manifest.json"
        atomic_write_json(
            manifest_path,
            {
                "schema": "career_local_dev_snapshot_v1",
                "task_id": clean_id,
                "commit": isolated_commit,
                "isolated_commit": isolated_commit,
                "tree": tree,
                "head_parent": before_head,
                "branch": before_branch,
                "git_root": str(git_root),
                "project_root": str(project_root),
                "project_prefix": (
                    "."
                    if project_root == git_root
                    else project_root.relative_to(git_root).as_posix()
                ),
                "excluded_paths": excluded,
                "files": manifest,
            },
        )
    except Exception:
        shutil.rmtree(worktree, ignore_errors=True)
        raise

    after_status = _git_bytes(
        ["status", "--porcelain=v2", "-z"], cwd=project_root
    )
    after_head = _git(["rev-parse", "HEAD"], cwd=git_root).stdout.strip()
    after_branch = _git(
        ["symbolic-ref", "--short", "-q", "HEAD"], cwd=git_root, check=False
    ).stdout.strip()
    if (before_status, before_head, before_branch) != (
        after_status,
        after_head,
        after_branch,
    ):
        cleanup_worktree(worktree, paths=paths, force=True)
        raise CoordinatorError(
            "Snapshot creation changed the active branch, HEAD, or workspace status."
        )
    return SnapshotInfo(
        commit=isolated_commit,
        tree=tree,
        worktree=worktree,
        manifest_path=manifest_path,
        excluded_paths=tuple(excluded),
    )


def _validate_no_sensitive_artifacts(
    worktree: Path, *, settings: LocalAgentSettings
) -> None:
    exempt_links = {
        ".venv",
        "dashboard/node_modules",
    }
    for root, directories, files in os.walk(worktree, followlinks=False):
        root_path = Path(root)
        relative_root = root_path.relative_to(worktree).as_posix()
        kept: list[str] = []
        for directory in directories:
            if relative_root == "." and directory == ".git":
                continue
            relative = (
                Path(relative_root) / directory
                if relative_root != "."
                else Path(directory)
            ).as_posix()
            target = root_path / directory
            if relative in exempt_links and target.is_symlink():
                continue
            if directory in settings.snapshot.forbidden_parts:
                continue
            if is_snapshot_forbidden(relative, settings):
                raise CoordinatorError(
                    f"Agent created a protected artifact: {relative}"
                )
            kept.append(directory)
        directories[:] = kept
        for filename in files:
            if relative_root == "." and filename == ".git":
                continue
            relative = (
                Path(relative_root) / filename
                if relative_root != "."
                else Path(filename)
            ).as_posix()
            if is_snapshot_forbidden(relative, settings):
                raise CoordinatorError(
                    f"Agent created a protected artifact: {relative}"
                )


def _parse_name_status(raw: bytes) -> dict[str, str]:
    values = _zlist(raw)
    if len(values) % 2:
        raise CoordinatorError("Git returned malformed changed-file metadata.")
    return {values[index + 1]: values[index] for index in range(0, len(values), 2)}


def build_patch(
    task: AgentTaskSpec,
    snapshot: SnapshotInfo,
    *,
    settings: LocalAgentSettings,
    run_dir: Path,
) -> PatchInfo:
    _validate_no_sensitive_artifacts(snapshot.worktree, settings=settings)
    generated_exclusions = [
        path
        for path in _snapshot_candidates(snapshot.worktree)
        if is_snapshot_forbidden(path, settings)
    ]
    index_path = run_dir / "patch.index"
    index_path.unlink(missing_ok=True)
    index_env = {"GIT_INDEX_FILE": str(index_path)}
    patch_path = run_dir / "agent.patch"
    try:
        _git(["read-tree", "HEAD"], cwd=snapshot.worktree, env=index_env)
        _git(["add", "-A", "--", "."], cwd=snapshot.worktree, env=index_env)
        for path in generated_exclusions:
            _git(
                ["update-index", "--force-remove", "--", path],
                cwd=snapshot.worktree,
                env=index_env,
                check=False,
            )
        raw_status = subprocess.run(
            [  # noqa: S603, S607  # git is a known-safe tool
                "git",
                "diff",
                "--cached",
                "--name-status",
                "-z",
                "--no-renames",
                "HEAD",
            ],
            cwd=snapshot.worktree,
            env={**os.environ, **index_env, "GIT_OPTIONAL_LOCKS": "0"},
            capture_output=True,
            check=False,
        )
        if raw_status.returncode != 0:
            raise CoordinatorError(
                raw_status.stderr.decode("utf-8", errors="replace").strip()
                or "Could not inspect the local-agent patch."
            )
        statuses = _parse_name_status(raw_status.stdout)
        if not statuses:
            raise CoordinatorError("Implementer completed without changing any files.")
        if len(statuses) > min(
            task.max_changed_files, settings.limits.max_changed_files
        ):
            raise CoordinatorError(
                f"Patch changes {len(statuses)} files; the limit is {task.max_changed_files}."
            )
        for path, status in statuses.items():
            if status.startswith("D") or status.startswith("T"):
                raise CoordinatorError(
                    f"Local-agent patches may not delete, rename, or replace files: {path}"
                )
            if not path_is_allowed(path, task.allowed_paths):
                raise CoordinatorError(f"Patch changed an out-of-scope path: {path}")
            if is_snapshot_forbidden(path, settings) or is_write_forbidden(path):
                raise CoordinatorError(f"Patch changed a protected path: {path}")

        # Architectural boundary validation
        repo_root = snapshot.worktree
        arch_violations = validate_architectural_boundaries(statuses.keys(), repo_root)
        if arch_violations:
            raise CoordinatorError(
                "Patch violates architectural boundaries:\n" + "\n".join(arch_violations)
            )

        numstat = _git(
            ["diff", "--cached", "--numstat", "--no-renames", "HEAD"],
            cwd=snapshot.worktree,
            env=index_env,
        ).stdout
        diff_lines = 0
        for line in numstat.splitlines():
            added, removed, _ = line.split("\t", 2)
            if added == "-" or removed == "-":
                raise CoordinatorError(
                    "Binary changes are not allowed in local-agent patches."
                )
            diff_lines += int(added) + int(removed)
        if diff_lines > min(task.max_diff_lines, settings.limits.max_diff_lines):
            raise CoordinatorError(
                f"Patch changes {diff_lines} lines; the limit is {task.max_diff_lines}."
            )
        _git(
            [
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-renames",
                f"--output={patch_path}",
                "HEAD",
            ],
            cwd=snapshot.worktree,
            env=index_env,
        )
    finally:
        index_path.unlink(missing_ok=True)
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    return PatchInfo(
        path=patch_path,
        sha256=digest,
        changed_files=tuple(sorted(statuses)),
        statuses=statuses,
        diff_lines=diff_lines,
    )


def cleanup_worktree(
    worktree: Path, *, paths: CoordinatorPaths, force: bool = False
) -> None:
    try:
        resolved = worktree.resolve(strict=False)
        root = paths.worktree_root.resolve(strict=False)
    except OSError as exc:
        raise CoordinatorError(f"Cannot validate worktree path: {worktree}") from exc
    if resolved.parent != root or not TASK_ID_PATTERN.fullmatch(resolved.name):
        raise CoordinatorError("Refusing to remove an unregistered worktree path.")
    if not worktree.exists():
        return
    if (worktree / ".git").is_dir():
        if not force:
            raise CoordinatorError("Isolated worktree cleanup requires force=True.")
        shutil.rmtree(worktree)
        return
    if force and not (worktree / ".git").exists():
        shutil.rmtree(worktree)
        return
    args = ["-c", "core.hooksPath=/dev/null", "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree))
    result = _git(args, cwd=Path(paths.git_root), check=False)
    if result.returncode != 0 and worktree.exists():
        raise CoordinatorError(
            result.stderr.strip()
            or f"Could not remove local-agent worktree: {worktree}"
        )
