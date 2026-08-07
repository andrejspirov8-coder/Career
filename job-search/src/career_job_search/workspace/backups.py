"""Encrypted backup creation, validation, and restoration."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import struct
import tarfile
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from career_job_search.core.paths import project_path
from career_job_search.core.time import utc_now_iso

JOB_ROOT = project_path()
BACKUP_DIR = project_path("state", "backups")
BACKUP_FILENAME_PATTERN = re.compile(
    r"^career-(?:backup|pre-restore)-\d{8}T\d{6}Z(?:-[a-f0-9]{6})?\.career-backup$"
)
BACKUP_MAGIC = b"CAREER_BACKUP_V1\n"
BACKUP_SCHEMA = "career_encrypted_backup_v1"
MAX_BACKUP_BYTES = 300 * 1024 * 1024
MAX_BACKUP_FILES = 5_000
MIN_PASSPHRASE_LENGTH = 12
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


def _allowed_backup_path(relative_path: PurePosixPath) -> bool:
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return False
    parts = relative_path.parts
    if not parts or any(part.startswith(".") for part in parts):
        return False
    suffix = relative_path.suffix.lower()
    if parts[0] == "state":
        if relative_path.as_posix() in {
            "state/dashboard_service.json",
            "state/dashboard_restart.request.json",
        }:
            return False
        return (
            len(parts) > 1
            and parts[1] != "backups"
            and suffix
            in {
                ".sqlite3",
                ".sqlite",
                ".db",
                ".json",
                ".jsonl",
                ".log",
                ".csv",
                ".yaml",
                ".yml",
            }
        )
    if parts[0] == "pipeline":
        return suffix in {".json", ".jsonl", ".csv", ".log", ".md", ".sqlite", ".db"}
    if parts[0] == "packs":
        return suffix in {".json", ".md", ".txt"}
    if parts[0] == "output":
        return suffix in {".pdf", ".txt"}
    if parts[0] == "config":
        return suffix in {".yaml", ".yml"}
    if parts[0] == "cv":
        return suffix in {".yaml", ".yml", ".md", ".png", ".jpg", ".jpeg"}
    return relative_path.as_posix() == "linkedin/config.yaml"


def _backup_source_files(
    job_root: Path = JOB_ROOT,
) -> list[tuple[Path, PurePosixPath]]:
    roots = ["state", "pipeline", "packs", "output", "config", "cv", "linkedin"]
    files: list[tuple[Path, PurePosixPath]] = []
    for root_name in roots:
        root = job_root / root_name
        if not root.exists():
            continue
        for source in sorted(root.rglob("*")):
            if source.is_symlink() or not source.is_file():
                continue
            relative = PurePosixPath(source.relative_to(job_root).as_posix())
            if _allowed_backup_path(relative):
                files.append((source, relative))
    if len(files) > MAX_BACKUP_FILES:
        raise RuntimeError("The workspace contains too many files for one safe backup.")
    return files


def _copy_sqlite(source: Path, destination: Path) -> None:
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_db:
        with sqlite3.connect(destination) as destination_db:
            source_db.backup(destination_db)


def _copy_backup_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in {".sqlite3", ".sqlite", ".db"}:
        _copy_sqlite(source, destination)
        destination.chmod(0o600)
        return
    shutil.copy2(source, destination, follow_symlinks=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_passphrase(value: Any) -> str:
    if not isinstance(value, str) or len(value) < MIN_PASSPHRASE_LENGTH:
        raise ValueError(
            f"Backup passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters."
        )
    if len(value) > 256:
        raise ValueError("Backup passphrase is too long.")
    return value


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
        passphrase.encode("utf-8")
    )


def _write_encrypted_backup(
    archive_path: Path, output_path: Path, passphrase: str
) -> None:
    archive_size = archive_path.stat().st_size
    if archive_size > MAX_BACKUP_BYTES:
        raise RuntimeError(
            "The workspace backup is larger than the 300 MB safety limit."
        )
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    header = {
        "schema": BACKUP_SCHEMA,
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "cipher": "aes-256-gcm",
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    ciphertext = AESGCM(_derive_key(passphrase, salt)).encrypt(
        nonce, archive_path.read_bytes(), header_bytes
    )
    temporary = output_path.with_name(f".{output_path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(BACKUP_MAGIC)
            handle.write(struct.pack(">I", len(header_bytes)))
            handle.write(header_bytes)
            handle.write(ciphertext)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, output_path)
        output_path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def create_backup(
    passphrase: str,
    *,
    pre_restore: bool = False,
    job_root: Path = JOB_ROOT,
    backup_dir: Path = BACKUP_DIR,
) -> dict[str, Any]:
    clean_passphrase = _validate_passphrase(passphrase)
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    kind = "pre-restore" if pre_restore else "backup"
    filename = f"career-{kind}-{timestamp}-{secrets.token_hex(3)}.career-backup"
    output_path = backup_dir / filename
    with tempfile.TemporaryDirectory(prefix="career-backup-") as temporary:
        temp_root = Path(temporary)
        payload_root = temp_root / "payload"
        manifest_files: list[dict[str, Any]] = []
        total_size = 0
        for source, relative in _backup_source_files(job_root):
            destination = payload_root.joinpath(*relative.parts)
            _copy_backup_source(source, destination)
            size = destination.stat().st_size
            total_size += size
            if total_size > MAX_BACKUP_BYTES:
                raise RuntimeError(
                    "The workspace is larger than the 300 MB safety limit."
                )
            manifest_files.append(
                {
                    "path": relative.as_posix(),
                    "size": size,
                    "sha256": _sha256(destination),
                }
            )
        manifest = {
            "schema": BACKUP_SCHEMA,
            "created_at": utc_now_iso(),
            "file_count": len(manifest_files),
            "total_bytes": total_size,
            "files": manifest_files,
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        archive_path = temp_root / "backup.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(temp_root / "manifest.json", arcname="manifest.json")
            if payload_root.exists():
                archive.add(payload_root, arcname="payload", recursive=True)
        _write_encrypted_backup(archive_path, output_path, clean_passphrase)
    return {
        "filename": filename,
        "created_at": manifest["created_at"],
        "file_count": manifest["file_count"],
        "data_bytes": manifest["total_bytes"],
        "encrypted_bytes": output_path.stat().st_size,
    }


def _safe_backup_path(filename: str, backup_dir: Path = BACKUP_DIR) -> Path:
    if not isinstance(filename, str) or not BACKUP_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("Choose a valid Career backup file.")
    path = backup_dir / filename
    try:
        resolved = path.resolve(strict=True)
        root = backup_dir.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("The selected backup no longer exists.") from exc
    if resolved.parent != root or not resolved.is_file():
        raise ValueError("Choose a valid Career backup file.")
    if resolved.stat().st_size > MAX_BACKUP_BYTES + 1024 * 1024:
        raise ValueError("The selected backup exceeds the safety limit.")
    return resolved


def list_backups(backup_dir: Path = BACKUP_DIR) -> list[dict[str, Any]]:
    if not backup_dir.exists():
        return []
    backups: list[dict[str, Any]] = []
    for path in backup_dir.iterdir():
        if not path.is_file() or not BACKUP_FILENAME_PATTERN.fullmatch(path.name):
            continue
        stat = path.stat()
        backups.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, UTC)
                .replace(microsecond=0)
                .isoformat(),
                "pre_restore": path.name.startswith("career-pre-restore-"),
            }
        )
    return sorted(backups, key=lambda row: str(row["created_at"]), reverse=True)[:20]


def _decrypt_backup(path: Path, passphrase: str, output_path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    if not content.startswith(BACKUP_MAGIC):
        raise ValueError("This is not a supported Career backup.")
    offset = len(BACKUP_MAGIC)
    if len(content) < offset + 4:
        raise ValueError("The backup header is incomplete.")
    header_length = struct.unpack(">I", content[offset : offset + 4])[0]
    offset += 4
    if (
        header_length < 20
        or header_length > 4096
        or len(content) <= offset + header_length
    ):
        raise ValueError("The backup header is invalid.")
    header_bytes = content[offset : offset + header_length]
    try:
        header = json.loads(header_bytes)
        if (
            header.get("schema") != BACKUP_SCHEMA
            or header.get("kdf") != "scrypt"
            or header.get("cipher") != "aes-256-gcm"
            or header.get("n") != SCRYPT_N
            or header.get("r") != SCRYPT_R
            or header.get("p") != SCRYPT_P
        ):
            raise ValueError
        salt = base64.b64decode(header["salt"], validate=True)
        nonce = base64.b64decode(header["nonce"], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("The backup encryption settings are invalid.") from exc
    try:
        plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(
            nonce, content[offset + header_length :], header_bytes
        )
    except Exception as exc:
        raise ValueError(
            "The backup passphrase is wrong or the file is damaged."
        ) from exc
    if len(plaintext) > MAX_BACKUP_BYTES:
        raise ValueError("The decrypted backup exceeds the safety limit.")
    output_path.write_bytes(plaintext)
    output_path.chmod(0o600)
    return header


def _extract_and_validate_archive(
    archive_path: Path, destination: Path
) -> dict[str, Any]:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > MAX_BACKUP_FILES + 20:
            raise ValueError("The backup contains too many files.")
        total = 0
        member_names: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("The backup contains an unsafe path.")
            normalized_name = path.as_posix().rstrip("/")
            if normalized_name in member_names:
                raise ValueError("The backup contains a duplicate path.")
            member_names.add(normalized_name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("The backup contains an unsupported file type.")
            if normalized_name not in {"manifest.json", "payload"}:
                if not path.parts or path.parts[0] != "payload" or len(path.parts) < 2:
                    raise ValueError("The backup contains an unexpected file.")
                relative = PurePosixPath(*path.parts[1:])
                if member.isfile() and not _allowed_backup_path(relative):
                    raise ValueError("The backup contains an unexpected data path.")
            total += max(0, member.size)
            if total > MAX_BACKUP_BYTES:
                raise ValueError("The backup expands beyond the safety limit.")
            if member.isdir():
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("A backup file could not be read.")
            with source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle, length=1024 * 1024)

    manifest_path = destination / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("The backup manifest is missing or invalid.") from exc
    files = manifest.get("files")
    if manifest.get("schema") != BACKUP_SCHEMA or not isinstance(files, list):
        raise ValueError("The backup manifest is not supported.")
    if manifest.get("file_count") != len(files) or len(files) > MAX_BACKUP_FILES:
        raise ValueError("The backup manifest file count is invalid.")
    seen: set[str] = set()
    total_size = 0
    for row in files:
        if not isinstance(row, dict):
            raise ValueError("The backup manifest contains an invalid entry.")
        relative = PurePosixPath(str(row.get("path") or ""))
        relative_text = relative.as_posix()
        if not _allowed_backup_path(relative) or relative_text in seen:
            raise ValueError("The backup manifest contains an unsafe data path.")
        seen.add(relative_text)
        source = destination / "payload" / Path(*relative.parts)
        if not source.is_file() or source.is_symlink():
            raise ValueError("A file listed in the backup is missing.")
        size = source.stat().st_size
        if size != row.get("size") or _sha256(source) != row.get("sha256"):
            raise ValueError("A file in the backup failed its integrity check.")
        total_size += size
    if total_size != manifest.get("total_bytes"):
        raise ValueError("The backup size does not match its manifest.")
    actual_files = {
        path.relative_to(destination / "payload").as_posix()
        for path in (destination / "payload").rglob("*")
        if path.is_file()
    }
    if actual_files != seen:
        raise ValueError("The backup contains files not listed in its manifest.")
    return manifest


def validate_backup(
    filename: str,
    passphrase: str,
    *,
    backup_dir: Path = BACKUP_DIR,
) -> dict[str, Any]:
    path = _safe_backup_path(filename, backup_dir)
    clean_passphrase = _validate_passphrase(passphrase)
    with tempfile.TemporaryDirectory(prefix="career-restore-check-") as temporary:
        root = Path(temporary)
        archive = root / "backup.tar.gz"
        _decrypt_backup(path, clean_passphrase, archive)
        manifest = _extract_and_validate_archive(archive, root / "verified")
    return {
        "filename": filename,
        "valid": True,
        "created_at": manifest["created_at"],
        "file_count": manifest["file_count"],
        "data_bytes": manifest["total_bytes"],
    }


def _worker_online(job_root: Path = JOB_ROOT) -> bool:
    database = job_root / "state" / "automation.sqlite3"
    if not database.exists():
        return False
    try:
        with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as con:
            row = con.execute(
                "SELECT status, heartbeat_at FROM automation_workers ORDER BY heartbeat_at DESC LIMIT 1"
            ).fetchone()
        if not row or row[0] != "running":
            return False
        heartbeat = datetime.fromisoformat(str(row[1]))
        age = (datetime.now(UTC) - heartbeat).total_seconds()
        return 0 <= age <= 60
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return False


def restore_backup(
    filename: str,
    passphrase: str,
    confirmation: str,
    *,
    job_root: Path = JOB_ROOT,
    backup_dir: Path = BACKUP_DIR,
    worker_online_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if confirmation != "RESTORE":
        raise ValueError("Type RESTORE exactly to confirm this recovery action.")
    if (worker_online_check or (lambda: _worker_online(job_root)))():
        raise RuntimeError(
            "Stop the dashboard automation worker before restoring private data."
        )
    path = _safe_backup_path(filename, backup_dir)
    clean_passphrase = _validate_passphrase(passphrase)
    with tempfile.TemporaryDirectory(prefix="career-restore-") as temporary:
        root = Path(temporary)
        archive = root / "backup.tar.gz"
        _decrypt_backup(path, clean_passphrase, archive)
        extracted = root / "verified"
        manifest = _extract_and_validate_archive(archive, extracted)
        safety = create_backup(
            clean_passphrase,
            pre_restore=True,
            job_root=job_root,
            backup_dir=backup_dir,
        )
        restored = 0
        for row in manifest["files"]:
            relative = PurePosixPath(row["path"])
            source = extracted / "payload" / Path(*relative.parts)
            destination = job_root / Path(*relative.parts)
            # Harden: reject symlinked destination or symlinked parent dirs
            # to prevent TOCTOU symlink-swap attacks between validation and replace.
            if destination.is_symlink():
                raise RuntimeError(
                    f"Refusing to restore over a symlinked destination: {destination}"
                )
            parent = destination.parent
            while parent != job_root.parent and str(parent) != str(job_root):
                if parent.is_symlink():
                    raise RuntimeError(
                        f"Refusing to restore under a symlinked parent directory: {parent}"
                    )
                parent = parent.parent
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary_destination = destination.with_name(
                f".{destination.name}.{secrets.token_hex(4)}.restore"
            )
            shutil.copy2(source, temporary_destination, follow_symlinks=False)
            temporary_destination.chmod(0o600)
            os.replace(temporary_destination, destination)
            if destination.suffix.lower() in {".sqlite3", ".sqlite", ".db"}:
                Path(f"{destination}-wal").unlink(missing_ok=True)
                Path(f"{destination}-shm").unlink(missing_ok=True)
            restored += 1
    return {
        "filename": filename,
        "restored_files": restored,
        "safety_backup": safety["filename"],
        "mode": "overlay",
    }
