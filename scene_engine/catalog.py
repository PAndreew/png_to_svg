from __future__ import annotations
from pathlib import Path
from typing import Any
import copy
import json
import re
import xml.etree.ElementTree as ET

ASSET_CATALOG: list[dict[str, Any]] = [
    {"kind": "car", "label": "Car", "category": "vehicles", "description": "Compact passenger vehicle, top-down pictogram.", "defaultColor": "#2563eb"},
    {"kind": "truck", "label": "Truck", "category": "vehicles", "description": "Box truck / heavy vehicle, top-down pictogram.", "defaultColor": "#f97316"},
    {"kind": "bus", "label": "Bus", "category": "vehicles", "description": "Bus pictogram with windows and wheels.", "defaultColor": "#ef4444"},
    {"kind": "pedestrian", "label": "Pedestrian", "category": "actors", "description": "Walking pedestrian icon.", "defaultColor": "#111827"},
    {"kind": "bicycle", "label": "Bicycle", "category": "actors", "description": "Cyclist / bicycle actor.", "defaultColor": "#16a34a"},
    {"kind": "traffic_light", "label": "Traffic Light", "category": "infrastructure", "description": "Traffic signal pole with red/yellow/green lights.", "defaultColor": "#111827"},
    {"kind": "tree", "label": "Tree", "category": "environment", "description": "Simple roadside tree.", "defaultColor": "#16a34a"},
    {"kind": "arrow", "label": "Arrow", "category": "annotations", "description": "Movement arrow, straight or turning.", "defaultColor": "#22c55e"},
    {"kind": "crosswalk", "label": "Crosswalk", "category": "roads", "description": "Zebra crossing marking.", "defaultColor": "#ffffff"},
    {"kind": "road", "label": "Road", "category": "roads", "description": "Straight road segment.", "defaultColor": "#6b7280"},
    {"kind": "intersection", "label": "Intersection", "category": "roads", "description": "Four-way intersection.", "defaultColor": "#6b7280"},
    {"kind": "t_junction", "label": "T-Junction", "category": "roads", "description": "T-junction road layout.", "defaultColor": "#6b7280"},
    {"kind": "roundabout", "label": "Roundabout", "category": "roads", "description": "Roundabout road layout.", "defaultColor": "#6b7280"},
]

