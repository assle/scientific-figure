"""Shared SVG normalization for byte-identical, target-aware output (plan section 15)."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

HASHSALT = "scientific-figure-builder"
_DATE_RE = re.compile(rb"<dc:date>.*?</dc:date>", re.DOTALL)
_COMMENT_RE = re.compile(rb"<!--.*?-->", re.DOTALL)
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_EXPORT_TARGETS = {"general", "ppt"}
_PPT_FONT_FAMILY = "Arial, SimSun, sans-serif"
_PPT_DEFAULT_FONT_SIZE_PT = "7.5"
_PRESENTATION_PROPERTIES = {
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-anchor",
}

ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
ET.register_namespace("cc", "http://creativecommons.org/ns#")
ET.register_namespace("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")


def resolve_export_target(value: str | None) -> str:
    """Resolve and validate the export target."""
    target = value or "general"
    if target not in _EXPORT_TARGETS:
        raise ValueError(
            f"unsupported export_target {target!r}; expected one of "
            f"{sorted(_EXPORT_TARGETS)}"
        )
    return target


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_style(style: str | None) -> dict[str, str]:
    if not style:
        return {}
    props: dict[str, str] = {}
    for part in style.split(";"):
        if not part.strip():
            continue
        name, _, value = part.partition(":")
        if name and value:
            props[name.strip()] = value.strip()
    return props


def _emit_style(props: dict[str, str]) -> str | None:
    if not props:
        return None
    return ";".join(f"{k}: {v}" for k, v in props.items())


def _is_identity_text_transform(transform: str | None) -> bool:
    if not transform:
        return False
    value = " ".join(transform.split())
    if value.startswith("rotate(-0 "):
        return True
    if value in {"translate(0 0)", "translate(0,0)", "scale(1)", "scale(1 1)"}:
        return True
    return False


def normalize_ppt_svg_bytes(data: bytes) -> bytes:
    """Make matplotlib SVG output friendlier to Microsoft Office import.

    The main goal is to keep ordinary text as real ``<text>`` elements while
    converting CSS ``style`` values into SVG presentation attributes that
    Office's SVG importer is more likely to honor. Identity/no-op transforms
    on text are removed so text does not get re-anchored to an unexpected point.
    Text elements also get an Office-friendly font family (Arial for Latin,
    SimSun/宋体 for Chinese) and a 六号 (7.5 pt) default font size when they do
    not declare one, so ungrouping in PowerPoint does not swap in a random
    font or re-flow overlapping text.
    """
    root = ET.fromstring(data)

    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag not in {"text", "tspan", "path", "rect", "line", "circle", "ellipse",
                       "polyline", "polygon", "use"}:
            continue

        style = elem.get("style")
        props = _parse_style(style)
        for name, value in props.items():
            if name in _PRESENTATION_PROPERTIES:
                elem.set(name, value)
        remaining = {k: v for k, v in props.items()
                     if k not in _PRESENTATION_PROPERTIES}
        new_style = _emit_style(remaining)
        if new_style:
            elem.set("style", new_style)
        elif "style" in elem.attrib:
            del elem.attrib["style"]

        if tag in {"text", "tspan"}:
            if _is_identity_text_transform(elem.get("transform")):
                del elem.attrib["transform"]
            family = elem.get("font-family")
            # Always declare the Office font stack so PowerPoint's font
            # fallback is deterministic: Arial for Latin, SimSun (宋体) for
            # Chinese, instead of whatever matplotlib resolved locally.
            if not family or "SimSun" not in family:
                elem.set("font-family", _PPT_FONT_FAMILY)
            if not elem.get("font-size"):
                elem.set("font-size", _PPT_DEFAULT_FONT_SIZE_PT)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def normalize_svg_bytes(data: bytes, export_target: str = "general") -> bytes:
    """Strip non-deterministic metadata and optionally apply PPT normalization."""
    data = _COMMENT_RE.sub(b"", data)
    data = _DATE_RE.sub(b"", data)
    if resolve_export_target(export_target) == "ppt":
        data = normalize_ppt_svg_bytes(data)
    return data
