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
    "car": {
        "footprint": {"width": 88, "height": 52}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "lane", "allowedPlacements": ["lane"], "orientation": "horizontal",
        "catalogGroup": "dynamic_topdown", "view": "top", "role": "dynamic", "layerGroup": "traffic",
        "assetClass": "vehicle", "mobility": "vehicle", "sizeBucket": "medium",
    },
    "truck": {
        "footprint": {"width": 120, "height": 56}, "defaultScale": 1.05, "defaultRotation": 0,
        "placement": "lane", "allowedPlacements": ["lane"], "orientation": "horizontal",
        "catalogGroup": "dynamic_topdown", "view": "top", "role": "dynamic", "layerGroup": "traffic",
        "assetClass": "vehicle", "mobility": "vehicle", "sizeBucket": "large",
    },
    "bus": {
        "footprint": {"width": 120, "height": 56}, "defaultScale": 1.08, "defaultRotation": 0,
        "placement": "lane", "allowedPlacements": ["lane"], "orientation": "horizontal",
        "catalogGroup": "dynamic_topdown", "view": "top", "role": "dynamic", "layerGroup": "traffic",
        "assetClass": "vehicle", "mobility": "vehicle", "sizeBucket": "large",
    },
    "bicycle": {
        "footprint": {"width": 74, "height": 42}, "defaultScale": 0.95, "defaultRotation": 0,
        "placement": "lane_edge", "allowedPlacements": ["lane_edge", "lane", "sidewalk"], "orientation": "horizontal",
        "catalogGroup": "dynamic_topdown", "view": "top", "role": "dynamic", "layerGroup": "traffic",
        "assetClass": "cyclist", "mobility": "vehicle", "sizeBucket": "small",
    },
    "pedestrian": {
        "footprint": {"width": 36, "height": 64}, "defaultScale": 0.9, "defaultRotation": 0,
        "placement": "sidewalk", "allowedPlacements": ["sidewalk", "crosswalk", "roadside"], "orientation": "vertical",
        "catalogGroup": "dynamic_topdown", "view": "top", "role": "dynamic", "layerGroup": "actors",
        "assetClass": "human", "mobility": "walker", "sizeBucket": "small",
    },
    "traffic_light": {
        "footprint": {"width": 44, "height": 110}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "roadside", "allowedPlacements": ["roadside", "sidewalk"], "orientation": "vertical",
        "catalogGroup": "static_environment", "view": "top", "role": "static", "layerGroup": "environment",
        "assetClass": "roadside_object", "mobility": "static", "sizeBucket": "medium",
    },
    "tree": {
        "footprint": {"width": 56, "height": 56}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "roadside", "allowedPlacements": ["roadside", "sidewalk"], "orientation": "vertical",
        "catalogGroup": "static_environment", "view": "top", "role": "static", "layerGroup": "environment",
        "assetClass": "roadside_object", "mobility": "static", "sizeBucket": "medium",
    },
    "arrow": {
        "footprint": {"width": 160, "height": 160}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "annotation", "allowedPlacements": ["annotation"], "orientation": "free",
        "catalogGroup": "annotations", "view": "top", "role": "annotation", "layerGroup": "annotations",
        "assetClass": "annotation", "mobility": "annotation", "sizeBucket": "medium",
    },
    "road": {
        "footprint": {"width": 920, "height": 180}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "layout", "allowedPlacements": ["layout"], "orientation": "horizontal",
        "catalogGroup": "layout_assets", "view": "top", "role": "layout", "layerGroup": "layout",
        "assetClass": "road_feature", "mobility": "static", "sizeBucket": "xlarge",
    },
    "intersection": {
        "footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "layout", "allowedPlacements": ["layout"], "orientation": "cross",
        "catalogGroup": "layout_assets", "view": "top", "role": "layout", "layerGroup": "layout",
        "assetClass": "road_feature", "mobility": "static", "sizeBucket": "xlarge",
    },
    "t_junction": {
        "footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "layout", "allowedPlacements": ["layout"], "orientation": "cross",
        "catalogGroup": "layout_assets", "view": "top", "role": "layout", "layerGroup": "layout",
        "assetClass": "road_feature", "mobility": "static", "sizeBucket": "xlarge",
    },
    "roundabout": {
        "footprint": {"width": 840, "height": 640}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "layout", "allowedPlacements": ["layout"], "orientation": "radial",
        "catalogGroup": "layout_assets", "view": "top", "role": "layout", "layerGroup": "layout",
        "assetClass": "road_feature", "mobility": "static", "sizeBucket": "xlarge",
    },
    "crosswalk": {
        "footprint": {"width": 120, "height": 180}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "layout", "allowedPlacements": ["layout"], "orientation": "vertical",
        "catalogGroup": "layout_assets", "view": "top", "role": "layout", "layerGroup": "layout",
        "assetClass": "road_feature", "mobility": "static", "sizeBucket": "medium",
    },
    "placeholder": {
        "footprint": {"width": 140, "height": 80}, "defaultScale": 1.0, "defaultRotation": 0,
        "placement": "free", "allowedPlacements": ["free", "roadside", "sidewalk"], "orientation": "free",
        "catalogGroup": "props_objects", "view": "top", "role": "object", "layerGroup": "props",
        "assetClass": "object", "mobility": "static", "sizeBucket": "medium",
    },
}

