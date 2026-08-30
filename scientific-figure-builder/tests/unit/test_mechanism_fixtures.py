import json
from pathlib import Path


CASES = Path(__file__).resolve().parents[1] / "fixtures" / "mechanism_cases"


def test_twenty_offline_mechanism_cases_cover_single_axis_defects():
    paths = sorted(CASES.glob("*.json"))
    cases = [json.loads(path.read_text()) for path in paths]

    assert len(cases) == 20
    assert len({case["case_id"] for case in cases}) == 20
    assert len({case["defect"] for case in cases}) == 20
    assert {case["axis"] for case in cases} == {
        "structure", "text", "geometry", "phase", "publication", "raster",
    }
    assert all(case["expected_check_id"] for case in cases)
