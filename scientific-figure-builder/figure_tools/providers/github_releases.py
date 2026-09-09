"""GitHub Release network Adapter for Product bundle resolution."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Mapping

from figure_tools.release_source import ReleaseAsset, ReleaseDescriptor


DEFAULT_REPOSITORY = "assle/scientific-figure"


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

    def download(self, asset: ReleaseAsset, destination: Path) -> None:
        request = urllib.request.Request(asset.url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            destination.write_bytes(response.read())

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


__all__ = ["GitHubReleaseClient"]
