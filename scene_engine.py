from __future__ import annotations

import copy
import json
import math
import re
import uuid
from collections import Counter
from typing import Any

SVG_NS = "http://www.w3.org/2000/svg"

ASSET_CATALOG: list[dict[str, Any]] = [
    {
        "kind": "car",
        "label": "Car",
        "category": "vehicles",
        "description": "Compact passenger vehicle, top-down pictogram.",
        "defaultColor": "#2563eb",
    },
    {
        "kind": "truck",
        "label": "Truck",
        "category": "vehicles",
        "description": "Box truck / heavy vehicle, top-down pictogram.",
        "defaultColor": "#f97316",
    },
    {
        "kind": "bus",
        "label": "Bus",
        "category": "vehicles",
        "description": "Bus pictogram with windows and wheels.",
        "defaultColor": "#ef4444",
    },
    {
        "kind": "pedestrian",
        "label": "Pedestrian",
        "category": "actors",
        "description": "Walking pedestrian icon.",
        "defaultColor": "#111827",
    },
    {
        "kind": "bicycle",
        "label": "Bicycle",
        "category": "actors",
        "description": "Cyclist / bicycle actor.",
        "defaultColor": "#16a34a",
    },
    {
        "kind": "traffic_light",
        "label": "Traffic Light",
        "category": "infrastructure",
        "description": "Traffic signal pole with red/yellow/green lights.",
        "defaultColor": "#111827",
    },
    {
        "kind": "tree",
        "label": "Tree",
        "category": "environment",
        "description": "Simple roadside tree.",
        "defaultColor": "#16a34a",
    },
    {
        "kind": "arrow",
        "label": "Arrow",
        "category": "annotations",
        "description": "Movement arrow, straight or turning.",
        "defaultColor": "#22c55e",
    },
    {
        "kind": "crosswalk",
        "label": "Crosswalk",
        "category": "roads",
        "description": "Zebra crossing marking.",
        "defaultColor": "#ffffff",
    },
    {
        "kind": "road",
        "label": "Road",
        "category": "roads",
        "description": "Straight road segment.",
        "defaultColor": "#6b7280",
    },
    {
        "kind": "intersection",
        "label": "Intersection",
        "category": "roads",
        "description": "Four-way intersection.",
        "defaultColor": "#6b7280",
    },
    {
        "kind": "t_junction",
        "label": "T-Junction",
        "category": "roads",
        "description": "T-junction road layout.",
        "defaultColor": "#6b7280",
    },
    {
        "kind": "roundabout",
        "label": "Roundabout",
        "category": "roads",
        "description": "Roundabout road layout.",
        "defaultColor": "#6b7280",
    },
]

DEFAULT_CANVAS = {"width": 1024, "height": 768, "background": "#f8fafc"}
ALLOWED_KINDS = {item["kind"] for item in ASSET_CATALOG} | {"placeholder"}
COLOR_WORDS = {
    "red": "#ef4444",
    "blue": "#2563eb",
    "green": "#16a34a",
    "orange": "#f97316",
    "yellow": "#eab308",
    "purple": "#7c3aed",
    "black": "#111827",
    "white": "#ffffff",
    "gray": "#6b7280",
    "grey": "#6b7280",
}


def catalog() -> list[dict[str, Any]]:
    return copy.deepcopy(ASSET_CATALOG)


