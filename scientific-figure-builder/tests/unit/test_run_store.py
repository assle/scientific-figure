from __future__ import annotations

import json
from pathlib import Path

import pytest

from figure_tools.provenance import hash_json
from figure_tools.run_store import (
    ArtifactCorruptError,
    ArtifactMissingError,
    RunStore,
)


FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_commit_validates_and_returns_canonical_reference(tmp_path):
    store = RunStore(tmp_path)
    brief = json.loads((FIXTURES / "figure_brief.json").read_text(encoding="utf-8"))

    reference = store.commit_json(
        "plans/figure_brief.json", brief, schema="figure-brief.schema.json"
    )

    path = tmp_path / "plans" / "figure_brief.json"
    assert reference == {
        "path": str(path),
        "exists": True,
        "content_hash": hash_json(brief),
    }
    assert store.hash_json(brief) == hash_json(brief)
    assert store.load_json(
        "plans/figure_brief.json", schema="figure-brief.schema.json"
    ) == brief


def test_schema_rejection_leaves_no_artifact_or_partial_file(tmp_path):
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match="invalid figure-brief.schema.json"):
        store.commit_json(
            "plans/figure_brief.json",
            {"schema_version": "1.0"},
            schema="figure-brief.schema.json",
        )

    assert not (tmp_path / "plans" / "figure_brief.json").exists()
    assert list(tmp_path.rglob("*.tmp-*")) == []


def test_atomic_replace_failure_preserves_existing_artifact_and_cleans_temporary_file(
    tmp_path, monkeypatch
):
    store = RunStore(tmp_path)
    store.commit_json("plans/value.json", {"revision": 1})
    original = (tmp_path / "plans" / "value.json").read_bytes()

    def fail_replace(*_args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("figure_tools.run_store.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        store.commit_json("plans/value.json", {"revision": 2})

    assert (tmp_path / "plans" / "value.json").read_bytes() == original
    assert list(tmp_path.rglob("*.tmp-*")) == []


def test_safe_load_distinguishes_missing_and_corrupt_artifacts(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(ArtifactMissingError):
        store.load_json("plans/missing.json")

    corrupt = tmp_path / "plans" / "corrupt.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactCorruptError, match="plans/corrupt.json"):
        store.load_json("plans/corrupt.json")


def test_optional_load_and_directory_reference_are_observable(tmp_path):
    store = RunStore(tmp_path)
    assert store.load_optional_json("plans/missing.json") is None
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "figure.svg").write_text("<svg/>", encoding="utf-8")

    reference = store.reference("exports")

    assert reference["exists"] is True
    assert reference["content_hash"].startswith("sha256:")
