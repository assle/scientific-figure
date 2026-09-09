"""Resolve a GitHub Release to one verified, pinned Product bundle."""

from __future__ import annotations

import json
import os
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from figure_tools.release_bundle import (
    PRODUCT_VERSION_PATTERN,
    verify_detached_checksum,
    verify_product_bundle,
)


DEFAULT_REPOSITORY = "assle/scientific-figure"


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


class GitHubReleaseClient:
    def __init__(
        self,
        repository: str = DEFAULT_REPOSITORY,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.repository = repository
        self.environ = os.environ if environ is None else environ

    def describe(self, selector: str) -> ReleaseDescriptor:
        suffix = (
            "latest" if selector == "latest"
            else "tags/" + urllib.parse.quote(
                selector if selector.startswith("v") else f"v{selector}", safe="",
            )
        )
        payload = self._read_json(
            f"https://api.github.com/repos/{self.repository}/releases/{suffix}"
        )
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise RuntimeError("GitHub Release has no assets")
        tag_name = str(payload.get("tag_name") or "")
        return ReleaseDescriptor(
            tag_name=tag_name,
            source_commit=self._tag_commit(tag_name),
            assets=tuple(
                ReleaseAsset(
                    name=str(item.get("name") or ""),
                    url=str(item.get("browser_download_url") or ""),
                )
                for item in assets
                if isinstance(item, dict)
            ),
        )

    def _tag_commit(self, tag_name: str) -> str:
        reference = self._read_json(
            f"https://api.github.com/repos/{self.repository}/git/ref/tags/"
            + urllib.parse.quote(tag_name, safe="")
        )
        target = reference.get("object")
        if not isinstance(target, dict):
            raise RuntimeError("GitHub tag has no target")
        if target.get("type") == "commit":
            return str(target.get("sha") or "")
        if target.get("type") == "tag":
            annotated = self._read_json(
                f"https://api.github.com/repos/{self.repository}/git/tags/"
                + urllib.parse.quote(str(target.get("sha") or ""), safe="")
            )
            annotated_target = annotated.get("object")
            if isinstance(annotated_target, dict):
                return str(annotated_target.get("sha") or "")
        raise RuntimeError("GitHub tag does not resolve to a commit")

    def download(self, asset: ReleaseAsset, destination: Path) -> None:
        request = urllib.request.Request(asset.url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            destination.write_bytes(response.read())

    def _read_json(self, url: str) -> dict[str, object]:
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read())
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub Release response must be an object")
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "scientific-figure-builder",
        }
        token = self.environ.get("GITHUB_TOKEN") or self.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


def resolve_release_bundle(
    selector: str,
    *,
    cache_dir: Path,
    client: ReleaseClient | None = None,
) -> ResolvedRelease:
    """Resolve latest once, download its assets, and verify the exact bundle."""

    selected_client = client or GitHubReleaseClient()
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
    "GitHubReleaseClient",
    "ReleaseAsset",
    "ReleaseDescriptor",
    "ResolvedRelease",
    "resolve_release_bundle",
]