ASSET_SPECS: dict[str, dict[str, Any]] = {
    "car": {"footprint": {"width": 88, "height": 52}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "lane", "orientation": "horizontal"},
    "truck": {"footprint": {"width": 120, "height": 56}, "defaultScale": 1.05, "defaultRotation": 0, "placement": "lane", "orientation": "horizontal"},
    "bus": {"footprint": {"width": 120, "height": 56}, "defaultScale": 1.08, "defaultRotation": 0, "placement": "lane", "orientation": "horizontal"},
    "bicycle": {"footprint": {"width": 74, "height": 42}, "defaultScale": 0.95, "defaultRotation": 0, "placement": "lane_edge", "orientation": "horizontal"},
    "pedestrian": {"footprint": {"width": 36, "height": 64}, "defaultScale": 0.9, "defaultRotation": 0, "placement": "sidewalk", "orientation": "vertical"},
    "traffic_light": {"footprint": {"width": 44, "height": 110}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "roadside", "orientation": "vertical"},
    "tree": {"footprint": {"width": 56, "height": 56}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "roadside", "orientation": "vertical"},
    "arrow": {"footprint": {"width": 160, "height": 160}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "annotation", "orientation": "free"},
    "road": {"footprint": {"width": 920, "height": 180}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "layout", "orientation": "horizontal"},
    "intersection": {"footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "layout", "orientation": "cross"},
    "t_junction": {"footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "layout", "orientation": "cross"},
    "roundabout": {"footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "layout", "orientation": "radial"},
    "crosswalk": {"footprint": {"width": 120, "height": 180}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "layout", "orientation": "vertical"},
    "placeholder": {"footprint": {"width": 140, "height": 80}, "defaultScale": 1.0, "defaultRotation": 0, "placement": "free", "orientation": "free"},
}

CUSTOM_ASSETS_PATH = Path(__file__).with_name("custom_assets.json")

DEFAULT_CANVAS = {"width": 1024, "height": 768, "background": "#f8fafc"}
COLOR_WORDS = {
    "red": "#ef4444", "blue": "#2563eb", "green": "#16a34a", "orange": "#f97316",
    "yellow": "#eab308", "purple": "#7c3aed", "black": "#111827", "white": "#ffffff",
    "gray": "#6b7280", "grey": "#6b7280",
}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _parse_number(value: str | None, fallback: float) -> float:
    if value is None:
        return fallback
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return fallback
    try:
        return float(match.group(0))
    except Exception:
        return fallback


def _extract_viewbox(svg_text: str, root: ET.Element) -> tuple[float, float, float, float]:
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [float(part) for part in re.split(r"[\s,]+", viewbox.strip()) if part]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[0], parts[1], parts[2], parts[3]
    width = _parse_number(root.get("width"), 100.0)
    height = _parse_number(root.get("height"), 100.0)
    return 0.0, 0.0, max(width, 1.0), max(height, 1.0)


def _extract_svg_inner_markup(svg_text: str) -> str:
    text = re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg_text.strip(), flags=re.I)
    match = re.search(r"<svg\b[^>]*>(.*)</svg>\s*$", text, flags=re.I | re.S)
    return (match.group(1) if match else "").strip()


def _extract_default_color(root: ET.Element) -> str:
    for element in root.iter():
        fill = element.attrib.get("fill")
        if not fill:
            continue
        value = fill.strip().lower()
        if value in ("none", "transparent"):
            continue
        if re.fullmatch(r"#[0-9a-f]{6}", value):
            return value
        if re.fullmatch(r"#[0-9a-f]{3}", value):
            return "#" + "".join(ch * 2 for ch in value[1:])
    return "#94a3b8"


def _load_custom_assets() -> list[dict[str, Any]]:
    if not CUSTOM_ASSETS_PATH.exists():
        return []
    try:
        data = json.loads(CUSTOM_ASSETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    assets: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = _slugify(str(item.get("kind") or item.get("label") or ""))
        markup = str(item.get("svgMarkup") or "").strip()
        if not kind or not markup:
            continue
        assets.append(
            {
                "kind": kind,
                "label": str(item.get("label") or kind.replace("_", " ").title()),
                "category": str(item.get("category") or "custom"),
                "description": str(item.get("description") or "Saved custom SVG asset."),
                "defaultColor": str(item.get("defaultColor") or "#94a3b8"),
                "svgMarkup": markup,
                "source": "custom",
            }
        )
    return assets


def _merged_catalog() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        item["kind"]: {**copy.deepcopy(item), **copy.deepcopy(ASSET_SPECS.get(item["kind"], {}))}
        for item in ASSET_CATALOG
    }
    for item in _load_custom_assets():
        merged[item["kind"]] = {**copy.deepcopy(item), **copy.deepcopy(ASSET_SPECS.get(item["kind"], {}))}
    return list(merged.values())


def _refresh_allowed_kinds() -> None:
    ALLOWED_KINDS.clear()
    ALLOWED_KINDS.update(item["kind"] for item in _merged_catalog())
    ALLOWED_KINDS.add("placeholder")


ALLOWED_KINDS: set[str] = set()
_refresh_allowed_kinds()


def catalog() -> list[dict[str, Any]]:
    return copy.deepcopy(_merged_catalog())


def save_svg_asset(name: str, svg_text: str, overwrite: bool = False) -> dict[str, Any]:
    label = str(name or "").strip()
    if not label:
        raise ValueError("Asset name is required.")

    kind = _slugify(label)
    if not kind:
        raise ValueError("Asset name must include at least one letter or number.")

    text = str(svg_text or "").strip()
    if not text:
        raise ValueError("SVG content is required.")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid SVG: {exc}") from exc

    if not str(root.tag).endswith("svg"):
        raise ValueError("The uploaded content must be an SVG document.")

    inner_markup = _extract_svg_inner_markup(text)
    if not inner_markup:
        raise ValueError("The SVG does not contain any drawable content.")

    min_x, min_y, width, height = _extract_viewbox(text, root)
    target_size = 160.0
    scale = target_size / max(width, height, 1.0)
    center_x = -(min_x + width / 2)
    center_y = -(min_y + height / 2)
    wrapped_markup = (
        f'<g transform="scale({scale:.6f})">'
        f'<g transform="translate({center_x:.6f} {center_y:.6f})">{inner_markup}</g>'
        f'</g>'
    )

    payload = {
        "kind": kind,
        "label": label,
        "category": "custom",
        "description": f"Saved from canvas SVG: {label}",
        "defaultColor": _extract_default_color(root),
        "svgMarkup": wrapped_markup,
        "source": "custom",
    }

    custom_assets = _load_custom_assets()
    index = next((i for i, item in enumerate(custom_assets) if item["kind"] == kind), None)

    builtin_exists = any(item["kind"] == kind for item in ASSET_CATALOG)
    if index is None and builtin_exists and not overwrite:
        raise FileExistsError(f"An asset named '{label}' already exists.")
    if index is not None and not overwrite:
        raise FileExistsError(f"An asset named '{label}' already exists.")

    if index is None:
        custom_assets.append(payload)
    else:
        custom_assets[index] = payload

    CUSTOM_ASSETS_PATH.write_text(json.dumps(custom_assets, indent=2), encoding="utf-8")
    _refresh_allowed_kinds()
    return copy.deepcopy(payload)


def default_color(kind: str) -> str:
    for item in _merged_catalog():
        if item["kind"] == kind:
            return item["defaultColor"]
    return "#94a3b8"


def default_label(kind: str) -> str:
    for item in _merged_catalog():
        if item["kind"] == kind:
            return item["label"]
    return kind.replace("_", " ").title()


def asset_spec(kind: str) -> dict[str, Any]:
    return copy.deepcopy(ASSET_SPECS.get(kind, ASSET_SPECS.get("placeholder", {})))
