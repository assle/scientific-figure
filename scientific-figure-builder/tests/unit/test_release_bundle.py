"""Complete Product bundle build and verification contract."""

from __future__ import annotations

from pathlib import Path
import tomllib

from figure_tools.release_bundle import (
    ProductBundleRequest,
    build_product_bundle,
    verify_product_bundle,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERSION = str(tomllib.loads(
    (REPOSITORY_ROOT / "scientific-figure-builder" / "pyproject.toml").read_text()
)["project"]["version"])


def test_product_bundle_binds_installer_plugin_and_core_artifact(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / f"scientific_figure_builder-{VERSION}-py3-none-any.whl"
    wheel.write_bytes(b"core-wheel")

    result = build_product_bundle(ProductBundleRequest(
        repository_root=REPOSITORY_ROOT,
        output_dir=tmp_path / "dist",
        product_version=VERSION,
        source_commit="abc123",
        core_wheel=wheel,
    ))
    manifest = verify_product_bundle(result.bundle, expected_version=VERSION)

    assert manifest.product_version == VERSION
    assert manifest.source_commit == "abc123"
    assert manifest.compatibility == {
        "artifact_schemas": "1.0",
        "phase_prompt": "1.0",
    }
    assert manifest.files["install.sh"].sha256
    assert manifest.files[
        "plugins/scientific-figure-builder/.codex-plugin/plugin.json"
    ].sha256
    assert manifest.files[
        f"artifacts/scientific_figure_builder-{VERSION}-py3-none-any.whl"
    ].sha256
    assert result.checksums.read_text(encoding="utf-8").endswith(
        f"  {result.bundle.name}\n"
    )