def default_scene() -> dict[str, Any]:
    return {
        "version": "odd.scene.v1",
        "canvas": copy.deepcopy(DEFAULT_CANVAS),
        "title": "ODD pictogram",
        "prompt": "",
        "warnings": [],
        "elements": [],
    }


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def xml_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compact_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def deep_copy_scene(scene: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(scene) if scene else default_scene()


def normalize_scene(scene: dict[str, Any] | None) -> dict[str, Any]:
    normalized = default_scene()
    if scene:
        normalized.update({k: v for k, v in scene.items() if k != "canvas"})
        if isinstance(scene.get("canvas"), dict):
            normalized["canvas"].update(scene["canvas"])

    normalized["canvas"]["width"] = clamp_number(
        normalized["canvas"].get("width", 1024), 640, 1600, 1024
    )
    normalized["canvas"]["height"] = clamp_number(
        normalized["canvas"].get("height", 768), 480, 1200, 768
    )
    normalized["canvas"]["background"] = ensure_color(
        normalized["canvas"].get("background", "#f8fafc"), "#f8fafc"
    )
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
            normalized["warnings"].append(
                f"Unknown asset '{kind}' rendered as placeholder."
            )
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

    normalized["elements"] = sorted(
        elements, key=lambda item: (item.get("layer", 10), item["id"])
    )
    return normalized


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


def default_color(kind: str) -> str:
    for item in ASSET_CATALOG:
        if item["kind"] == kind:
            return item["defaultColor"]
    return "#94a3b8"


def default_label(kind: str) -> str:
    return kind.replace("_", " ").title()


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
    kind: str,
    *,
    x: float,
    y: float,
    rotation: float = 0,
    scale: float = 1,
    color: str | None = None,
    layer: int = 10,
    label: str | None = None,
    props: dict[str, Any] | None = None,
    transform: str | None = None,
) -> dict[str, Any]:
    return {
        "id": new_id(kind),
        "kind": kind,
        "label": label or default_label(kind),
        "x": x,
        "y": y,
        "rotation": rotation,
        "scale": scale,
        "color": color or default_color(kind),
        "layer": layer,
        "props": props or {},
        "transform": transform or "",
    }