LAYER_GROUP_ORDER = {
    "layout": 0,
    "environment": 4,
    "traffic": 10,
    "actors": 12,
    "props": 16,
    "annotations": 20,
}

UNIT_LONG_SIDE = 100.0
ORIENTATION_ROTATION = {"right": 0.0, "up": 90.0, "left": 180.0, "down": -90.0}

CUSTOM_ASSETS_PATH = Path(__file__).with_name("custom_assets.json")

DEFAULT_CANVAS = {"width": 1024, "height": 768, "background": "#f8fafc"}
COLOR_WORDS = {
    "red": "#ef4444", "blue": "#2563eb", "green": "#16a34a", "orange": "#f97316",
    "yellow": "#eab308", "purple": "#7c3aed", "black": "#111827", "white": "#ffffff",
    "gray": "#6b7280", "grey": "#6b7280",
}
RESERVED_BUILTIN_KINDS = {"road", "crosswalk", "intersection", "t_junction", "roundabout"}


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
        label = str(item.get("label") or kind.replace("_", " ").title())
        inferred = _infer_custom_semantics(
            label,
            footprint=item.get("footprint") if isinstance(item.get("footprint"), dict) else None,
        )
        assets.append(
            {
                "kind": kind,
                "label": label,
                "category": str(item.get("category") or inferred["category"]),
                "description": str(item.get("description") or "Saved custom SVG asset."),
                "defaultColor": str(item.get("defaultColor") or "#94a3b8"),
                "svgMarkup": markup,
                "source": "custom",
                "footprint": copy.deepcopy(item.get("footprint") or {"width": UNIT_LONG_SIDE, "height": UNIT_LONG_SIDE}),
                "defaultScale": float(item.get("defaultScale") or 1.0),
                "defaultRotation": float(item.get("defaultRotation") or 0.0),
                "placement": str(item.get("placement") or inferred["placement"]),
                "allowedPlacements": list(item.get("allowedPlacements") or inferred["allowedPlacements"]),
                "orientation": str(item.get("orientation") or "right"),
                "sourceOrientation": str(item.get("sourceOrientation") or item.get("orientation") or "right"),
                "unitLongSide": float(item.get("unitLongSide") or UNIT_LONG_SIDE),
                "sizeBucket": str(item.get("sizeBucket") or inferred["sizeBucket"]),
                "catalogGroup": str(item.get("catalogGroup") or inferred["catalogGroup"]),
                "view": str(item.get("view") or inferred["view"]),
                "role": str(item.get("role") or inferred["role"]),
                "layerGroup": str(item.get("layerGroup") or inferred["layerGroup"]),
                "assetClass": str(item.get("assetClass") or inferred["assetClass"]),
                "mobility": str(item.get("mobility") or inferred["mobility"]),
                "layer": int(item.get("layer") or LAYER_GROUP_ORDER.get(str(item.get("layerGroup") or inferred["layerGroup"]), 16)),
            }
        )
    return assets


