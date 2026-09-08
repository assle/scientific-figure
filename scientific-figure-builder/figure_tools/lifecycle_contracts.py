"""JSON schemas for the two public Lifecycle MCP tools."""

from __future__ import annotations

import json
from typing import Any
from figure_tools._resources import schema_path
from figure_tools.generation_intent import SELECTION_SCHEMA
from figure_tools.style_spec import STYLE_INPUT_SCHEMA


PANEL_REQUEST_SCHEMA = json.loads(
    schema_path("panel-request.schema.json").read_text(encoding="utf-8")
)


FIGURE_REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["figure_id", "panels"],
    "properties": {
        "generation_intent": SELECTION_SCHEMA,
        "require_editable_objects": {"type": "boolean"},
        "figure_id": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "minLength": 1},
        "intent": {"type": "string"},
        "description": {"type": "string"},
        "canvas": {
            "type": "object",
            "additionalProperties": False,
            "required": ["aspect_ratio", "width", "height"],
            "properties": {
                "aspect_ratio": {"type": "number", "exclusiveMinimum": 0},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "height": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "units": {"type": "string", "enum": ["mm", "cm", "in", "px"]},
        "panels": {
            "type": "array",
            "minItems": 1,
            "items": PANEL_REQUEST_SCHEMA,
        },
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["element_id", "kind", "content"],
                "properties": {
                    "element_id": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "enum": ["label", "annotation", "equation"]},
                    "bbox": {"type": "array", "minItems": 4, "maxItems": 4,
                             "items": {"type": "number", "minimum": 0, "maximum": 1}},
                    "content": {"type": "string", "minLength": 1},
                    "panel_id": {"type": "string", "minLength": 1},
                },
            },
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "user_input_requirements": {"type": "array", "items": {"type": "string"}},
        "reference_figures": {"type": "array", "items": {"type": "string"}},
        "export_target": {"type": ["string", "null"], "enum": ["general", "ppt", None]},
        "figure_width_cm": {"type": ["number", "null"], "exclusiveMinimum": 0},
        "language": {"type": ["string", "null"], "enum": ["zh", "en", None]},
        "style": STYLE_INPUT_SCHEMA,
        "publication_profile": {"type": "string", "enum": ["general", "nature_research"]},
        "figure_graph": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ports", "typed_edges", "groups", "labels", "constraints"],
            "properties": {
                "ports": {"type": "array", "items": {"type": "object"}},
                "typed_edges": {"type": "array", "items": {"type": "object"}},
                "groups": {"type": "array", "items": {"type": "object"}},
                "labels": {"type": "array", "items": {"type": "object"}},
                "constraints": {"type": "array", "items": {"type": "object"}},
            },
        },
        "include_pptx": {"type": "boolean"},
        "auto_execute": {"type": "boolean"},
    },
}

WORKFLOW_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_dir"],
    "properties": {
        "run_dir": {"type": "string", "minLength": 1},
        "project_dir": {"type": "string", "minLength": 1},
        "base_dir": {"type": "string", "minLength": 1},
        "dpi": {"type": "integer", "minimum": 1},
        "wait_timeout": {"type": "number", "minimum": 0, "maximum": 240},
        "operation_id": {"type": "string", "minLength": 1},
        "request": FIGURE_REQUEST_SCHEMA,
        "action": {
            "oneOf": [
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "operation_id", "reason"],
                    "properties": {
                        "action": {"const": "cancel_operation"},
                        "operation_id": {"type": "string", "minLength": 1},
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "generation_intent", "reason"],
                    "properties": {
                        "action": {"const": "revise_generation_intent"},
                        "generation_intent": SELECTION_SCHEMA,
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
                {"type": "string", "enum": [
                    "start", "resume", "approve_plan", "approve_style_anchor",
                ]},
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "answers"],
                    "properties": {
                        "action": {"const": "submit_clarifications"},
                        "answers": {
                            "type": "object", "additionalProperties": False,
                            "minProperties": 1,
                            "properties": {
                                "export_target": {"type": "string", "enum": ["general", "ppt"]},
                                "figure_width_cm": {"type": "number", "exclusiveMinimum": 0},
                                "language": {"type": "string", "enum": ["zh", "en"]},
                                "style": STYLE_INPUT_SCHEMA,
                            },
                        },
                    },
                },
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "repairs"],
                    "properties": {
                        "action": {"const": "apply_repair"},
                        "repairs": {
                            "type": "array", "minItems": 1,
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "required": ["asset_id"],
                                "anyOf": [
                                    {"required": ["route"]},
                                    {"required": ["operation"]},
                                ],
                                "properties": {
                                    "asset_id": {"type": "string", "minLength": 1},
                                    "route": {"type": "string", "enum": ["python", "svg", "image_edit", "image_model"]},
                                    "plot_spec": {"type": "string", "minLength": 1},
                                    "content": {"type": "string", "minLength": 1},
                                    "prompt": {"type": "string", "minLength": 1},
                                    "operation": {"type": "string", "enum": [
                                        "layout_patch", "connector_patch",
                                        "vector_patch", "raster_edit",
                                    ]},
                                    "bbox": {
                                        "type": "array", "minItems": 4, "maxItems": 4,
                                        "items": {"type": "number", "minimum": 0, "maximum": 1},
                                    },
                                    "bbox_space": {"type": "string", "enum": ["panel", "canvas"]},
                                    "edge_id": {"type": "string", "minLength": 1},
                                    "source_port": {"type": "string", "minLength": 1},
                                    "target_port": {"type": "string", "minLength": 1},
                                    "direction": {"type": "string", "enum": [
                                        "forward", "reverse", "bidirectional",
                                    ]},
                                    "semantic_type": {"type": "string", "minLength": 1},
                                    "mask_path": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                    },
                },
                {
                    "type": "object", "additionalProperties": False,
                    "required": ["action", "reason"],
                    "properties": {
                        "action": {"const": "force_export"},
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
            ],
        },
    },
}

ARTIFACT_REFERENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "exists", "content_hash"],
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "exists": {"type": "boolean"},
        "content_hash": {"type": ["string", "null"]},
    },
}

WORKFLOW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phase", "status", "next_action", "artifacts"],
    "properties": {
        "phase": {"type": "string", "enum": [
            "intake", "planning", "execution", "review_and_repair", "export",
        ]},
        "status": {"type": "string", "enum": ["in_progress", "paused", "completed"]},
        "next_action": {"type": ["string", "null"]},
        "artifacts": {
            "type": "object",
            "additionalProperties": ARTIFACT_REFERENCE_SCHEMA,
        },
        "clarifications": {"type": "array", "items": {"type": "object"}},
        "export_blocked_reason": {"type": ["string", "null"]},
        "generation_summary": {"type": "string"},
        "error": {"type": "string"},
        "recovery": {"type": "string"},
        "operation_id": {"type": "string", "minLength": 1},
        "operation_status": {
            "type": "string",
            "enum": [
                "running", "cancellation_requested", "failed", "cancelled",
                "remote_outcome_unknown",
            ],
        },
    },
}

INITIALIZE_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["project_dir"],
    "properties": {"project_dir": {"type": "string", "minLength": 1}},
}


__all__ = [
    "FIGURE_REQUEST_SCHEMA",
    "INITIALIZE_INPUT_SCHEMA",
    "WORKFLOW_INPUT_SCHEMA",
    "WORKFLOW_OUTPUT_SCHEMA",
]