def generate_scene_heuristic(
    prompt: str,
    history: list[dict[str, Any]] | None = None,
    current_scene: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    text = " ".join(
        str(part)
        for part in [
            *(entry.get("content", "") for entry in (history or [])[-4:]),
            prompt,
        ]
    ).lower()

    scene = deep_copy_scene(current_scene)
    if not current_scene or looks_like_new_scene(prompt):
        scene = default_scene()
        layout = detect_layout(text)
        scene["elements"] = build_layout(layout)
        scene["warnings"] = []
    else:
        scene = normalize_scene(scene)

    scene["prompt"] = prompt
    scene["title"] = build_title(prompt)
    warnings = list(scene.get("warnings") or [])

    apply_prompt_modifiers(scene, prompt, warnings)

    if not has_actor(scene):
        add_default_actor(scene, prompt)

    if needs_arrow(prompt, scene):
        ensure_motion_arrow(scene, prompt)

    infer_environment(scene, prompt)
    normalized = normalize_scene(scene)
    normalized["warnings"] = dedupe_strings(warnings + normalized.get("warnings", []))
    return normalized, normalized["warnings"]


def looks_like_new_scene(prompt: str) -> bool:
    text = prompt.lower()
    return any(
        key in text
        for key in [
            "new scene",
            "start over",
            "reset",
            "generate",
            "create",
            "show",
            "draw",
        ]
    ) or not any(
        key in text for key in ["add", "remove", "delete", "also", "refine", "update"]
    )


def detect_layout(text: str) -> str:
    if any(term in text for term in ["roundabout", "traffic circle"]):
        return "roundabout"
    if any(term in text for term in ["t-junction", "t junction", "t-intersection"]):
        return "t_junction"
    if any(term in text for term in ["intersection", "crossroad", "four-way"]):
        return "intersection"
    if any(
        term in text for term in ["crosswalk", "pedestrian crossing", "zebra crossing"]
    ):
        return "crosswalk"
    return "straight"


def build_layout(layout: str) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    if layout == "intersection":
        elements.append(make_element("intersection", x=512, y=384, layer=0, scale=1.0))
    elif layout == "t_junction":
        elements.append(make_element("t_junction", x=512, y=404, layer=0, scale=1.0))
    elif layout == "roundabout":
        elements.append(make_element("roundabout", x=512, y=384, layer=0, scale=1.0))
    elif layout == "crosswalk":
        elements.append(
            make_element(
                "road", x=512, y=384, layer=0, props={"length": 900, "width": 180}
            )
        )
        elements.append(
            make_element(
                "crosswalk", x=512, y=384, layer=2, props={"length": 120, "width": 180}
            )
        )
    else:
        elements.append(
            make_element(
                "road", x=512, y=384, layer=0, props={"length": 920, "width": 180}
            )
        )
    return elements


def build_title(prompt: str) -> str:
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt[:80] if prompt else "ODD pictogram"


def apply_prompt_modifiers(
    scene: dict[str, Any], prompt: str, warnings: list[str]
) -> None:
    text = prompt.lower()
    if any(term in text for term in ["remove truck", "delete truck"]):
        remove_first(scene, "truck")
    if any(term in text for term in ["remove bus", "delete bus"]):
        remove_first(scene, "bus")
    if any(term in text for term in ["remove pedestrian", "delete pedestrian"]):
        remove_first(scene, "pedestrian")

    if "overtak" in text:
        ensure_overtake(scene)
    elif any(term in text for term in ["truck", "lorry"]):
        ensure_actor(scene, "truck", x=620, y=384, rotation=180, scale=1.0)
    elif "bus" in text:
        ensure_actor(scene, "bus", x=640, y=384, rotation=180, scale=1.0)

    if any(term in text for term in ["pedestrian", "walker"]):
        ensure_actor(scene, "pedestrian", x=520, y=360, rotation=0, scale=1.0)
    if any(term in text for term in ["bicycle", "cyclist", "bike"]):
        ensure_actor(scene, "bicycle", x=450, y=330, rotation=0, scale=1.0)
    if any(term in text for term in ["traffic light", "traffic signal"]):
        ensure_actor(
            scene, "traffic_light", x=740, y=250, rotation=0, scale=1.0, layer=5
        )
    if any(term in text for term in ["tree", "trees", "roadside tree"]):
        ensure_actor(scene, "tree", x=160, y=180, rotation=0, scale=1.0, layer=1)
        ensure_actor(scene, "tree", x=870, y=610, rotation=0, scale=1.0, layer=1)

    if any(term in text for term in ["ego", "car", "vehicle"]):
        ensure_primary_car(scene, prompt)

    apply_color_hints(scene, text)

    if "inclin" in text or "slope" in text or "hill" in text:
        warnings.append(
            "Inclined-road phrasing was approximated with a flat top-down pictogram."
        )
    if any(term in text for term in ["animal", "tram", "train", "construction crane"]):
        warnings.append(
            "One or more requested assets are not in the local catalogue and may need manual editing."
        )
        scene["elements"].append(
            make_element(
                "placeholder",
                x=780,
                y=180,
                layer=12,
                label="Missing asset",
                props={"text": "Missing asset"},
            )
        )


def apply_color_hints(scene: dict[str, Any], text: str) -> None:
    mentioned = [
        name
        for name in COLOR_WORDS
        if f"{name} car" in text or f"{name} truck" in text or f"{name} bus" in text
    ]
    if not mentioned:
        return
    for element in scene.get("elements", []):
        if element["kind"] in {"car", "truck", "bus"}:
            for name in mentioned:
                if (
                    f"{name} {element['kind']}" in text
                    or f"{name} vehicle" in text
                    or f"{name} car" in text
                ):
                    element["color"] = COLOR_WORDS[name]
                    break


def has_actor(scene: dict[str, Any]) -> bool:
    return any(
        el["kind"] in {"car", "truck", "bus", "pedestrian", "bicycle"}
        for el in scene.get("elements", [])
    )


def add_default_actor(scene: dict[str, Any], prompt: str) -> None:
    ensure_primary_car(scene, prompt)


def ensure_primary_car(scene: dict[str, Any], prompt: str) -> None:
    text = prompt.lower()
    layout = current_layout_kind(scene)
    x, y, rotation = 300, 384, 0
    if layout == "roundabout":
        x, y, rotation = 512, 210, 90
    elif layout == "intersection":
        x, y, rotation = 300, 384, 0
    elif layout == "t_junction":
        x, y, rotation = 330, 404, 0
    elif layout == "crosswalk":
        x, y, rotation = 300, 384, 0

    if "turn left" in text or "turning left" in text:
        x, y, rotation = (
            420,
            470,
            -90 if layout in {"intersection", "t_junction"} else 0,
        )
    elif "turn right" in text or "turning right" in text:
        x, y, rotation = 420, 300, 90 if layout in {"intersection", "t_junction"} else 0

    ensure_actor(scene, "car", x=x, y=y, rotation=rotation, scale=1.0)


def ensure_actor(
    scene: dict[str, Any],
    kind: str,
    *,
    x: float,
    y: float,
    rotation: float,
    scale: float,
    layer: int = 10,
) -> dict[str, Any]:
    for element in scene.get("elements", []):
        if element["kind"] == kind:
            return element
    element = make_element(kind, x=x, y=y, rotation=rotation, scale=scale, layer=layer)
    scene.setdefault("elements", []).append(element)
    return element


def ensure_overtake(scene: dict[str, Any]) -> None:
    car = ensure_actor(scene, "car", x=350, y=415, rotation=0, scale=1.0)
    car["color"] = car.get("color") or "#2563eb"
    second = None
    for element in scene.get("elements", []):
        if element["kind"] == "truck":
            second = element
            break
    if not second:
        second = make_element("truck", x=520, y=360, rotation=0, scale=1.0, layer=10)
        scene["elements"].append(second)
    second["rotation"] = 0
    second["x"] = 520
    second["y"] = 360


def remove_first(scene: dict[str, Any], kind: str) -> None:
    elements = scene.get("elements", [])
    for index, element in enumerate(elements):
        if element.get("kind") == kind:
            elements.pop(index)
            return


def current_layout_kind(scene: dict[str, Any]) -> str:
    for kind in ["roundabout", "intersection", "t_junction", "road", "crosswalk"]:
        if any(el["kind"] == kind for el in scene.get("elements", [])):
            return kind
    return "road"


def needs_arrow(prompt: str, scene: dict[str, Any]) -> bool:
    text = prompt.lower()
    return any(
        term in text
        for term in [
            "turn",
            "merge",
            "overtak",
            "arrow",
            "changing lane",
            "lane change",
        ]
    )


def ensure_motion_arrow(scene: dict[str, Any], prompt: str) -> None:
    text = prompt.lower()
    style = "straight"
    x, y, rotation = 300, 300, 0
    if "left" in text:
        style = "left"
        x, y = 420, 390
    elif "right" in text:
        style = "right"
        x, y = 420, 290
    elif "u-turn" in text or "u turn" in text:
        style = "uturn"
        x, y = 480, 290
    elif "overtak" in text or "lane change" in text:
        style = "merge"
        x, y = 390, 350

    arrow = None
    for element in scene.get("elements", []):
        if element["kind"] == "arrow":
            arrow = element
            break
    if not arrow:
        arrow = make_element("arrow", x=x, y=y, rotation=rotation, scale=1.0, layer=20)
        scene["elements"].append(arrow)
    arrow["props"] = dict(arrow.get("props") or {}, style=style, length=140)
    arrow["color"] = "#22c55e"
    arrow["x"] = x
    arrow["y"] = y


def infer_environment(scene: dict[str, Any], prompt: str) -> None:
    text = prompt.lower()
    if any(
        term in text for term in ["crosswalk", "pedestrian crossing", "zebra crossing"]
    ):
        if not any(el["kind"] == "crosswalk" for el in scene.get("elements", [])):
            scene["elements"].append(
                make_element(
                    "crosswalk",
                    x=520,
                    y=384,
                    layer=3,
                    props={"length": 120, "width": 180},
                )
            )
    if any(term in text for term in ["traffic light", "traffic signal"]):
        ensure_actor(
            scene, "traffic_light", x=760, y=250, rotation=0, scale=1.0, layer=5
        )


def dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def render_scene_svg(scene: dict[str, Any]) -> str:
    scene = normalize_scene(scene)
    canvas = scene["canvas"]
    width = int(canvas["width"])
    height = int(canvas["height"])
    background = canvas["background"]

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="{SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" fill="{xml_escape(background)}"/>',
    ]

    for element in scene["elements"]:
        parts.append(render_element(element))

    parts.append("</svg>")
    return "\n".join(parts)