def _infer_custom_semantics(label: str, footprint: dict[str, Any] | None = None) -> dict[str, Any]:
    text = label.lower()
    width = float((footprint or {}).get("width") or UNIT_LONG_SIDE)
    height = float((footprint or {}).get("height") or UNIT_LONG_SIDE)
    aspect = width / max(height, 1.0)
    view = "side" if any(term in text for term in ["side", "profile", "lateral"]) else "top"
    rules = [
        (("truck", "lorry"), {"category": "vehicles", "placement": "lane", "allowedPlacements": ["lane"], "sizeBucket": "large", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "traffic", "assetClass": "vehicle", "mobility": "vehicle"}),
        (("bus",), {"category": "vehicles", "placement": "lane", "allowedPlacements": ["lane"], "sizeBucket": "large", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "traffic", "assetClass": "vehicle", "mobility": "vehicle"}),
        (("car", "vehicle", "van"), {"category": "vehicles", "placement": "lane", "allowedPlacements": ["lane"], "sizeBucket": "medium", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "traffic", "assetClass": "vehicle", "mobility": "vehicle"}),
        (("bike", "bicycle", "cyclist"), {"category": "actors", "placement": "lane_edge", "allowedPlacements": ["lane_edge", "lane", "sidewalk"], "sizeBucket": "small", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "traffic", "assetClass": "cyclist", "mobility": "vehicle"}),
        (("pedestrian", "person", "walker", "human", "child"), {"category": "actors", "placement": "sidewalk", "allowedPlacements": ["sidewalk", "crosswalk", "roadside"], "sizeBucket": "small", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "actors", "assetClass": "human", "mobility": "walker"}),
        (("cat", "dog", "animal", "pet"), {"category": "actors", "placement": "sidewalk", "allowedPlacements": ["sidewalk", "crosswalk", "roadside"], "sizeBucket": "small", "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "actors", "assetClass": "animal", "mobility": "walker"}),
        (("tree", "pole", "sign", "light", "lamp"), {"category": "infrastructure", "placement": "roadside", "allowedPlacements": ["roadside", "sidewalk"], "sizeBucket": "medium", "catalogGroup": "static_environment", "view": view, "role": "static", "layerGroup": "environment", "assetClass": "roadside_object", "mobility": "static"}),
        (("road", "lane", "intersection", "junction", "roundabout", "crosswalk"), {"category": "roads", "placement": "layout", "allowedPlacements": ["layout"], "sizeBucket": "xlarge", "catalogGroup": "layout_assets", "view": view, "role": "layout", "layerGroup": "layout", "assetClass": "road_feature", "mobility": "static"}),
        (("arrow",), {"category": "annotations", "placement": "annotation", "allowedPlacements": ["annotation"], "sizeBucket": "medium", "catalogGroup": "annotations", "view": view, "role": "annotation", "layerGroup": "annotations", "assetClass": "annotation", "mobility": "annotation"}),
    ]
    for terms, payload in rules:
        if any(term in text for term in terms):
            return dict(payload)
    if aspect >= 4.0:
        return {
            "category": "roads", "placement": "layout", "allowedPlacements": ["layout"], "sizeBucket": "xlarge",
            "catalogGroup": "layout_assets", "view": view, "role": "layout", "layerGroup": "layout",
            "assetClass": "road_feature", "mobility": "static",
        }
    if aspect >= 1.75:
        return {
            "category": "objects", "placement": "lane", "allowedPlacements": ["lane", "free"], "sizeBucket": "medium",
            "catalogGroup": "dynamic_sideview" if view == "side" else "dynamic_topdown", "view": view, "role": "dynamic", "layerGroup": "traffic",
            "assetClass": "vehicle", "mobility": "vehicle",
        }
    if height > width * 1.35:
        return {
            "category": "objects", "placement": "roadside", "allowedPlacements": ["roadside", "sidewalk", "free"], "sizeBucket": "medium",
            "catalogGroup": "static_environment", "view": view, "role": "static", "layerGroup": "environment",
            "assetClass": "roadside_object", "mobility": "static",
        }
    return {
        "category": "custom", "placement": "free", "allowedPlacements": ["free", "roadside", "sidewalk"], "sizeBucket": "medium",
        "catalogGroup": "props_objects", "view": view, "role": "object", "layerGroup": "props",
        "assetClass": "object", "mobility": "static",
    }


def _merged_catalog() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        item["kind"]: {**copy.deepcopy(item), **copy.deepcopy(ASSET_SPECS.get(item["kind"], {}))}
        for item in ASSET_CATALOG
    }
    for item in _load_custom_assets():
        if item["kind"] in RESERVED_BUILTIN_KINDS:
            continue
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


def catalog_by_group() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "layout_assets": [],
        "static_environment": [],
        "dynamic_topdown": [],
        "dynamic_sideview": [],
        "props_objects": [],
        "annotations": [],
    }
    for item in _merged_catalog():
        key = str(item.get("catalogGroup") or "props_objects")
        grouped.setdefault(key, []).append(copy.deepcopy(item))
    return grouped


