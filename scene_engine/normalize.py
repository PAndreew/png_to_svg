from __future__ import annotations
import copy
import json
import re
import uuid
from typing import Any
from .catalog import ALLOWED_KINDS, DEFAULT_CANVAS, COLOR_WORDS, default_color, default_label

SVG_NS = "http://www.w3.org/2000/svg"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def xml_escape(value: Any) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def compact_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def default_scene() -> dict[str, Any]:
    return {
        "version": "odd.scene.v1",
        "canvas": copy.deepcopy(DEFAULT_CANVAS),
        "title": "ODD pictogram",
        "prompt": "",
        "warnings": [],
        "elements": [],
    }


def deep_copy_scene(scene: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(scene) if scene else default_scene()


def ensure_color(value: Any, fallback: str) -> str:
    if not value:
        return fallback
    text = str(value).strip().lower()
    if text in COLOR_WORDS:
        return COLOR_WORDS[text]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return text
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return "#" + "".join(ch * 2 for ch in text[1:])
    return fallback


def clamp_number(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except Exception:
        return fallback
    return max(low, min(high, number))


def normalize_scene(scene: dict[str, Any] | None) -> dict[str, Any]:
    normalized = default_scene()
    if scene:
        normalized.update({k: v for k, v in scene.items() if k != "canvas"})
        if isinstance(scene.get("canvas"), dict):
            normalized["canvas"].update(scene["canvas"])

    normalized["canvas"]["width"] = clamp_number(normalized["canvas"].get("width", 1024), 640, 1600, 1024)
    normalized["canvas"]["height"] = clamp_number(normalized["canvas"].get("height", 768), 480, 1200, 768)
    normalized["canvas"]["background"] = ensure_color(normalized["canvas"].get("background", "#f8fafc"), "#f8fafc")
    normalized["warnings"] = list(normalized.get("warnings") or [])

    elements = []
    for raw in normalized.get("elements") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "placeholder")
        if kind not in ALLOWED_KINDS:
            raw = dict(raw)
            raw["label"] = raw.get("label") or f"Missing asset: {kind}"
            raw["kind"] = "placeholder"
            normalized["warnings"].append(f"Unknown asset '{kind}' rendered as placeholder.")
            kind = "placeholder"

        element = {
            "id": str(raw.get("id") or new_id(kind)),
            "kind": kind,
            "label": str(raw.get("label") or default_label(kind)),
            "layer": int(raw.get("layer", 10)),
            "color": ensure_color(raw.get("color"), default_color(kind)),
            "accentColor": ensure_color(raw.get("accentColor"), "#ffffff"),
            "x": float(raw.get("x", 0)),
            "y": float(raw.get("y", 0)),
            "rotation": float(raw.get("rotation", 0)),
            "scale": float(raw.get("scale", 1)),
            "transform": str(raw.get("transform") or "").strip(),
            "props": raw.get("props") if isinstance(raw.get("props"), dict) else {},
        }
        element["scale"] = max(0.2, min(6.0, element["scale"]))
        elements.append(element)

    normalized["elements"] = sorted(elements, key=lambda item: (item.get("layer", 10), item["id"]))
    return normalized


def build_transform(element: dict[str, Any]) -> str:
    if element.get("transform"):
        return element["transform"]
    x = float(element.get("x", 0))
    y = float(element.get("y", 0))
    rotation = float(element.get("rotation", 0))
    scale = float(element.get("scale", 1))
    parts = [f"translate({x:.2f} {y:.2f})"]
    if rotation:
        parts.append(f"rotate({rotation:.2f})")
    if scale != 1:
        parts.append(f"scale({scale:.4f})")
    return " ".join(parts)


def make_element(
    kind: str, *, x: float, y: float, rotation: float = 0, scale: float = 1,
    color: str | None = None, layer: int = 10, label: str | None = None,
    props: dict[str, Any] | None = None, transform: str | None = None,
) -> dict[str, Any]:
    return {
        "id": new_id(kind),
        "kind": kind,
        "label": label or default_label(kind),
        "x": x, "y": y, "rotation": rotation, "scale": scale,
        "color": color or default_color(kind),
        "layer": layer,
        "props": props or {},
        "transform": transform or "",
    }