def render_element(element: dict[str, Any]) -> str:
    renderer = {
        "road": render_road,
        "intersection": render_intersection,
        "t_junction": render_t_junction,
        "roundabout": render_roundabout,
        "crosswalk": render_crosswalk,
        "car": render_car,
        "truck": render_truck,
        "bus": render_bus,
        "pedestrian": render_pedestrian,
        "bicycle": render_bicycle,
        "traffic_light": render_traffic_light,
        "tree": render_tree,
        "arrow": render_arrow,
        "placeholder": render_placeholder,
    }.get(element["kind"], render_placeholder)

    inner = renderer(element)
    attrs = {
        "class": "scene-asset",
        "data-scene-id": element["id"],
        "data-kind": element["kind"],
        "data-label": element.get("label", default_label(element["kind"])),
        "transform": build_transform(element),
    }
    attr_text = " ".join(f'{key}="{xml_escape(value)}"' for key, value in attrs.items())
    return f"<g {attr_text}>{inner}</g>"


def render_road(element: dict[str, Any]) -> str:
    props = element.get("props") or {}
    length = clamp_number(props.get("length", 920), 180, 1400, 920)
    width = clamp_number(props.get("width", 180), 80, 340, 180)
    lane_count = int(clamp_number(props.get("lanes", 2), 1, 4, 2))
    shoulder = width / 2
    markings = []
    if lane_count >= 2:
        markings.append(
            f'<line x1="{-length/2+24:.1f}" y1="0" x2="{length/2-24:.1f}" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"/>'
        )
    edge_y = shoulder - 14
    markings.append(
        f'<line x1="{-length/2+20:.1f}" y1="{-edge_y:.1f}" x2="{length/2-20:.1f}" y2="{-edge_y:.1f}" stroke="#d1d5db" stroke-width="3" opacity="0.55"/>'
    )
    markings.append(
        f'<line x1="{-length/2+20:.1f}" y1="{edge_y:.1f}" x2="{length/2-20:.1f}" y2="{edge_y:.1f}" stroke="#d1d5db" stroke-width="3" opacity="0.55"/>'
    )
    return (
        f'<rect x="{-length/2:.1f}" y="{-width/2:.1f}" width="{length:.1f}" height="{width:.1f}" rx="28" fill="#6b7280"/>\n'
        + "\n".join(markings)
    )


