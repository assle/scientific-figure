#!/usr/bin/env python3
"""Prepare, publish, resume, and optionally activate one Product release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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


def require_release_acceptance(repository: Path, version: str) -> None:
    path = repository / "release-acceptance" / f"{version}.json"
    if not path.is_file():
        raise RuntimeError(f"release acceptance evidence is missing: {path}")
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"release acceptance evidence is invalid: {path}") from exc
    expected_versions = (
        "product_version", "plugin_version", "active_runtime_version",
        "cli_version", "mcp_version", "configuration_app_version",
    )
    valid = (
        isinstance(evidence, dict)
        and all(evidence.get(key) == version for key in expected_versions)
        and evidence.get("codex_restart_verified") is True
        and evidence.get("new_task_mcp_verified") is True
        and evidence.get("old_processes") == 0
        and evidence.get("clean") is True
    )
    if not valid:
        raise RuntimeError(f"release acceptance evidence is incomplete: {path}")


def require_approved_release_notes(repository: Path, version: str) -> Path:
    path = repository / "release-notes" / f"{version}.md"
    if not path.is_file():
        raise RuntimeError(f"release notes are missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\nstatus: approved\n---\n"):
        raise RuntimeError(f"release notes are not approved: {path}")
    return path


def release_is_complete(payload: object, version: str) -> bool:
    if not isinstance(payload, dict) or payload.get("isDraft") is not False:
        return False
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return False
    names = {
        str(item.get("name")) for item in assets if isinstance(item, dict)
    }
    return (
        "SHA256SUMS" in names
        and f"scientific-figure-builder-{version}.tar.gz" in names
        and any(
            name.startswith(f"scientific_figure_builder-{version}-")
            and name.endswith(".whl")
            for name in names
        )
    )


def select_target_version(
    current: str,
    selector: str,
    *,
    current_release_complete: bool,
) -> str:
    if not current_release_complete:
        return current
    return resolve_target_version(current, selector)


def select_base_revision(
    *,
    current: str,
    target: str,
    origin_version: str | None,
    prepared_version: str | None,
    prepared_ref: str,
) -> str:
    if prepared_version == target:
        return prepared_ref
    if current == target:
        return "HEAD"
    return "origin/main" if origin_version == target else "HEAD"


def candidate_ref(version: str) -> str:
    return f"refs/heads/codex/release-{version}"


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


def prepare_release(
    repository: Path,
    selector: str,
    *,
    notes_source: Path | None = None,
) -> tuple[str, str]:
    current = read_product_version(repository)
    target = resolve_target_version(current, selector)
    if target == current:
        return target, _run(("git", "rev-parse", "HEAD"), cwd=repository)
    sync_version_metadata(repository, target)
    notes = repository / "release-notes" / f"{target}.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    if notes_source is not None:
        notes.write_text(notes_source.read_text(encoding="utf-8"), encoding="utf-8")
    elif not notes.exists():
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
    if version == "0.6.0":
        require_release_acceptance(repository, version)
    require_approved_release_notes(repository, version)
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


def _release_payload(repository: Path, version: str) -> object:
    text = _run(
        ("gh", "release", "view", f"v{version}", "--json", "url,isDraft,assets"),
        cwd=repository,
        allow_failure=True,
    )
    return json.loads(text) if text else None


def _version_at(repository: Path, revision: str) -> str | None:
    text = _run(
        ("git", "show", f"{revision}:scientific-figure-builder/pyproject.toml"),
        cwd=repository,
        allow_failure=True,
    )
    if not text:
        return None
    return str(tomllib.loads(text)["project"]["version"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release Scientific Figure Builder")
    parser.add_argument("selector", help="patch, minor, major, or an exact X.Y.Z")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--activate-local", action="store_true")
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--check-acceptance", action="store_true")
    parser.add_argument("--check-notes", action="store_true")
    parser.add_argument("--check-release", action="store_true")
    args = parser.parse_args(argv)
    repository = REPOSITORY_ROOT
    if args.check_acceptance:
        require_release_acceptance(repository, args.selector)
        return 0
    if args.check_notes:
        require_approved_release_notes(repository, args.selector)
        return 0
    if args.check_release:
        version = args.selector.removeprefix("v")
        payload = json.loads(_run(
            ("gh", "release", "view", f"v{version}", "--json", "url,isDraft,assets"),
            cwd=repository,
        ))
        if not release_is_complete(payload, version):
            raise RuntimeError(f"GitHub Release v{version} is incomplete")
        return 0
    if _run(("git", "branch", "--show-current"), cwd=repository) != "main":
        raise RuntimeError("releases must start from main")
    _report("Inspecting main, tags, and existing GitHub Release state")
    _run(("git", "fetch", "origin", "--tags", "--prune"), cwd=repository)
    _run(("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"), cwd=repository)

    current = read_product_version(repository)
    target = select_target_version(
        current,
        args.selector,
        current_release_complete=release_is_complete(
            _release_payload(repository, current), current,
        ),
    )
    origin_version = _version_at(repository, "origin/main")
    prepared_ref = candidate_ref(target)
    prepared_version = _version_at(repository, prepared_ref)
    base_revision = select_base_revision(
        current=current,
        target=target,
        origin_version=origin_version,
        prepared_version=prepared_version,
        prepared_ref=prepared_ref,
    )
    notes_source = args.notes_file.resolve() if args.notes_file is not None else None
    if args.publish and target != current and notes_source is None:
        raise RuntimeError(
            "publishing a new version requires --notes-file with approved Release notes"
        )

    with tempfile.TemporaryDirectory(prefix="scientific-figure-release-") as temporary:
        worktree = Path(temporary) / "worktree"
        _run(("git", "worktree", "add", "--detach", str(worktree), base_revision),
             cwd=repository)
        try:
            _report(f"Preparing Product version {target} in an isolated worktree")
            version, commit = prepare_release(
                worktree, target, notes_source=notes_source,
            )
            payload: dict[str, object] = {
                "version": version,
                "commit": commit,
                "published": False,
            }
            activation_exit_code = 0
            if args.publish:
                _report("Publishing the release commit and waiting for authoritative CI")
                payload["release_url"] = publish_release(worktree, version, commit)
                payload["published"] = True
                if args.activate_local:
                    _report("Activating the published Product bundle locally")
                    completed = subprocess.run(
                        [str(worktree / "install.sh"), "--codex", "--release",
                         f"v{version}"],
                        cwd=worktree,
                        check=False,
                    )
                    activation_exit_code = completed.returncode
                    payload["local_activation_exit_code"] = activation_exit_code
                _run(
                    ("git", "update-ref", "-d", prepared_ref, commit),
                    cwd=repository,
                    allow_failure=True,
                )
            else:
                _run(("git", "update-ref", prepared_ref, commit), cwd=repository)
                payload["candidate_ref"] = prepared_ref
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
        "---\nstatus: draft\n---\n\n"
        f"# Scientific Figure Builder {version}\n\n"
        "## Changes\n\n"
        f"{log or '- Release preparation'}\n\n"
        "## Verification\n\n"
        "Authoritative test, type-check, bundle, and artifact evidence is attached "
        "by the tag Release workflow.\n"
    )


def _wait_for_main_ci(repository: Path, commit: str) -> None:
    _report(f"Waiting for Tests workflow on {commit[:12]}")
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
    _report(f"Waiting for the tag workflow to publish {tag}")
    version = tag.removeprefix("v")
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        text = _run(
            ("gh", "release", "view", tag, "--json", "url,isDraft,assets"),
            cwd=repository,
            allow_failure=True,
        )
        if text:
            payload = json.loads(text)
            if release_is_complete(payload, version):
                return str(payload["url"])
            if payload.get("isDraft") is False:
                raise RuntimeError(
                    f"GitHub Release {tag} exists but is missing formal artifacts"
                )
        time.sleep(5)
    raise RuntimeError(f"timed out waiting for GitHub Release {tag}")


def _replace(path: Path, pattern: str, replacement: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, original, count=1)
    if count != 1:
        raise RuntimeError(f"could not update version metadata in {path}")
    path.write_text(updated, encoding="utf-8")


def _report(message: str) -> None:
    print(f"[release] {message}", file=sys.stderr, flush=True)


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
