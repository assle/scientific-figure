"""Build and verify one complete, version-bound Product bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath


MANIFEST_NAME = "release-manifest.json"
BUNDLE_SCHEMA_VERSION = "1.0"
PRODUCT_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
PRODUCT_SOURCE_ITEMS = (
    "figure_tools",
    "install",
    "schemas",
    "templates",
    "SKILL.md",
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
    "install.sh",
)


@dataclass(frozen=True)
class ProductBundleRequest:
    repository_root: Path
    output_dir: Path
    product_version: str
    source_commit: str
    core_wheel: Path


@dataclass(frozen=True)
class ReleaseFile:
    sha256: str
    size: int


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: str
    product_version: str
    source_commit: str
    core_artifact: str
    compatibility: dict[str, str]
    files: dict[str, ReleaseFile]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProductBundleResult:
    bundle: Path
    checksums: Path
    manifest: ReleaseManifest


def build_product_bundle(request: ProductBundleRequest) -> ProductBundleResult:
    """Create the complete release archive from canonical repository inputs."""

    repository = request.repository_root.resolve()
    package = repository / "scientific-figure-builder"
    _require_version(package, request.product_version)
    if not request.core_wheel.is_file():
        raise ValueError(f"Core wheel is missing: {request.core_wheel}")
    _require_component_identity(repository, request.core_wheel, request.product_version)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    bundle = request.output_dir / (
        f"scientific-figure-builder-{request.product_version}.tar.gz"
    )
    checksums = request.output_dir / "SHA256SUMS"

    with tempfile.TemporaryDirectory(prefix="scientific-figure-bundle-") as temporary:
        stage = Path(temporary) / f"scientific-figure-builder-{request.product_version}"
        stage.mkdir()
        shutil.copy2(repository / "install.sh", stage / "install.sh")
        _copy_product_source(package, stage / "scientific-figure-builder")
        shutil.copytree(
            repository / "plugins" / "scientific-figure-builder",
            stage / "plugins" / "scientific-figure-builder",
            ignore=_ignored_source,
        )
        marketplace = stage / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        shutil.copy2(
            repository / ".agents" / "plugins" / "marketplace.json",
            marketplace,
        )
        artifact = stage / "artifacts" / request.core_wheel.name
        artifact.parent.mkdir()
        shutil.copy2(request.core_wheel, artifact)

        files = {
            path.relative_to(stage).as_posix(): ReleaseFile(
                sha256=_sha256(path), size=path.stat().st_size,
            )
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        }
        manifest = ReleaseManifest(
            schema_version=BUNDLE_SCHEMA_VERSION,
            product_version=request.product_version,
            source_commit=request.source_commit,
            core_artifact=artifact.relative_to(stage).as_posix(),
            compatibility=_compatibility(package),
            files=files,
        )
        (stage / MANIFEST_NAME).write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_reproducible_tar(stage, bundle)

    checksums.write_text(
        f"{_sha256(request.core_wheel)}  {request.core_wheel.name}\n"
        f"{_sha256(bundle)}  {bundle.name}\n",
        encoding="utf-8",
    )
    return ProductBundleResult(bundle=bundle, checksums=checksums, manifest=manifest)


def verify_product_bundle(
    bundle: Path,
    *,
    expected_version: str | None = None,
) -> ReleaseManifest:
    """Validate archive safety, manifest identity, and every bundled file digest."""

    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("Product bundle is empty")
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            raise ValueError("Product bundle must contain one root directory")
        root = next(iter(roots))
        regular: dict[str, tarfile.TarInfo] = {}
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or member.issym()
                or member.islnk()
            ):
                raise ValueError(f"Unsafe Product bundle member: {member.name}")
            if member.isfile():
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                if relative in regular:
                    raise ValueError(f"Duplicate Product bundle member: {relative}")
                regular[relative] = member
        manifest_member = regular.pop(MANIFEST_NAME, None)
        if manifest_member is None:
            raise ValueError("Product bundle has no Release manifest")
        manifest_stream = archive.extractfile(manifest_member)
        if manifest_stream is None:
            raise ValueError("Release manifest is unreadable")
        manifest = _manifest_from_dict(json.loads(manifest_stream.read()))
        if manifest.schema_version != BUNDLE_SCHEMA_VERSION:
            raise ValueError("Unsupported Release manifest version")
        if PRODUCT_VERSION_PATTERN.fullmatch(manifest.product_version) is None:
            raise ValueError("Release manifest has an invalid Product version")
        if expected_version is not None and manifest.product_version != expected_version:
            raise ValueError(
                f"Product bundle version {manifest.product_version} does not match "
                f"requested version {expected_version}"
            )
        if set(regular) != set(manifest.files):
            raise ValueError("Product bundle files do not match the Release manifest")
        for name, expected in manifest.files.items():
            stream = archive.extractfile(regular[name])
            if stream is None:
                raise ValueError(f"Product bundle member is unreadable: {name}")
            content = stream.read()
            if len(content) != expected.size or hashlib.sha256(content).hexdigest() != expected.sha256:
                raise ValueError(f"Product bundle digest mismatch: {name}")
        if manifest.core_artifact not in manifest.files:
            raise ValueError("Release manifest Core artifact is missing")
        _verify_archived_component_identity(
            archive, regular, manifest,
        )
        if not root.endswith(manifest.product_version):
            raise ValueError("Product bundle root does not match Product version")
        return manifest


def verify_detached_checksum(bundle: Path, checksums: Path | None = None) -> None:
    """Verify a Product bundle against its detached SHA256SUMS entry."""

    checksum_file = checksums or bundle.with_name("SHA256SUMS")
    if not checksum_file.is_file():
        raise ValueError(f"Detached checksums are missing: {checksum_file}")
    expected = None
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == bundle.name:
            expected = parts[0].lower()
            break
    if (
        expected is None
        or len(expected) != 64
        or any(char not in "0123456789abcdef" for char in expected)
    ):
        raise ValueError(f"Detached checksums have no valid entry for {bundle.name}")
    actual = _sha256(bundle)
    if actual != expected:
        raise ValueError(
            f"Product bundle checksum mismatch: expected {expected}, got {actual}"
        )


def extract_product_bundle(
    bundle: Path,
    destination: Path,
    *,
    expected_version: str | None = None,
) -> tuple[ReleaseManifest, Path]:
    """Verify and safely extract a Product bundle into a new destination."""

    manifest = verify_product_bundle(bundle, expected_version=expected_version)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        root_name = PurePosixPath(members[0].name).parts[0]
        for member in members:
            path = PurePosixPath(member.name)
            relative = Path(*path.parts[1:])
            target = destination / root_name / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"Unsupported Product bundle member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Product bundle member is unreadable: {member.name}")
            target.write_bytes(stream.read())
            target.chmod(member.mode & 0o777)
    return manifest, destination / root_name


def _copy_product_source(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in PRODUCT_SOURCE_ITEMS:
        item = source / name
        target = destination / name
        if item.is_dir():
            shutil.copytree(item, target, ignore=_ignored_source)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _ignored_source(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name in {"__pycache__", ".pytest_cache", ".venv", "dist", "build"}
        or name.endswith((".pyc", ".pyo"))
    }


def _require_version(package: Path, expected: str) -> None:
    import tomllib

    project = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))
    actual = str(project["project"]["version"])
    if actual != expected:
        raise ValueError(f"Product source version {actual} does not match {expected}")


def _require_component_identity(
    repository: Path,
    wheel: Path,
    expected: str,
) -> None:
    plugin = json.loads(
        (repository / "plugins" / "scientific-figure-builder" / ".codex-plugin"
         / "plugin.json").read_text(encoding="utf-8")
    )
    if str(plugin.get("version")) != expected:
        raise ValueError("Native plugin version does not match Product version")
    skill = (
        repository / "scientific-figure-builder" / "SKILL.md"
    ).read_text(encoding="utf-8")
    if re.search(rf'(?m)^  version: "{re.escape(expected)}"\r?$', skill) is None:
        raise ValueError("Workflow Skill version does not match Product version")
    _require_wheel_identity(wheel.read_bytes(), expected)


def _verify_archived_component_identity(
    archive: tarfile.TarFile,
    regular: dict[str, tarfile.TarInfo],
    manifest: ReleaseManifest,
) -> None:
    required = {
        "plugin": "plugins/scientific-figure-builder/.codex-plugin/plugin.json",
        "skill": "scientific-figure-builder/SKILL.md",
        "wheel": manifest.core_artifact,
    }
    content: dict[str, bytes] = {}
    for key, name in required.items():
        member = regular.get(name)
        stream = archive.extractfile(member) if member is not None else None
        if stream is None:
            raise ValueError(f"Product bundle is missing {name}")
        content[key] = stream.read()
    plugin = json.loads(content["plugin"])
    if str(plugin.get("version")) != manifest.product_version:
        raise ValueError("Bundled Native plugin version does not match manifest")
    skill = content["skill"].decode("utf-8")
    if re.search(
        rf'(?m)^  version: "{re.escape(manifest.product_version)}"\r?$', skill,
    ) is None:
        raise ValueError("Bundled Workflow Skill version does not match manifest")
    _require_wheel_identity(content["wheel"], manifest.product_version)


def _require_wheel_identity(content: bytes, expected: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            metadata_names = [
                name for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise ValueError("Core wheel must contain one METADATA file")
            metadata = Parser().parsestr(
                archive.read(metadata_names[0]).decode("utf-8")
            )
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise ValueError("Core artifact is not a valid wheel") from exc
    if metadata.get("Name") != "scientific-figure-builder":
        raise ValueError("Core wheel has the wrong distribution name")
    if metadata.get("Version") != expected:
        raise ValueError("Core wheel version does not match Product version")


def _write_reproducible_tar(source: Path, destination: Path) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted((source, *source.rglob("*"))):
                    arcname = path.relative_to(source.parent).as_posix()
                    info = archive.gettarinfo(str(path), arcname)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    if path.is_file():
                        with path.open("rb") as stream:
                            archive.addfile(info, stream)
                    else:
                        archive.addfile(info)


def _manifest_from_dict(payload: object) -> ReleaseManifest:
    if not isinstance(payload, dict):
        raise ValueError("Release manifest must be an object")
    raw_files = payload.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("Release manifest files must be an object")
    files: dict[str, ReleaseFile] = {}
    for name, raw in raw_files.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            raise ValueError("Release manifest contains an invalid file entry")
        try:
            files[name] = ReleaseFile(sha256=str(raw["sha256"]), size=int(raw["size"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Release manifest file: {name}") from exc
    try:
        return ReleaseManifest(
            schema_version=str(payload["schema_version"]),
            product_version=str(payload["product_version"]),
            source_commit=str(payload["source_commit"]),
            core_artifact=str(payload["core_artifact"]),
            compatibility={
                str(key): str(value)
                for key, value in dict(payload["compatibility"]).items()
            },
            files=files,
        )
    except KeyError as exc:
        raise ValueError(f"Release manifest is missing {exc.args[0]}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _compatibility(package: Path) -> dict[str, str]:
    prompt_text = (
        package / "figure_tools" / "lifecycle_prompts.py"
    ).read_text(encoding="utf-8")
    prompt_match = re.search(
        r'^PHASE_PROMPT_VERSION = "([^"]+)"$', prompt_text, re.MULTILINE,
    )
    if prompt_match is None:
        raise ValueError("Phase prompt compatibility version is missing")
    schema_versions: set[str] = set()
    for schema_path in (package / "schemas").glob("*.schema.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        version = (schema.get("properties") or {}).get("schema_version", {}).get("const")
        if version is not None:
            schema_versions.add(str(version))
    if len(schema_versions) != 1:
        raise ValueError("Artifact schemas do not share one compatibility version")
    return {
        "artifact_schemas": next(iter(schema_versions)),
        "phase_prompt": prompt_match.group(1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a complete Product bundle")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--core-wheel", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    version = args.version
    if version is None:
        project = tomllib.loads(
            (args.repository_root / "scientific-figure-builder" / "pyproject.toml")
            .read_text(encoding="utf-8")
        )
        version = str(project["project"]["version"])
    result = build_product_bundle(ProductBundleRequest(
        repository_root=args.repository_root,
        output_dir=args.output_dir,
        product_version=version,
        source_commit=args.source_commit,
        core_wheel=args.core_wheel,
    ))
    print(json.dumps({
        "bundle": str(result.bundle),
        "checksums": str(result.checksums),
        "version": result.manifest.product_version,
    }))
    return 0


__all__ = [
    "ProductBundleRequest",
    "ProductBundleResult",
    "ReleaseFile",
    "ReleaseManifest",
    "build_product_bundle",
    "extract_product_bundle",
    "verify_product_bundle",
    "verify_detached_checksum",
]


if __name__ == "__main__":
    raise SystemExit(main())