def render_intersection(element: dict[str, Any]) -> str:
    base = [
        '<rect x="-420" y="-92" width="840" height="184" rx="28" fill="#6b7280"/>',
        '<rect x="-92" y="-320" width="184" height="640" rx="28" fill="#6b7280"/>',
        '<line x1="-390" y1="0" x2="390" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"/>',
        '<line x1="0" y1="-290" x2="0" y2="290" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"/>',
    ]
    return "\n".join(base)


def render_t_junction(element: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<rect x="-420" y="-92" width="840" height="184" rx="28" fill="#6b7280"/>',
            '<rect x="146" y="-320" width="184" height="320" rx="28" fill="#6b7280"/>',
            '<line x1="-390" y1="0" x2="120" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"/>',
            '<line x1="238" y1="-290" x2="238" y2="-30" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"/>',
        ]
    )


def render_roundabout(element: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<circle cx="0" cy="0" r="170" fill="#6b7280"/>',
            '<circle cx="0" cy="0" r="78" fill="#f8fafc"/>',
            '<circle cx="0" cy="0" r="42" fill="#86efac" stroke="#16a34a" stroke-width="8"/>',
            '<rect x="-420" y="-46" width="220" height="92" rx="26" fill="#6b7280"/>',
            '<rect x="200" y="-46" width="220" height="92" rx="26" fill="#6b7280"/>',
            '<rect x="-46" y="-320" width="92" height="170" rx="26" fill="#6b7280"/>',
            '<rect x="-46" y="150" width="92" height="170" rx="26" fill="#6b7280"/>',
        ]
    )


