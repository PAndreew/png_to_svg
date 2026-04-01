from __future__ import annotations
from typing import Any
from .normalize import normalize_scene, build_transform, xml_escape, ensure_color, clamp_number, default_label
from .catalog import catalog

SVG_NS = "http://www.w3.org/2000/svg"


def _asset_definition(kind: str) -> dict[str, Any] | None:
    for item in catalog():
        if item.get("kind") == kind:
            return item
    return None


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
    asset_definition = _asset_definition(element["kind"])
    if asset_definition and asset_definition.get("svgMarkup"):
        inner = str(asset_definition["svgMarkup"])
    else:
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
    path_points = props.get("pathPoints") if isinstance(props.get("pathPoints"), list) else []
    if path_points:
        coords = [point for point in path_points if isinstance(point, (tuple, list)) and len(point) >= 2]
        if len(coords) >= 2:
            width = clamp_number(props.get("width", 180), 80, 420, 180)
            lane_count = int(clamp_number(props.get("lanes", 2), 1, 6, 2))
            road_role = str(props.get("roadRole") or "road").strip().lower()
            base_color = "#5b6474" if road_role in {"arterial", "main", "main_road"} else "#6b7280"
            path_d = "M " + " L ".join(f"{float(point[0]):.1f} {float(point[1]):.1f}" for point in coords)
            parts = [
                f'<path d="{path_d}" fill="none" stroke="{base_color}" stroke-width="{width:.1f}" stroke-linecap="round" stroke-linejoin="round"/>',
            ]
            if lane_count >= 2:
                parts.append(
                    f'<path d="{path_d}" fill="none" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            parts.append(
                f'<path d="{path_d}" fill="none" stroke="#d1d5db" stroke-width="{max(width - 28.0, 12.0):.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.08"/>'
            )
            return "\n".join(parts)
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
