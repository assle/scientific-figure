"""Schema-validation tests for Phase 1 exit criteria.

Exit criteria (plan section 15, Phase 1):
- Every example core document validates against its schema.
- No model calls exist yet (these tests are purely local).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
TEMPLATE_DIR = ROOT / "templates"

DRAFT = "https://json-schema.org/draft/2020-12/schema"

# schema file -> list of documents (fixtures or templates) that must validate.
SCHEMA_DOCUMENTS = {
    "figure-plan.schema.json": ["figure_plan.json"],
    "plot-spec.schema.json": ["plot_spec.json"],
    "asset-manifest.schema.json": ["asset_manifest.json"],
    "style-bible.schema.json": ["style_bible.json", "default-style-bible.json"],
    "run-state.schema.json": ["run_state.json"],
    "validation-report.schema.json": ["validation_report.json"],
    "layout-analysis.schema.json": ["layout_analysis.json"],
    "root-cause-report.schema.json": ["root_cause_report.json"],
}

EXPECTED_SCHEMAS = sorted(SCHEMA_DOCUMENTS.keys())


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _doc_path(name: str) -> Path:
    fixture = FIXTURE_DIR / name
    if fixture.exists():
        return fixture
    template = TEMPLATE_DIR / name
    if template.exists():
        return template
    raise FileNotFoundError(f"document not found: {name}")


@pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
def test_schema_file_exists(schema_name: str) -> None:
    assert (SCHEMA_DIR / schema_name).is_file(), f"missing schema: {schema_name}"


@pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = _load_json(SCHEMA_DIR / schema_name)
    assert schema.get("$schema") == DRAFT, f"{schema_name} must declare Draft 2020-12"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
def test_schema_requires_version_1_0(schema_name: str) -> None:
    schema = _load_json(SCHEMA_DIR / schema_name)
    props = schema.get("properties", {})
    assert "schema_version" in props, f"{schema_name} must define schema_version"
    sv = props["schema_version"]
    assert sv.get("const") == "1.0", f"{schema_name} schema_version must be const 1.0"
    assert "schema_version" in schema.get("required", []), (
        f"{schema_name} must require schema_version"
    )


@pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
def test_every_schema_has_a_validating_document(schema_name: str) -> None:
    documents = SCHEMA_DOCUMENTS[schema_name]
    assert documents, f"{schema_name} has no example documents"
    schema = _load_json(SCHEMA_DIR / schema_name)
    validator = Draft202012Validator(schema)
    for doc_name in documents:
        doc = _load_json(_doc_path(doc_name))
        errors = sorted(validator.iter_errors(doc), key=lambda e: e.path)
        assert not errors, (
            f"{doc_name} failed {schema_name}: "
            + "; ".join(e.message for e in errors)
        )


def test_default_project_yaml_is_valid_and_non_secret() -> None:
    project_yaml = TEMPLATE_DIR / "default-project.yaml"
    assert project_yaml.is_file(), "default-project.yaml template missing"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # Must contain the four model roles from plan section 5.
    models = data.get("models", {})
    for role in ("image_generate", "image_edit", "vision_analyze", "vision_validate"):
        assert role in models, f"default-project.yaml missing model role {role}"

    # Project config must contain no secrets (plan section 5). Comments are not
    # parsed YAML, so explanatory mentions of ARK_API_KEY are allowed; actual
    # secret-bearing keys or credential-like values are not.
    secret_key_re = re.compile(r"(api_?key|secret|token|password|credential)", re.I)
    cred_value_re = re.compile(r"^(sk-|AKIA|Bearer\s)", re.I)

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert not secret_key_re.search(str(k)), f"secret-like key: {k}"
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, str):
            assert not cred_value_re.match(obj), f"credential-like value: {obj}"

    walk(data)


def test_publication_mplstyle_exists() -> None:
    assert (TEMPLATE_DIR / "publication.mplstyle").is_file()


def test_network_only_via_transport_abstraction() -> None:
    """All network I/O is confined to the ark/ subpackage (the transport seam).
    No direct HTTP/network call sites exist elsewhere in figure_tools."""
    forbidden_patterns = [
        r"volcengine",
        r"ark\.cn-",
        r"requests\.(get|post)",
        r"httpx\.(get|post|Client)",
        r"urllib\.request",
    ]
    offenders = []
    for py in (ROOT / "figure_tools").rglob("*.py"):
        if "ark" in py.relative_to(ROOT).parts:  # ark/ is the network boundary
            continue
        text = py.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            if re.search(pat, text, re.IGNORECASE):
                offenders.append(f"{py.relative_to(ROOT)} matches {pat}")
    assert not offenders, "direct network call site outside ark/: " + ", ".join(offenders)