def render_crosswalk(element: dict[str, Any]) -> str:
    props = element.get("props") or {}
    length = clamp_number(props.get("length", 120), 60, 220, 120)
    width = clamp_number(props.get("width", 180), 80, 260, 180)
    stripes = []
    stripe_count = 6
    stripe_w = length / (stripe_count * 1.6)
    start_x = -length / 2
    for i in range(stripe_count):
        x = start_x + i * stripe_w * 1.6
        stripes.append(
            f'<rect x="{x:.1f}" y="{-width/2:.1f}" width="{stripe_w:.1f}" height="{width:.1f}" fill="#f8fafc" opacity="0.96"/>'
        )
    return "\n".join(stripes)


def render_car(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#2563eb")
    return "\n".join(
        [
            f'<rect x="-44" y="-22" width="88" height="44" rx="12" fill="{color}" stroke="#111827" stroke-width="4"/>',
            '<rect x="-24" y="-15" width="48" height="30" rx="8" fill="#dbeafe" stroke="#111827" stroke-width="3"/>',
            '<circle cx="-28" cy="-26" r="7" fill="#111827"/>',
            '<circle cx="28" cy="-26" r="7" fill="#111827"/>',
            '<circle cx="-28" cy="26" r="7" fill="#111827"/>',
            '<circle cx="28" cy="26" r="7" fill="#111827"/>',
        ]
    )


def render_truck(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#f97316")
    return "\n".join(
        [
            f'<rect x="-62" y="-24" width="78" height="48" rx="10" fill="{color}" stroke="#111827" stroke-width="4"/>',
            '<rect x="16" y="-20" width="42" height="40" rx="8" fill="#fde68a" stroke="#111827" stroke-width="4"/>',
            '<rect x="22" y="-14" width="22" height="14" rx="4" fill="#dbeafe" stroke="#111827" stroke-width="2.5"/>',
            '<circle cx="-40" cy="-28" r="8" fill="#111827"/>',
            '<circle cx="-4" cy="-28" r="8" fill="#111827"/>',
            '<circle cx="22" cy="-28" r="8" fill="#111827"/>',
            '<circle cx="-40" cy="28" r="8" fill="#111827"/>',
            '<circle cx="-4" cy="28" r="8" fill="#111827"/>',
            '<circle cx="22" cy="28" r="8" fill="#111827"/>',
        ]
    )


def render_bus(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#ef4444")
    windows = []
    for i in range(4):
        windows.append(
            f'<rect x="{-38 + i * 20}" y="-14" width="14" height="16" rx="3" fill="#dbeafe" stroke="#111827" stroke-width="2"/>'
        )
    return "\n".join(
        [
            f'<rect x="-60" y="-24" width="120" height="48" rx="12" fill="{color}" stroke="#111827" stroke-width="4"/>',
            *windows,
            '<circle cx="-36" cy="-28" r="8" fill="#111827"/>',
            '<circle cx="36" cy="-28" r="8" fill="#111827"/>',
            '<circle cx="-36" cy="28" r="8" fill="#111827"/>',
            '<circle cx="36" cy="28" r="8" fill="#111827"/>',
        ]
    )


def render_pedestrian(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#111827")
    return "\n".join(
        [
            f'<circle cx="0" cy="-22" r="11" fill="{color}"/>',
            f'<path d="M 0 -10 L 0 18 M -18 0 L 0 -2 L 16 10 M -14 40 L 0 18 L 16 42" stroke="{color}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
        ]
    )


def render_bicycle(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#16a34a")
    return "\n".join(
        [
            '<circle cx="-26" cy="18" r="17" fill="none" stroke="#111827" stroke-width="5"/>',
            '<circle cx="30" cy="18" r="17" fill="none" stroke="#111827" stroke-width="5"/>',
            f'<path d="M -26 18 L -4 -6 L 14 18 L -2 18 L 8 2 L 26 2" stroke="{color}" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
            f'<line x1="14" y1="18" x2="30" y2="18" stroke="{color}" stroke-width="6" stroke-linecap="round"/>',
            f'<line x1="-4" y1="-6" x2="10" y2="-20" stroke="{color}" stroke-width="6" stroke-linecap="round"/>',
        ]
    )


def render_traffic_light(element: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<rect x="-8" y="-58" width="16" height="110" rx="6" fill="#111827"/>',
            '<rect x="-22" y="-90" width="44" height="64" rx="10" fill="#1f2937" stroke="#111827" stroke-width="4"/>',
            '<circle cx="0" cy="-74" r="7" fill="#ef4444"/>',
            '<circle cx="0" cy="-58" r="7" fill="#f59e0b"/>',
            '<circle cx="0" cy="-42" r="7" fill="#22c55e"/>',
        ]
    )


def render_tree(element: dict[str, Any]) -> str:
    return "\n".join(
        [
            '<rect x="-10" y="6" width="20" height="36" rx="6" fill="#92400e"/>',
            '<circle cx="0" cy="0" r="24" fill="#22c55e" stroke="#15803d" stroke-width="4"/>',
            '<circle cx="-18" cy="8" r="18" fill="#4ade80" stroke="#15803d" stroke-width="3"/>',
            '<circle cx="18" cy="8" r="18" fill="#4ade80" stroke="#15803d" stroke-width="3"/>',
        ]
    )


def render_arrow(element: dict[str, Any]) -> str:
    color = ensure_color(element.get("color"), "#22c55e")
    style = str((element.get("props") or {}).get("style", "straight"))
    if style == "left":
        path = "M -50 40 L -10 40 L -10 -10 L 30 -10 L 30 -34 L 76 0 L 30 34 L 30 10 L 10 10 L 10 60 L -50 60 Z"
    elif style == "right":
        path = "M 50 40 L 10 40 L 10 -10 L -30 -10 L -30 -34 L -76 0 L -30 34 L -30 10 L -10 10 L -10 60 L 50 60 Z"
    elif style == "uturn":
        path = "M 36 -52 L 82 -18 L 36 16 L 36 -8 L -6 -8 Q -50 -8 -50 36 Q -50 78 -8 78 L 30 78 L 30 56 L 78 92 L 30 128 L 30 102 L -10 102 Q -74 102 -74 38 Q -74 -32 -6 -32 L 36 -32 Z"
    elif style == "merge":
        path = "M -56 58 L -8 58 L -8 28 L 44 28 L 44 2 L 92 42 L 44 82 L 44 56 L 4 56 L 4 88 L -56 88 Z"
    else:
        path = "M -70 -16 L 12 -16 L 12 -44 L 92 0 L 12 44 L 12 16 L -70 16 Z"
    return f'<path d="{path}" fill="{color}" stroke="#166534" stroke-width="4" stroke-linejoin="round"/>'


def render_placeholder(element: dict[str, Any]) -> str:
    text = xml_escape(
        (element.get("props") or {}).get("text") or element.get("label") or "Missing"
    )
    return "\n".join(
        [
            '<rect x="-70" y="-40" width="140" height="80" rx="14" fill="#e2e8f0" stroke="#64748b" stroke-width="4" stroke-dasharray="10 8"/>',
            f'<text x="0" y="6" font-size="16" text-anchor="middle" fill="#334155" font-family="Segoe UI, sans-serif">{text}</text>',
        ]
    )


def summarize_scene(scene: dict[str, Any]) -> str:
    scene = normalize_scene(scene)
    counts = Counter(element["kind"] for element in scene.get("elements", []))
    layout = current_layout_kind(scene).replace("_", " ")
    parts = [f"{layout.title()} layout"]
    for kind in ["car", "truck", "bus", "pedestrian", "bicycle", "traffic_light"]:
        count = counts.get(kind)
        if count:
            label = kind.replace("_", " ")
            parts.append(f"{count} {label}{'' if count == 1 else 's'}")
    return " · ".join(parts)
