"""RealArkTransport unit tests (no network calls)."""

from __future__ import annotations

import os

import pytest

from figure_tools.ark.real_transport import _extract_json
from figure_tools.ark.transport import ArkError


def test_extract_json_plain():
    assert _extract_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert _extract_json('Here is the result: {"a": 1} done') == {"a": 1}


def test_real_transport_requires_api_key(monkeypatch):
    from figure_tools.ark.real_transport import RealArkTransport

    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with pytest.raises(ArkError):
        RealArkTransport()
