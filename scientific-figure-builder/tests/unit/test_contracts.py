"""Provider-neutral prompt and structured-response contract tests."""

from __future__ import annotations

from figure_tools.providers.contracts import DEFAULT_VALIDATION_INSTRUCTION, extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert extract_json('Here is the result: {"a": 1} done') == {"a": 1}


def test_validation_instruction_includes_layout_checks():
    assert "legend_data_overlap" in DEFAULT_VALIDATION_INSTRUCTION
    assert "text_overlap" in DEFAULT_VALIDATION_INSTRUCTION
    assert "label_readability" in DEFAULT_VALIDATION_INSTRUCTION


def test_validation_instruction_remains_concise():
    assert len(DEFAULT_VALIDATION_INSTRUCTION) < 800
