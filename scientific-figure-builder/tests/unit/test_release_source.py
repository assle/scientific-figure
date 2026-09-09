"""Resolve one immutable GitHub Release into a verified local Product bundle."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import pytest

from figure_tools.release_bundle import ProductBundleRequest, build_product_bundle
from figure_tools.release_source import (
    ReleaseAsset,
    ReleaseDescriptor,
    resolve_release_bundle,
)
from tests.support import write_core_wheel


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERSION = str(tomllib.loads(
    (REPOSITORY_ROOT / "scientific-figure-builder" / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"])


class ReleaseClient:
    def __init__(self, assets: dict[str, bytes]) -> None:
        self.assets = assets
        self.selectors: list[str] = []

    def describe(self, selector: str) -> ReleaseDescriptor:
        self.selectors.append(selector)
        return ReleaseDescriptor(
            tag_name=f"v{VERSION}",
            source_commit="abc123",
            assets=tuple(
                ReleaseAsset(name=name, url=f"memory://{name}")
                for name in self.assets
            ),
        )

    def download(self, asset: ReleaseAsset, destination: Path) -> None:
        destination.write_bytes(self.assets[asset.name])


def test_latest_is_resolved_once_and_bundle_checksum_is_verified(tmp_path: Path) -> None:
    wheel = write_core_wheel(
        tmp_path / f"scientific_figure_builder-{VERSION}-py3-none-any.whl",
        VERSION,
    )
    built = build_product_bundle(ProductBundleRequest(
        repository_root=REPOSITORY_ROOT,
        output_dir=tmp_path / "built",
        product_version=VERSION,
        source_commit="abc123",
        core_wheel=wheel,
    ))
    bundle_bytes = built.bundle.read_bytes()
    assets = {
        built.bundle.name: bundle_bytes,
        "SHA256SUMS": (
            f"{hashlib.sha256(bundle_bytes).hexdigest()}  {built.bundle.name}\n"
        ).encode(),
    }
    client = ReleaseClient(assets)

    resolved = resolve_release_bundle(
        "latest", cache_dir=tmp_path / "cache", client=client,
    )

    assert resolved.version == VERSION
    assert resolved.bundle.read_bytes() == bundle_bytes
    assert client.selectors == ["latest"]


def test_checksum_failure_removes_downloaded_release_cache(tmp_path: Path) -> None:
    assets = {
        f"scientific-figure-builder-{VERSION}.tar.gz": b"corrupt",
        "SHA256SUMS": (
            "0" * 64 + f"  scientific-figure-builder-{VERSION}.tar.gz\n"
        ).encode(),
    }

    with pytest.raises(ValueError, match="checksum mismatch"):
        resolve_release_bundle(
            "latest",
            cache_dir=tmp_path / "cache",
            client=ReleaseClient(assets),
        )

    assert not (tmp_path / "cache" / VERSION).exists()


def test_release_source_rejects_non_semver_tag_before_using_it_as_a_path(
    tmp_path: Path,
) -> None:
    class UnsafeClient(ReleaseClient):
        def describe(self, selector: str) -> ReleaseDescriptor:
            del selector
            return ReleaseDescriptor(
                tag_name="v../../escape", source_commit="abc123", assets=(),
            )

    with pytest.raises(RuntimeError, match="invalid Product tag"):
        resolve_release_bundle(
            "latest", cache_dir=tmp_path / "cache", client=UnsafeClient({}),
        )

    assert not (tmp_path / "escape").exists()
