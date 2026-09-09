#!/usr/bin/env python3
"""Prepare, publish, resume, and optionally activate one Product release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path


SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def resolve_target_version(current: str, selector: str) -> str:
    match = SEMVER.fullmatch(current)
    if match is None:
        raise ValueError(f"current Product version is not stable SemVer: {current}")
    major, minor, patch = (int(item) for item in match.groups())
    if selector == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if selector == "minor":
        return f"{major}.{minor + 1}.0"
    if selector == "major":
        return f"{major + 1}.0.0"
    if SEMVER.fullmatch(selector):
        return selector
    raise ValueError("release selector must be patch, minor, major, or X.Y.Z")


def require_tag_target(*, tag: str, actual: str, expected: str) -> None:
    if actual and actual != expected:
        raise RuntimeError(
            f"immutable tag {tag} points to {actual}, expected {expected}"
        )


def read_product_version(repository: Path) -> str:
    project = tomllib.loads(
        (repository / "scientific-figure-builder" / "pyproject.toml")
        .read_text(encoding="utf-8")
    )
    return str(project["project"]["version"])


def sync_version_metadata(repository: Path, version: str) -> None:
    _replace(
        repository / "scientific-figure-builder" / "pyproject.toml",
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
    )
    _replace(
        repository / "scientific-figure-builder" / "SKILL.md",
        r'(?m)^  version: "[^"]+"$',
        f'  version: "{version}"',
    )
    _replace(
        repository / "CITATION.cff",
        r"(?m)^version: .+$",
        f"version: {version}",
    )
    _run(("uv", "lock"), cwd=repository / "scientific-figure-builder")
    _run(("python3", "scripts/sync_plugin_bundle.py"), cwd=repository)


def prepare_release(repository: Path, selector: str) -> tuple[str, str]:
    current = read_product_version(repository)
    target = resolve_target_version(current, selector)
    if target == current:
        return target, _run(("git", "rev-parse", "HEAD"), cwd=repository)
    sync_version_metadata(repository, target)
    notes = repository / "release-notes" / f"{target}.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    if not notes.exists():
        notes.write_text(_release_notes(repository, target), encoding="utf-8")
    _run(("git", "add", "CITATION.cff", "release-notes", "plugins",
          "scientific-figure-builder/pyproject.toml",
          "scientific-figure-builder/uv.lock",
          "scientific-figure-builder/SKILL.md"), cwd=repository)
    _run(("git", "diff", "--cached", "--check"), cwd=repository)
    _run(("git", "commit", "-m", f"Release Scientific Figure Builder {target}"),
         cwd=repository)
    return target, _run(("git", "rev-parse", "HEAD"), cwd=repository)


def publish_release(repository: Path, version: str, commit: str) -> str:
    _run(("git", "push", "origin", f"{commit}:main"), cwd=repository, capture=False)
    _wait_for_main_ci(repository, commit)
    tag = f"v{version}"
    remote_tag = _run(
        ("git", "ls-remote", "origin", f"refs/tags/{tag}"), cwd=repository,
    )
    actual = remote_tag.split()[0] if remote_tag else ""
    require_tag_target(tag=tag, actual=actual, expected=commit)
    if not actual:
        local_tag = _run(
            ("git", "rev-parse", f"refs/tags/{tag}"),
            cwd=repository,
            allow_failure=True,
        )
        require_tag_target(tag=tag, actual=local_tag, expected=commit)
        if not local_tag:
            _run(("git", "tag", tag, commit), cwd=repository)
        _run(("git", "push", "origin", tag), cwd=repository, capture=False)
    return _wait_for_release(repository, tag)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release Scientific Figure Builder")
    parser.add_argument("selector", help="patch, minor, major, or an exact X.Y.Z")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--activate-local", action="store_true")
    args = parser.parse_args(argv)
    repository = REPOSITORY_ROOT
    if _run(("git", "branch", "--show-current"), cwd=repository) != "main":
        raise RuntimeError("releases must start from main")
    _run(("git", "fetch", "origin", "--tags", "--prune"), cwd=repository)
    _run(("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"), cwd=repository)

    with tempfile.TemporaryDirectory(prefix="scientific-figure-release-") as temporary:
        worktree = Path(temporary) / "worktree"
        _run(("git", "worktree", "add", "--detach", str(worktree), "HEAD"),
             cwd=repository)
        try:
            version, commit = prepare_release(worktree, args.selector)
            payload: dict[str, object] = {
                "version": version,
                "commit": commit,
                "published": False,
            }
            activation_exit_code = 0
            if args.publish:
                payload["release_url"] = publish_release(repository, version, commit)
                payload["published"] = True
                if args.activate_local:
                    completed = subprocess.run(
                        [str(repository / "install.sh"), "--codex", "--release",
                         f"v{version}"],
                        cwd=repository,
                        check=False,
                    )
                    activation_exit_code = completed.returncode
                    payload["local_activation_exit_code"] = activation_exit_code
            print(json.dumps(payload, indent=2))
            return activation_exit_code
        finally:
            _run(("git", "worktree", "remove", "--force", str(worktree)),
                 cwd=repository)


def _release_notes(repository: Path, version: str) -> str:
    previous = _run(
        ("git", "describe", "--tags", "--abbrev=0", "HEAD"),
        cwd=repository,
        allow_failure=True,
    )
    revision = f"{previous}..HEAD" if previous else "HEAD"
    log = _run(("git", "log", revision, "--pretty=- %s"), cwd=repository)
    return (
        f"# Scientific Figure Builder {version}\n\n"
        "## Changes\n\n"
        f"{log or '- Release preparation'}\n\n"
        "## Verification\n\n"
        "Authoritative test, type-check, bundle, and artifact evidence is attached "
        "by the tag Release workflow.\n"
    )


def _wait_for_main_ci(repository: Path, commit: str) -> None:
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        text = _run(
            ("gh", "run", "list", "--commit", commit, "--workflow", "Tests",
             "--limit", "1", "--json", "databaseId,status,conclusion"),
            cwd=repository,
        )
        runs = json.loads(text or "[]")
        if runs:
            run = runs[0]
            if run.get("status") == "completed":
                if run.get("conclusion") != "success":
                    raise RuntimeError(f"main CI failed for {commit}")
                return
        time.sleep(5)
    raise RuntimeError(f"timed out waiting for main CI for {commit}")


def _wait_for_release(repository: Path, tag: str) -> str:
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        text = _run(
            ("gh", "release", "view", tag, "--json", "url,isDraft"),
            cwd=repository,
            allow_failure=True,
        )
        if text:
            payload = json.loads(text)
            if payload.get("url") and payload.get("isDraft") is False:
                return str(payload["url"])
        time.sleep(5)
    raise RuntimeError(f"timed out waiting for GitHub Release {tag}")


def _replace(path: Path, pattern: str, replacement: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, original, count=1)
    if count != 1:
        raise RuntimeError(f"could not update version metadata in {path}")
    path.write_text(updated, encoding="utf-8")


def _run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    capture: bool = True,
    allow_failure: bool = False,
) -> str:
    completed = subprocess.run(
        list(command), cwd=cwd, text=True,
        capture_output=capture, check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = completed.stderr.strip() if capture else ""
        raise RuntimeError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip() if capture and completed.returncode == 0 else ""


if __name__ == "__main__":
    raise SystemExit(main())
