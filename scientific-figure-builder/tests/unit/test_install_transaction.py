"""Atomic install transaction, locking, logging, and retention."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from figure_tools.install_transaction import (
    InstallTransaction,
    install_lock_status,
    prune_runtime_versions,
)
from install.install_delivery import delivery_paths


def _paths(tmp_path: Path, version: str = "0.2.0"):
    return delivery_paths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        cache_home=tmp_path / "cache",
        session_home=tmp_path / "session",
        install_home=tmp_path / "install",
        codex_home=tmp_path / "codex",
        bin_dir=tmp_path / "bin",
        product_version=version,
    )


def test_transaction_rolls_back_replacements_in_reverse(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    destination = tmp_path / "destination.txt"
    destination.write_text("before", encoding="utf-8")

    with pytest.raises(RuntimeError, match="injected"):
        with InstallTransaction(paths) as transaction:
            staged = transaction.stage_path("candidate.txt")
            staged.write_text("after", encoding="utf-8")
            transaction.replace(staged, destination)
            raise RuntimeError("injected")

    assert destination.read_text(encoding="utf-8") == "before"
    log = json.loads(next(paths.transaction_log_dir.glob("*.json")).read_text())
    assert log["status"] == "rolled_back"
    assert log["rolled_back_paths"] == [str(destination)]
    assert install_lock_status(paths.install_lock_dir) == "missing"


def test_transaction_commit_keeps_candidate_and_cleans_internal_backups(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    destination = tmp_path / "destination.txt"
    destination.write_text("before", encoding="utf-8")
    with InstallTransaction(paths) as transaction:
        staged = transaction.stage_path("candidate.txt")
        staged.write_text("after", encoding="utf-8")
        transaction.replace(staged, destination)
        transaction.commit()
    assert destination.read_text(encoding="utf-8") == "after"
    assert not list(paths.staging_parent.glob("*"))
    assert not list(paths.transaction_backup_parent.glob("*"))


def test_concurrent_transaction_is_rejected(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with InstallTransaction(paths) as first:
        with pytest.raises(RuntimeError, match="another install or upgrade"):
            with InstallTransaction(paths):
                pass
        first.commit()


def test_orphaned_lock_and_staging_are_recovered(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.install_lock_dir.mkdir(parents=True)
    (paths.install_lock_dir / "owner.json").write_text(
        json.dumps({"pid": 999999999}), encoding="utf-8"
    )
    orphan_stage = paths.staging_parent / "orphan"
    orphan_backup = paths.transaction_backup_parent / "orphan"
    orphan_stage.mkdir(parents=True)
    orphan_backup.mkdir(parents=True)
    assert install_lock_status(paths.install_lock_dir) == "orphaned"

    with InstallTransaction(paths) as transaction:
        assert not orphan_stage.exists()
        assert not orphan_backup.exists()
        transaction.commit()


def test_runtime_retention_keeps_current_and_one_previous(tmp_path: Path) -> None:
    current = _paths(tmp_path, "0.3.0")
    previous = _paths(tmp_path, "0.2.0")
    expired = _paths(tmp_path, "0.1.0")
    for paths in (current, previous, expired):
        paths.runtime_dir.mkdir(parents=True)
    removed = prune_runtime_versions(current, previous.runtime_dir)
    assert current.runtime_dir.is_dir()
    assert previous.runtime_dir.is_dir()
    assert not expired.runtime_dir.exists()
    assert str(expired.runtime_dir) in removed


def test_transaction_log_retention_is_bounded(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for _ in range(22):
        with InstallTransaction(paths) as transaction:
            transaction.commit()
    assert len(list(paths.transaction_log_dir.glob("*.json"))) == 20
