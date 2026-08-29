"""Export gate and publish step (shared deep module).

Owns the "may this figure be exported?" decision — any validation report with
blocking failures blocks export unless ``force_export`` explicitly bypasses
the gate — plus the mechanical copy of the final PNG/SVG/PDF artifacts from
the assembly directory to the export destination.

The Figure Execution Module crosses this interface after the Orchestrator has
completed review. The gate rule and its messages therefore live in exactly one
place.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Sequence


def export_figure(
    validation_reports: Sequence[dict[str, Any]],
    source_dir: str | Path,
    output_dir: str | Path,
    force_export: bool = False,
    formats: Sequence[str] = ("png", "svg", "pdf"),
) -> dict[str, Any]:
    """Publish assembled figure files, gated on the validation reports.

    Args:
        validation_reports: reports the caller chose to surface to the gate.
            The caller decides which reports count (full run: every asset
            report plus the final report; MCP tool: the final report from
            disk). Any report whose ``summary.blocking`` is true blocks export.
        source_dir: assembly directory containing ``figure.<ext>`` files.
        output_dir: destination directory for the copied artifacts.
        force_export: bypass the gate (existing, explicit opt-in semantics).
        formats: file extensions to publish, defaults to png/svg/pdf.

    Returns:
        ``{"files": {ext: path}, "export_blocked_reason": str | None}``.
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)

    export_blocked_reason: str | None = None
    if not validation_reports:
        export_blocked_reason = (
            "no validation reports found; run validation before export"
        )
    elif not force_export and any(
        bool(r.get("summary", {}).get("blocking")) for r in validation_reports
    ):
        export_blocked_reason = (
            "validation reports contain blocking errors; "
            "use force_export=True to override"
        )

    if export_blocked_reason is not None:
        return {"files": {}, "export_blocked_reason": export_blocked_reason}

    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for ext in formats:
        src = source_dir / f"figure.{ext}"
        if src.exists():
            dst = output_dir / f"figure.{ext}"
            shutil.copyfile(src, dst)
            files[ext] = str(dst)
    return {"files": files, "export_blocked_reason": None}


__all__ = ["export_figure"]
