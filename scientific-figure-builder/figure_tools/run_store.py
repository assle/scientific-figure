"""Schema-governed persistence for one scientific-figure run directory."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from figure_tools._resources import schema_path
from figure_tools.provenance import hash_file, hash_json


RUN_SUBDIRECTORIES = (
    "inputs",
    "plans",
    "prompts",
    "assets",
    "plots",
    "vectors",
    "validation",
    "exports",
)

PHASES = ("intake", "planning", "execution", "review_and_repair", "export")


class RunStoreError(RuntimeError):
    """Base class for observable Run Store failures."""


class ArtifactMissingError(RunStoreError):
    """The requested run artifact does not exist."""


class ArtifactCorruptError(RunStoreError):
    """The requested run artifact cannot be decoded or validated."""


@lru_cache(maxsize=1)
def schema_registry() -> Registry:
    registry = Registry()
    for path in schema_path("run-state.schema.json").parent.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        identifier = contents.get("$id")
        if identifier:
            registry = registry.with_resource(
                str(identifier), Resource.from_contents(contents),
            )
    return registry


def schema_error_detail(
    value: Mapping[str, Any], contract: Mapping[str, Any],
) -> str | None:
    """Return one stable validation detail shared by artifact-owning modules."""

    errors = sorted(
        Draft202012Validator(
            contract, registry=schema_registry(),
        ).iter_errors(dict(value)),
        key=lambda error: list(error.path),
    )
    return "; ".join(error.message for error in errors) if errors else None


class RunStore:
    """Own run paths, atomic JSON commits, validation, hashes, and references."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)

    def ensure_structure(self) -> Path:
        for name in RUN_SUBDIRECTORIES:
            (self.run_dir / name).mkdir(parents=True, exist_ok=True)
        return self.run_dir

    def path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("run artifact paths must stay inside the run directory")
        return self.run_dir / relative

    def current_phase(self) -> str:
        """Read the Lifecycle phase this run is in.

        A run that has not persisted a valid phase is reported as the phase it
        is about to enter: Planning once the Figure brief exists, otherwise
        Intake. ``RunState`` writes ``"init"`` before any phase is marked and
        ``run-state.schema.json`` accepts any non-empty string, so an
        unrecognized value means "not started" rather than a phase.
        """
        state = self.load_optional_json("run_state.json") or {}
        phase = state.get("current_phase")
        if phase in PHASES:
            return str(phase)
        return "planning" if self.path("plans/figure_brief.json").is_file() else "intake"

    @staticmethod
    def hash_json(value: Any) -> str:
        return hash_json(value)

    def commit_json(
        self,
        relative_path: str | Path,
        value: Mapping[str, Any],
        *,
        schema: str | None = None,
    ) -> dict[str, Any]:
        data = dict(value)
        if schema is not None:
            self._validate(data, schema)
        path = self.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            temporary.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.reference(relative_path)

    def commit_text(self, relative_path: str | Path, value: str) -> dict[str, Any]:
        path = self.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            temporary.write_text(value, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.reference(relative_path)

    def delete(self, relative_path: str | Path) -> None:
        path = self.path(relative_path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def claim(self, relative_path: str | Path, owner: str) -> None:
        """Atomically claim one run-owned lock path for an operation owner."""

        path = self.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RunStoreError(f"run claim already exists: {relative_path}") from exc
        try:
            os.write(descriptor, owner.encode("utf-8"))
        finally:
            os.close(descriptor)

    def release_claim(self, relative_path: str | Path, owner: str) -> bool:
        """Release a run-owned claim only when its owner still matches."""

        path = self.path(relative_path)
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        if current != owner:
            return False
        path.unlink(missing_ok=True)
        return True

    def validate(self, value: Mapping[str, Any], schema: str) -> None:
        self._validate(value, schema)

    def load_json(
        self,
        relative_path: str | Path,
        *,
        schema: str | None = None,
    ) -> dict[str, Any]:
        path = self.path(relative_path)
        if not path.is_file():
            raise ArtifactMissingError(f"run artifact is missing: {relative_path}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptError(
                f"run artifact is corrupt: {relative_path}"
            ) from exc
        if not isinstance(value, dict):
            raise ArtifactCorruptError(
                f"run artifact must be a JSON object: {relative_path}"
            )
        if schema is not None:
            try:
                self._validate(value, schema)
            except ValueError as exc:
                raise ArtifactCorruptError(
                    f"run artifact is corrupt: {relative_path}: {exc}"
                ) from exc
        return value

    def load_optional_json(
        self,
        relative_path: str | Path,
        *,
        schema: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.path(relative_path).is_file():
            return None
        return self.load_json(relative_path, schema=schema)

    def reference(self, relative_path: str | Path) -> dict[str, Any]:
        path = self.path(relative_path)
        content_hash: str | None = None
        if path.is_file():
            if path.suffix == ".json":
                try:
                    content_hash = hash_json(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (OSError, UnicodeError, json.JSONDecodeError):
                    content_hash = hash_file(path)
            else:
                content_hash = hash_file(path)
        elif path.is_dir():
            contents = {
                str(child.relative_to(self.run_dir)): self._path_hash(child)
                for child in sorted(path.rglob("*"))
                if child.is_file()
            }
            content_hash = hash_json(contents)
        return {
            "path": str(path),
            "exists": path.exists(),
            "content_hash": content_hash,
        }

    def reference_matches(
        self,
        reference: Any,
        relative_path: str | Path,
    ) -> bool:
        if not isinstance(reference, Mapping):
            return False
        current = self.reference(relative_path)
        return (
            current["exists"] is True
            and reference.get("exists", True) is True
            and reference.get("content_hash") == current["content_hash"]
        )

    @staticmethod
    def _path_hash(path: Path) -> str:
        if path.suffix == ".json":
            try:
                return hash_json(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        return hash_file(path)

    @staticmethod
    def _validate(value: Mapping[str, Any], schema: str) -> None:
        contract = json.loads(schema_path(schema).read_text(encoding="utf-8"))
        detail = schema_error_detail(value, contract)
        if detail:
            raise ValueError(f"invalid {schema}: {detail}")


__all__ = [
    "ArtifactCorruptError",
    "ArtifactMissingError",
    "RUN_SUBDIRECTORIES",
    "RunStore",
    "RunStoreError",
    "schema_error_detail",
    "schema_registry",
]
