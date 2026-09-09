"""Resolve a GitHub Release to one verified, pinned Product bundle."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from figure_tools.release_bundle import (
    PRODUCT_VERSION_PATTERN,
    verify_detached_checksum,
    verify_product_bundle,
)


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str


@dataclass(frozen=True)
class ReleaseDescriptor:
    tag_name: str
    source_commit: str
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class ResolvedRelease:
    version: str
    bundle: Path


class ReleaseClient(Protocol):
    def describe(self, selector: str) -> ReleaseDescriptor: ...

    def download(self, asset: ReleaseAsset, destination: Path) -> None: ...


def resolve_release_bundle(
    selector: str,
    *,
    cache_dir: Path,
    client: ReleaseClient | None = None,
) -> ResolvedRelease:
    """Resolve latest once, download its assets, and verify the exact bundle."""

    if client is None:
        from figure_tools.providers.github_releases import GitHubReleaseClient

        selected_client: ReleaseClient = GitHubReleaseClient()
    else:
        selected_client = client
    release = selected_client.describe(selector)
    if not release.tag_name.startswith("v") or len(release.tag_name) == 1:
        raise RuntimeError("GitHub Release has an invalid Product tag")
    version = release.tag_name[1:]
    if PRODUCT_VERSION_PATTERN.fullmatch(version) is None:
        raise RuntimeError("GitHub Release has an invalid Product tag")
    bundle_name = f"scientific-figure-builder-{version}.tar.gz"
    assets = {asset.name: asset for asset in release.assets}
    try:
        bundle_asset = assets[bundle_name]
        checksums_asset = assets["SHA256SUMS"]
    except KeyError as exc:
        raise RuntimeError(f"GitHub Release is missing {exc.args[0]}") from exc

    release_dir = cache_dir / version
    release_dir.mkdir(parents=True, exist_ok=True)
    bundle = release_dir / bundle_name
    checksums = release_dir / "SHA256SUMS"
    try:
        selected_client.download(bundle_asset, bundle)
        selected_client.download(checksums_asset, checksums)
        verify_detached_checksum(bundle, checksums)
        manifest = verify_product_bundle(bundle, expected_version=version)
        if manifest.source_commit != release.source_commit:
            raise RuntimeError(
                "Product bundle source commit does not match the selected tag"
            )
    except Exception:
        shutil.rmtree(release_dir, ignore_errors=True)
        raise
    return ResolvedRelease(version=version, bundle=bundle)


__all__ = [
    "ReleaseAsset",
    "ReleaseDescriptor",
    "ResolvedRelease",
    "resolve_release_bundle",
]
