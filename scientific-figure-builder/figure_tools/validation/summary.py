"""Shared validation-summary helper (plan section 11)."""

from __future__ import annotations

from typing import Any


def make_check(check_id: str, scope: str, level: str, status: str,
               detail: str = "", **extra: Any) -> dict[str, Any]:
    c: dict[str, Any] = {"check_id": check_id, "scope": scope, "level": level, "status": status}
    if detail:
        c["detail"] = detail
    for key, value in extra.items():
        if value is not None:
            c[key] = value
    return c


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify checks into errors/warnings and compute blocking flag.

    error + fail  -> blocks export
    warning + fail -> recorded but non-blocking
    """
    errors = sum(1 for c in checks if c.get("level") == "error" and c.get("status") == "fail")
    warnings = sum(1 for c in checks if c.get("level") == "warning" and c.get("status") == "fail")
    passed = sum(1 for c in checks if c.get("status") == "pass")
    return {"errors": errors, "warnings": warnings, "passed": passed, "blocking": errors > 0}
