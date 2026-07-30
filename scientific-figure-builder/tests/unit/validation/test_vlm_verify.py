"""Unit tests for local VLM verification (plan section 20.3)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from figure_tools.validation.vlm_verify import VLMVerifier


class _MockArk:
    def __init__(self, verdict=None, fail=False):
        self._verdict = verdict
        self._fail = fail
        self.calls = []

    def verify_local_region(self, crop_path, issue_type, context):
        self.calls.append((issue_type, context))
        if self._fail:
            raise RuntimeError("model unavailable")
        return self._verdict


def _check(cid="text_text_overlap", method="geometry", evidence="x.png"):
    return {"check_id": cid, "status": "fail", "level": "error",
            "method": method, "element_ids": ["a", "b"], "bbox": [0, 0, 10, 10],
            "detail": "overlap", "evidence_path": evidence}


def test_vlm_enriches_geometry_error_without_downgrading(tmp_path: Path):
    ark = _MockArk(verdict={"confirmed": True, "confidence": 0.9,
                            "severity": "error", "detail": "confirmed",
                            "move_element_id": "a", "direction": "right",
                            "minimum_shift_px": 12})
    v = VLMVerifier(ark, {"multimodal": {"enabled": True, "max_regions": 4}})
    checks = v.review([_check()])
    c = checks[0]
    assert c["status"] == "fail"  # geometry error not downgraded
    assert c["vlm_confirmed"] is True
    assert c["vlm_confidence"] == 0.9
    assert "move a" in c["repair_action"]


def test_vlm_cannot_downgrade_geometry_error_to_pass(tmp_path: Path):
    ark = _MockArk(verdict={"confirmed": False, "confidence": 0.95,
                            "detail": "not really overlapping"})
    v = VLMVerifier(ark, {})
    checks = v.review([_check(method="geometry")])
    assert checks[0]["status"] == "fail"  # stays fail


def test_vlm_can_reject_non_geometry_suspect(tmp_path: Path):
    ark = _MockArk(verdict={"confirmed": False, "confidence": 0.8,
                            "detail": "no text here"})
    v = VLMVerifier(ark, {"multimodal": {"minimum_issue_confidence": 0.5}})
    checks = v.review([_check(cid="unexpected_ai_text", method="ocr")])
    assert checks[0]["status"] == "pass"


def test_vlm_empty_verdict_not_pass(tmp_path: Path):
    ark = _MockArk(verdict={})
    v = VLMVerifier(ark, {})
    checks = v.review([_check()])
    assert checks[0]["status"] == "fail"
    assert checks[0]["vlm_status"] == "empty"


def test_vlm_failure_keeps_deterministic_result(tmp_path: Path):
    ark = _MockArk(fail=True)
    v = VLMVerifier(ark, {})
    checks = v.review([_check()])
    assert checks[0]["status"] == "fail"
    assert checks[0]["vlm_status"] == "error"


def test_vlm_skipped_without_ark_client():
    v = VLMVerifier(None, {"multimodal": {"enabled": True}})
    checks = v.review([_check()])
    assert "vlm_confirmed" not in checks[0]
    assert checks[0]["status"] == "fail"


def test_vlm_respects_max_regions():
    ark = _MockArk(verdict={"confirmed": True, "confidence": 0.9})
    v = VLMVerifier(ark, {"multimodal": {"max_regions": 2}})
    checks = [_check(evidence=f"e{i}.png") for i in range(5)]
    v.review(checks)
    assert len(ark.calls) == 2


def test_vlm_only_reviews_failing_reviewable_with_evidence():
    ark = _MockArk(verdict={"confirmed": True, "confidence": 0.9})
    v = VLMVerifier(ark, {})
    checks = [
        _check(cid="text_text_overlap", evidence="e.png"),  # reviewable
        {"check_id": "text_text_overlap", "status": "pass"},  # not failing
        {"check_id": "missing_assets", "status": "fail", "method": "geometry"},  # not reviewable
        _check(cid="text_text_overlap", evidence=None),  # no evidence
    ]
    v.review(checks)
    assert len(ark.calls) == 1