def save_svg_asset(
    name: str,
    svg_text: str,
    overwrite: bool = False,
    orientation: str = "right",
) -> dict[str, Any]:
    label = str(name or "").strip()
    if not label:
        raise ValueError("Asset name is required.")

    kind = _slugify(label)
    if not kind:
        raise ValueError("Asset name must include at least one letter or number.")

    text = str(svg_text or "").strip()
    if not text:
        raise ValueError("SVG content is required.")

    normalized_orientation = str(orientation or "right").strip().lower()
    if normalized_orientation not in ORIENTATION_ROTATION:
        raise ValueError("Orientation must be one of: right, up, left, down.")

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
    rotation = ORIENTATION_ROTATION[normalized_orientation]
    rotated_width = height if int(abs(rotation)) in {90, 270} else width
    rotated_height = width if int(abs(rotation)) in {90, 270} else height
    scale = UNIT_LONG_SIDE / max(rotated_width, rotated_height, 1.0)
    center_x = -(min_x + width / 2)
    center_y = -(min_y + height / 2)
    wrapped_markup = (
        f'<g transform="scale({scale:.6f})">'
        f'<g transform="rotate({rotation:.6f})">'
        f'<g transform="translate({center_x:.6f} {center_y:.6f})">{inner_markup}</g>'
        f'</g>'
        f'</g>'
    )

    normalized_width = round(rotated_width * scale, 4)
    normalized_height = round(rotated_height * scale, 4)
    semantics = _infer_custom_semantics(label, footprint={"width": normalized_width, "height": normalized_height})

    payload = {
        "kind": kind,
        "label": label,
        "category": semantics["category"],
        "description": f"Saved from canvas SVG: {label}",
        "defaultColor": _extract_default_color(root),
        "svgMarkup": wrapped_markup,
        "source": "custom",
        "footprint": {"width": normalized_width, "height": normalized_height},
        "defaultScale": 1.0,
        "defaultRotation": 0.0,
        "placement": semantics["placement"],
        "allowedPlacements": list(semantics["allowedPlacements"]),
        "orientation": "right",
        "sourceOrientation": normalized_orientation,
        "unitLongSide": UNIT_LONG_SIDE,
        "sizeBucket": semantics["sizeBucket"],
        "catalogGroup": semantics["catalogGroup"],
        "view": semantics["view"],
        "role": semantics["role"],
        "layerGroup": semantics["layerGroup"],
        "assetClass": semantics["assetClass"],
        "mobility": semantics["mobility"],
        "layer": LAYER_GROUP_ORDER.get(semantics["layerGroup"], 16),
    }

    custom_assets = _load_custom_assets()
    index = next((i for i, item in enumerate(custom_assets) if item["kind"] == kind), None)

    builtin_exists = any(item["kind"] == kind for item in ASSET_CATALOG)
    if builtin_exists and kind in RESERVED_BUILTIN_KINDS:
        raise FileExistsError(f"'{label}' is a reserved built-in layout asset name.")
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
    for item in _merged_catalog():
        if item["kind"] == kind:
            spec = {
                "footprint": copy.deepcopy(item.get("footprint") or {}),
                "defaultScale": item.get("defaultScale", 1.0),
                "defaultRotation": item.get("defaultRotation", 0.0),
                "placement": item.get("placement", "free"),
                "allowedPlacements": copy.deepcopy(item.get("allowedPlacements") or [item.get("placement", "free")]),
                "orientation": item.get("orientation", "right"),
                "sizeBucket": item.get("sizeBucket", "medium"),
                "catalogGroup": item.get("catalogGroup", "props_objects"),
                "view": item.get("view", "top"),
                "role": item.get("role", "object"),
                "layerGroup": item.get("layerGroup", "props"),
                "assetClass": item.get("assetClass", "object"),
                "mobility": item.get("mobility", "static"),
                "layer": item.get("layer", LAYER_GROUP_ORDER.get(str(item.get("layerGroup") or "props"), 16)),
            }
            return spec
    return copy.deepcopy(ASSET_SPECS.get(kind, ASSET_SPECS.get("placeholder", {})))
