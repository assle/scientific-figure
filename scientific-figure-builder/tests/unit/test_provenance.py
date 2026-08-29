from __future__ import annotations

import json

from figure_tools.provenance import hash_bytes, hash_file, hash_json


def test_hash_vocabulary_uses_the_same_sha256_representation(tmp_path):
    payload = b"scientific figure\n"
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)

    assert hash_bytes(payload).startswith("sha256:")
    assert hash_file(path) == hash_bytes(payload)


def test_hash_json_is_stable_across_mapping_order():
    left = {"figure": "f-1", "panels": ["a", "b"]}
    right = json.loads('{"panels":["a","b"],"figure":"f-1"}')

    assert hash_json(left) == hash_json(right)
