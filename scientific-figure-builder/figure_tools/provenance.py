"""Canonical provenance hashes shared by persisted scientific artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def hash_file(path: str | Path) -> str:
    return hash_bytes(Path(path).read_bytes())


def hash_json(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hash_bytes(payload)


__all__ = ["hash_bytes", "hash_file", "hash_json"]
