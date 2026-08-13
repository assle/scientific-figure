"""Generation report writer (plan section 13)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_generation_report(
    run_dir: str | Path,
    figure_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    validation_reports: list[dict[str, Any]],
    run_state: dict[str, Any] | None = None,
    exported: bool = False,
    force_export: bool = False,
    export_blocked_reason: str | None = None,
    export_target: str = "general",
) -> Path:
    run_dir = Path(run_dir)
    lines: list[str] = []
    lines.append(f"# Generation report: {figure_plan.get('figure_id', '')}")
    lines.append("")
    lines.append(f"- Run ID: {figure_plan.get('run_id', '')}")
    lines.append(f"- Task: classified by router; approval: "
                 f"{figure_plan.get('approval', {}).get('status', '')}")
    lines.append(f"- Export target: {export_target}")
    lines.append(f"- Exported: {exported}")
    lines.append("")

    lines.append("## Estimated vs used paid calls")
    calls = (run_state or {}).get("calls", {})
    counts = calls.get("counts", {})
    est = figure_plan.get("estimated_paid_calls", {})
    lines.append("| role | estimated | used |")
    lines.append("|---|---|---|")
    for role in ("reference_analysis", "generation", "edits", "validations",
                 "final_validation"):
        lines.append(f"| {role} | {est.get(role, 0)} | {counts.get(role, 0)} |")
    lines.append("")

    lines.append("## Assets")
    routing_by_id = {a["asset_id"]: a.get("routing", "-")
                     for a in figure_plan.get("assets", [])}
    lines.append("| asset_id | type | routing | transparent |")
    lines.append("|---|---|---|---|")
    for a in asset_manifest.get("assets", []):
        lines.append(f"| {a['asset_id']} | {a['type']} | "
                     f"{routing_by_id.get(a['asset_id'], '-')} | "
                     f"{a.get('transparent','-')} |")
    lines.append("")

    lines.append("## Validation")
    for rep in validation_reports:
        s = rep.get("summary", {})
        lines.append(f"- {rep.get('run_id','?')}: errors={s.get('errors',0)} "
                     f"warnings={s.get('warnings',0)} blocking={s.get('blocking',False)}")
    lines.append("")

    # Issue summary with localized evidence (plan section 17.4).
    issues = []
    for rep in validation_reports:
        for c in rep.get("checks", []):
            if c.get("status") == "fail":
                issues.append(c)
    if issues:
        lines.append("## Validation issues")
        lines.append("| check_id | level | detail | evidence |")
        lines.append("|---|---|---|---|")
        for c in issues:
            ev = c.get("evidence_path", "-")
            if ev:
                ev = ev.replace(str(run_dir) + "/", "")
            detail = (c.get("detail") or "").replace("|", "/")
            lines.append(f"| {c.get('check_id','')} | {c.get('level','')} | "
                         f"{detail} | {ev} |")
        lines.append("")

    if validation_reports:
        worst = max(r.get("summary", {}).get("errors", 0) for r in validation_reports)
        if worst > 0 and exported and force_export:
            lines.append("> Export forced despite validation errors (force_export=True).")
        elif worst > 0 and not exported:
            lines.append("> Export blocked due to validation errors.")
            if export_blocked_reason:
                lines.append(f"> Reason: {export_blocked_reason}")
        elif exported:
            lines.append("> Export completed; warnings (if any) recorded above.")

    out = run_dir / "generation_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
