"""Provider-neutral prompt and structured-response contracts."""

from __future__ import annotations

import json
import re
from typing import Any

from figure_tools.providers.transport import ProviderError

REFERENCE_ANALYSIS_INSTRUCTION = (
    "Analyze this scientific reference figure. Return ONLY JSON with keys: "
    '"panels" (list of {panel_id, bbox=[x,y,width,height] normalized 0-1}), '
    '"objects" (list of {label, confidence}), "text_candidates" '
    '(list of {text, confidence}), "confidence" (0-1), "uncertainties" '
    "(list of strings)."
)

DEFAULT_VALIDATION_INSTRUCTION = (
    "Validate this scientific figure image. Return ONLY JSON with keys: "
    '"checks" (list of {check_id, status, detail}) and "blocking" (boolean). '
    "Check: background_residues (opaque bg that should be transparent), "
    "text_overlap (colliding text/labels/ticks/titles), "
    "label_axis_collision (panel labels (a),(b) vs axis labels/ticks), "
    "colorbar_collision (colorbar vs plot area/panels), "
    "legend_data_overlap (legend vs data), "
    "label_readability (tick labels readable, not crowded), "
    "object_count (expected objects present), "
    "forbidden_text (text in AI-generated portions, must be text-free), "
    "style_consistency (consistent style across panels), "
    "scientific_errors (wrong axis direction or misleading color scale)."
)


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            value = json.loads(match.group(0))
        else:
            raise ProviderError(
                f"could not parse JSON from model response: {text[:200]}"
            )
    if not isinstance(value, dict):
        raise ProviderError("model response JSON must be an object")
    return value


def vision_prompt(role: str, payload: dict[str, Any]) -> str:
    instruction = (
        REFERENCE_ANALYSIS_INSTRUCTION
        if role == "reference_analysis"
        else DEFAULT_VALIDATION_INSTRUCTION
    )
    prompt = payload.get("prompt")
    return f"{prompt}\n\n{instruction}" if prompt else instruction
