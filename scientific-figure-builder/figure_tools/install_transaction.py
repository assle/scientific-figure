"""Atomic, auditable filesystem transaction for install and upgrade."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from figure_tools.install_paths import DeliveryPaths


def _remove(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def install_lock_status(lock: Path) -> str:
    if not lock.is_dir():
        return "missing"
    try:
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        pid = int(owner["pid"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return "orphaned"
    return "active" if _process_alive(pid) else "orphaned"


@dataclass(frozen=True)
class Replacement:
    destination: Path
    backup: Path | None


class InstallTransaction:
    """Stage replacements, commit atomically, and roll back in reverse order."""

    def __init__(self, paths: DeliveryPaths) -> None:
        self.paths = paths
        self.transaction_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.staging_dir = paths.staging_parent / self.transaction_id
        self.backup_dir = paths.transaction_backup_parent / self.transaction_id
        self.replacements: list[Replacement] = []
        self.created_directories: list[Path] = []
        self.committed = False
        self.rolled_back: list[str] = []

    def __enter__(self) -> "InstallTransaction":
        self._acquire_lock()
        self._cleanup_orphans()
        self.staging_dir.mkdir(parents=True)
        self.backup_dir.mkdir(parents=True)
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        try:
            if exc is not None or not self.committed:
                self.rollback()
            self._write_log("committed" if self.committed and exc is None else "rolled_back")
        finally:
            _remove(self.staging_dir)
            _remove(self.backup_dir)
            self._release_lock()
        return False

    def stage_path(self, name: str) -> Path:
        path = self.staging_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def replace(self, staged: Path, destination: Path) -> None:
        if not staged.exists():
            raise RuntimeError(f"staged install payload is missing: {staged}")
        self._ensure_directory(destination.parent)
        backup = None
        if destination.exists():
            backup = self.backup_dir / f"{len(self.replacements):02d}-{destination.name}"
            destination.replace(backup)
        staged.replace(destination)
        self.replacements.append(Replacement(destination=destination, backup=backup))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        for replacement in reversed(self.replacements):
            _remove(replacement.destination)
            if replacement.backup is not None and replacement.backup.exists():
                replacement.destination.parent.mkdir(parents=True, exist_ok=True)
                replacement.backup.replace(replacement.destination)
            self.rolled_back.append(str(replacement.destination))
        for directory in reversed(self.created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        self.committed = False

    @property
    def committed_paths(self) -> list[str]:
        return [str(item.destination) for item in self.replacements]

    def _acquire_lock(self) -> None:
        lock = self.paths.install_lock_dir
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.mkdir()
        except FileExistsError:
            owner_file = lock / "owner.json"
            try:
                owner = json.loads(owner_file.read_text(encoding="utf-8"))
                owner_pid = int(owner["pid"])
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                owner_pid = -1
            if owner_pid > 0 and _process_alive(owner_pid):
                raise RuntimeError(
                    f"another install or upgrade owns this runtime scope: {lock}"
                )
            _remove(lock)
            lock.mkdir()
        (lock / "owner.json").write_text(
            json.dumps({"pid": os.getpid(), "transaction_id": self.transaction_id}) + "\n",
            encoding="utf-8",
        )

    def _ensure_directory(self, directory: Path) -> None:
        missing: list[Path] = []
        candidate = directory
        while not candidate.exists() and candidate != candidate.parent:
            missing.append(candidate)
            candidate = candidate.parent
        directory.mkdir(parents=True, exist_ok=True)
        self.created_directories.extend(reversed(missing))

    def _release_lock(self) -> None:
        _remove(self.paths.install_lock_dir)

    def _cleanup_orphans(self) -> None:
        for parent in (self.paths.staging_parent, self.paths.transaction_backup_parent):
            if not parent.is_dir():
                continue
            for child in parent.iterdir():
                _remove(child)

    def _write_log(self, status: str) -> None:
        self.paths.transaction_log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "transaction_id": self.transaction_id,
            "status": status,
            "scope": self.paths.scope_id,
            "version": self.paths.product_version,
            "committed_paths": self.committed_paths if status == "committed" else [],
            "rolled_back_paths": self.rolled_back,
        }
        log_path = self.paths.transaction_log_dir / f"{self.transaction_id}.json"
        log_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        logs = sorted(
            self.paths.transaction_log_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for expired in logs[20:]:
            _remove(expired)


def prune_runtime_versions(
    paths: DeliveryPaths,
    previous_runtime: Path | None,
) -> list[str]:
    """Keep the active runtime and at most one previously verified runtime."""

    runtime_root = paths.runtime_dir.parent
    if not runtime_root.is_dir():
        return []
    keep = {paths.runtime_dir.absolute()}
    if previous_runtime is not None and previous_runtime.is_dir():
        keep.add(previous_runtime.absolute())
    removed: list[str] = []
    for candidate in runtime_root.iterdir():
        if not candidate.is_dir() or candidate.absolute() in keep:
            continue
        _remove(candidate)
        removed.append(str(candidate))
    for candidate in runtime_root.glob("*.backup-*"):
        _remove(candidate)
        removed.append(str(candidate))
    return removed


__all__ = ["InstallTransaction", "install_lock_status", "prune_runtime_versions"]
