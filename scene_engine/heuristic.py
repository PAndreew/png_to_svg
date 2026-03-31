from __future__ import annotations
import math
import re
from typing import Any, Mapping
from .catalog import COLOR_WORDS, LAYER_GROUP_ORDER, asset_spec
from .normalize import (
    default_scene,
    deep_copy_scene,
    normalize_scene,
    make_element,
    new_id,
    ensure_color,
)


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
    apply_spatial_layout(scene, prompt)
    normalized = normalize_scene(scene)
    normalized["warnings"] = dedupe_strings(warnings + normalized.get("warnings", []))
    return normalized, normalized["warnings"]


def _layout_slots(layout: str) -> list[dict[str, float | int | str]]:
    slots = {
        "highway": [
            {"x": 250, "y": 314, "rotation": 0, "lane": "lane_1"},
            {"x": 480, "y": 314, "rotation": 0, "lane": "lane_1"},
            {"x": 710, "y": 314, "rotation": 0, "lane": "lane_1"},
            {"x": 250, "y": 384, "rotation": 0, "lane": "lane_2"},
            {"x": 520, "y": 384, "rotation": 0, "lane": "lane_2"},
            {"x": 790, "y": 384, "rotation": 0, "lane": "lane_2"},
            {"x": 260, "y": 454, "rotation": 0, "lane": "lane_3"},
            {"x": 500, "y": 454, "rotation": 0, "lane": "lane_3"},
            {"x": 740, "y": 454, "rotation": 0, "lane": "lane_3"},
        ],
        "road": [
            {"x": 260, "y": 348, "rotation": 0, "lane": "eastbound"},
            {"x": 470, "y": 348, "rotation": 0, "lane": "eastbound"},
            {"x": 700, "y": 348, "rotation": 0, "lane": "eastbound"},
            {"x": 760, "y": 420, "rotation": 180, "lane": "westbound"},
            {"x": 550, "y": 420, "rotation": 180, "lane": "westbound"},
            {"x": 330, "y": 420, "rotation": 180, "lane": "westbound"},
        ],
        "crosswalk": [
            {"x": 250, "y": 348, "rotation": 0, "lane": "eastbound"},
            {"x": 680, "y": 420, "rotation": 180, "lane": "westbound"},
            {"x": 400, "y": 348, "rotation": 0, "lane": "eastbound"},
        ],
        "intersection": [
            {"x": 250, "y": 420, "rotation": 0, "lane": "west_entry"},
            {"x": 760, "y": 348, "rotation": 180, "lane": "east_entry"},
            {"x": 560, "y": 210, "rotation": 90, "lane": "north_entry"},
            {"x": 468, "y": 560, "rotation": -90, "lane": "south_entry"},
            {"x": 140, "y": 420, "rotation": 0, "lane": "west_queue"},
            {"x": 860, "y": 348, "rotation": 180, "lane": "east_queue"},
        ],
        "t_junction": [
            {"x": 250, "y": 420, "rotation": 0, "lane": "west_entry"},
            {"x": 760, "y": 348, "rotation": 180, "lane": "east_entry"},
            {"x": 750, "y": 210, "rotation": 90, "lane": "north_entry"},
            {"x": 150, "y": 420, "rotation": 0, "lane": "west_queue"},
        ],
        "roundabout": [
            {"x": 512, "y": 180, "rotation": 90, "lane": "north_arc"},
            {"x": 760, "y": 384, "rotation": 180, "lane": "east_arc"},
            {"x": 512, "y": 590, "rotation": -90, "lane": "south_arc"},
            {"x": 260, "y": 384, "rotation": 0, "lane": "west_arc"},
        ],
    }
    return [dict(slot) for slot in slots.get(layout, slots["road"])]


def _layout_anchor(layout: str) -> tuple[float, float]:
    anchors = {
        "highway": (512.0, 384.0),
        "road": (512.0, 384.0),
        "crosswalk": (512.0, 384.0),
        "intersection": (512.0, 384.0),
        "t_junction": (512.0, 404.0),
        "roundabout": (512.0, 384.0),
    }
    return anchors.get(layout, anchors["road"])


def _has_layout_backdrop(scene: dict[str, Any]) -> bool:
    return any(
        str(element.get("kind")) in {"road", "intersection", "t_junction", "roundabout"}
        for element in scene.get("elements", [])
    )


def _ensure_layout_backdrop(scene: dict[str, Any], layout: str) -> None:
    if _has_layout_backdrop(scene):
        return
    if any(_is_lane_asset(element) for element in scene.get("elements", [])) or any(
        str(asset_spec(str(element.get("kind"))).get("placement") or "") == "layout"
        for element in scene.get("elements", [])
    ):
        x, y = _layout_anchor("road")
        scene.setdefault("elements", []).insert(
            0,
            make_element(
                "road", x=x, y=y, layer=0, props={"length": 920, "width": 180}
            ),
        )


def _anchor_layout_elements(scene: dict[str, Any], layout: str) -> None:
    anchor_x, anchor_y = _layout_anchor(layout)
    for element in scene.get("elements", []):
        kind = str(element.get("kind"))
        if kind not in {
            "road",
            "crosswalk",
            "intersection",
            "t_junction",
            "roundabout",
        }:
            continue
        if kind == "t_junction":
            element["x"], element["y"] = _layout_anchor("t_junction")
        else:
            element["x"] = anchor_x
            element["y"] = anchor_y
        if kind in {"road", "crosswalk", "intersection", "t_junction", "roundabout"}:
            element["rotation"] = 0.0
            element["scale"] = float(element.get("scale") or 1.0)


def _crossing_intent(prompt_text: str) -> bool:
    return any(
        term in prompt_text
        for term in [
            "crossing",
            "cross the road",
            "across the road",
            "walk through the crosswalk",
            "walks through the crosswalk",
            "pedestrian goes through",
            "pedestrian crossing",
            "on the crosswalk",
            "through a crosswalk",
        ]
    )


def _approach_intent(prompt_text: str) -> bool:
    return any(
        term in prompt_text
        for term in [
            "approaching",
            "approach",
            "appraoch",
            "near pedestrian",
            "toward pedestrian",
            "towards pedestrian",
            "close to pedestrian",
        ]
    )


def _primary_lane_vehicle(scene: dict[str, Any]) -> dict[str, Any] | None:
    vehicles = [
        element for element in scene.get("elements", []) if _is_lane_asset(element)
    ]
    if not vehicles:
        return None
    vehicles.sort(
        key=lambda element: (
            {"xlarge": 0, "large": 1, "medium": 2, "small": 3}.get(
                str(asset_spec(str(element.get("kind"))).get("sizeBucket")), 9
            ),
            element.get("layer", 10),
            element.get("id", ""),
        )
    )
    return vehicles[0]


def _vehicle_relative_point(
    vehicle: dict[str, Any], *, forward: float, lateral: float
) -> tuple[float, float]:
    rotation = float(vehicle.get("rotation", 0))
    angle = math.radians(rotation)
    forward_x = round(math.cos(angle), 6)
    forward_y = round(math.sin(angle), 6)
    right_x = round(-forward_y, 6)
    right_y = round(forward_x, 6)
    x = float(vehicle.get("x", 0)) + forward_x * forward + right_x * lateral
    y = float(vehicle.get("y", 0)) + forward_y * forward + right_y * lateral
    return x, y


def _place_walkers_near_vehicle(
    scene: dict[str, Any], walkers: list[dict[str, Any]]
) -> bool:
    vehicle = _primary_lane_vehicle(scene)
    if not vehicle:
        return False
    for index, element in enumerate(walkers):
        x, y = _vehicle_relative_point(
            vehicle, forward=140 + index * 34, lateral=112 + index * 28
        )
        spec = asset_spec(str(element.get("kind")))
        element["x"] = float(x)
        element["y"] = float(y)
        element["rotation"] = float(
            element.get("rotation") or spec.get("defaultRotation") or 0
        )
        element["scale"] = float(
            element.get("scale") or spec.get("defaultScale") or 1.0
        )
    return True


def _place_pedestrians(scene: dict[str, Any], prompt_text: str, layout: str) -> None:
    pedestrians = [el for el in scene.get("elements", []) if _is_walker_asset(el)]
    if not pedestrians:
        return
    if layout == "crosswalk" or any(
        el.get("kind") == "crosswalk" for el in scene.get("elements", [])
    ):
        crossing_slots = [(512, 334), (512, 384), (512, 434)]
        sidewalk_slots = [(420, 292), (604, 476)]
        slots = (
            crossing_slots
            if _crossing_intent(prompt_text) or len(pedestrians) == 1
            else sidewalk_slots
        )
        for index, element in enumerate(pedestrians):
            x, y = slots[min(index, len(slots) - 1)]
            spec = asset_spec(str(element.get("kind")))
            element["x"] = float(x)
            element["y"] = float(y)
            element["rotation"] = float(
                element.get("rotation") or spec.get("defaultRotation") or 0
            )
            element["scale"] = float(
                element.get("scale") or spec.get("defaultScale") or 1.0
            )
        return

    if (
        layout == "road"
        and _approach_intent(prompt_text)
        and _place_walkers_near_vehicle(scene, pedestrians)
    ):
        return

    _place_static_assets({"elements": pedestrians}, layout)


def _place_arrows(scene: dict[str, Any], prompt_text: str, layout: str) -> None:
    arrows = [el for el in scene.get("elements", []) if str(el.get("kind")) == "arrow"]
    if not arrows:
        return
    arrow_positions = {
        "road": (512, 312, 0),
        "crosswalk": (512, 286, 0),
        "intersection": (468, 286, 0),
        "t_junction": (468, 286, 0),
        "roundabout": (620, 210, 0),
    }
    base_x, base_y, base_rotation = arrow_positions.get(layout, arrow_positions["road"])
    for arrow in arrows:
        style = str((arrow.get("props") or {}).get("style") or "straight")
        arrow["x"] = float(base_x)
        arrow["y"] = float(base_y)
        if style == "left":
            arrow["x"] = float(base_x - 28)
        elif style == "right":
            arrow["x"] = float(base_x + 28)
        elif style == "merge":
            arrow["y"] = float(base_y + 36)
        elif style == "uturn":
            arrow["x"] = float(base_x + 36)
            arrow["y"] = float(base_y - 10)
        arrow["rotation"] = float(base_rotation)


def _is_lane_asset(element: dict[str, Any]) -> bool:
    spec = asset_spec(str(element.get("kind")))
    placement = str(spec.get("placement") or "")
    allowed = {str(value) for value in spec.get("allowedPlacements") or []}
    return (
        placement in {"lane", "lane_edge"}
        or bool({"lane", "lane_edge"} & allowed)
        or str(spec.get("assetClass")) in {"vehicle", "cyclist"}
    )


def _is_walker_asset(element: dict[str, Any]) -> bool:
    spec = asset_spec(str(element.get("kind")))
    return str(spec.get("mobility")) == "walker" or str(spec.get("assetClass")) in {
        "human",
        "animal",
    }


def _layer_for_element(element: dict[str, Any]) -> int:
    spec = asset_spec(str(element.get("kind")))
    base = int(
        spec.get("layer")
        or LAYER_GROUP_ORDER.get(str(spec.get("layerGroup") or "props"), 16)
    )
    kind = str(element.get("kind"))
    placement = str(spec.get("placement") or "")
    if kind in {"road", "intersection", "t_junction", "roundabout"}:
        return base
    if kind == "crosswalk" or placement == "layout":
        return base + 1
    if str(spec.get("layerGroup")) == "environment" and kind == "traffic_light":
        return base + 1
    if str(spec.get("layerGroup")) == "annotations":
        return base + 1
    return base


def _apply_layer_groups(scene: dict[str, Any]) -> None:
    for element in scene.get("elements", []):
        element["layer"] = _layer_for_element(element)


def _preferred_rotation(
    prompt_text: str, element: dict[str, Any], layout: str
) -> float:
    current = float(element.get("rotation", 0))
    if abs(current) > 1:
        return current
    kind = element.get("kind")
    if kind == "traffic_light":
        return 0
    if layout == "roundabout":
        return current or 90
    if "turn left" in prompt_text:
        return -90 if layout in {"intersection", "t_junction"} else 0
    if "turn right" in prompt_text:
        return 90 if layout in {"intersection", "t_junction"} else 0
    return current


def _slot_distance(
    element: dict[str, Any], slot: dict[str, float | int | str]
) -> float:
    return abs(float(element.get("x", 0)) - float(slot["x"])) + abs(
        float(element.get("y", 0)) - float(slot["y"])
    )


def _assign_vehicle_slots(scene: dict[str, Any], prompt_text: str, layout: str) -> None:
    slots = _layout_slots(layout)
    vehicles = [el for el in scene.get("elements", []) if _is_lane_asset(el)]
    vehicles.sort(
        key=lambda el: (
            {"xlarge": 0, "large": 1, "medium": 2, "small": 3}.get(
                str(asset_spec(str(el.get("kind"))).get("sizeBucket")), 9
            ),
            el.get("layer", 10),
            el.get("id", ""),
        )
    )
    used: set[int] = set()
    for element in vehicles:
        spec = asset_spec(str(element.get("kind")))
        element["scale"] = float(
            element.get("scale") or spec.get("defaultScale") or 1.0
        )
        preferred_rotation = _preferred_rotation(prompt_text, element, layout)
        ranked = sorted(
            enumerate(slots),
            key=lambda pair: _slot_distance(element, pair[1])
            + abs(preferred_rotation - float(pair[1]["rotation"])) * 0.75,
        )
        chosen_index = next(
            (index for index, _slot in ranked if index not in used),
            ranked[0][0] if ranked else None,
        )
        if chosen_index is None:
            continue
        used.add(chosen_index)
        slot = slots[chosen_index]
        element["x"] = float(slot["x"])
        element["y"] = float(slot["y"])
        element["rotation"] = (
            preferred_rotation
            if abs(preferred_rotation) > 1
            else float(slot["rotation"])
        )


def _place_static_assets(scene: dict[str, Any], layout: str) -> None:
    placements = {
        "roadside": {
            "road": [(850, 250)],
            "crosswalk": [(760, 250)],
            "intersection": [(760, 250), (250, 520)],
            "t_junction": [(760, 250)],
            "roundabout": [(820, 180)],
        },
        "roadside_large": {
            "road": [(140, 190), (880, 580)],
            "crosswalk": [(150, 180), (880, 590)],
            "intersection": [(120, 160), (900, 620)],
            "t_junction": [(120, 160), (900, 620)],
            "roundabout": [(150, 160), (890, 620)],
        },
        "sidewalk": {
            "road": [(170, 300), (860, 470)],
            "crosswalk": [(520, 305), (520, 465)],
            "intersection": [(340, 270), (680, 500)],
            "t_junction": [(330, 270), (700, 500)],
            "roundabout": [(300, 240), (720, 520)],
        },
    }
    counts: dict[str, int] = {}
    for element in scene.get("elements", []):
        kind = str(element.get("kind"))
        spec = asset_spec(kind)
        placement = str(spec.get("placement") or "")
        if placement == "roadside":
            key = (
                "roadside_large"
                if kind == "tree" or str(spec.get("sizeBucket")) in {"large", "xlarge"}
                else "roadside"
            )
        elif placement == "sidewalk":
            key = "sidewalk"
        else:
            continue
        options = placements[key].get(layout) or placements[key].get("road") or []
        index = counts.get(key, 0)
        counts[key] = index + 1
        if index >= len(options):
            index = len(options) - 1
        if index < 0:
            continue
        x, y = options[index]
        element["x"] = x
        element["y"] = y
        element["rotation"] = float(
            element.get("rotation") or spec.get("defaultRotation") or 0
        )
        element["scale"] = float(
            element.get("scale") or spec.get("defaultScale") or 1.0
        )


def apply_spatial_layout(scene: dict[str, Any], prompt: str = "") -> None:
    layout = current_layout_kind(scene)
    symbolic = str(scene.get("plannerMode") or "").lower() == "symbolic"
    if layout == "road":
        layout = "road"
    prompt_text = prompt.lower()
    _ensure_layout_backdrop(scene, layout)
    layout = current_layout_kind(scene)
    _anchor_layout_elements(scene, layout)
    if not symbolic:
        _assign_vehicle_slots(scene, prompt_text, layout)
        _place_static_assets(scene, layout)
        _place_pedestrians(scene, prompt_text, layout)
    _place_arrows(scene, prompt_text, layout)
    _apply_layer_groups(scene)


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
    if any(term in text for term in ["highway", "motorway", "freeway"]):
        return "highway"
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
    if layout == "highway":
        elements.append(
            make_element(
                "road",
                x=512,
                y=384,
                layer=0,
                props={"length": 940, "width": 260, "lanes": 3},
            )
        )
    elif layout == "intersection":
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


def _template_to_layout_kind(template: str) -> str:
    mappings = {
        "highway_3_lane": "highway",
        "straight_road": "road",
        "road": "road",
        "crosswalk_road": "crosswalk",
        "crosswalk": "crosswalk",
        "intersection": "intersection",
        "t_junction": "t_junction",
        "roundabout": "roundabout",
    }
    return mappings.get(str(template or "").strip().lower(), "road")


def _lane_paths(layout: str) -> dict[str, list[tuple[float, float]]]:
    paths = {
        "highway": {
            "lane_1": [(200, 314), (824, 314)],
            "lane_2": [(200, 384), (824, 384)],
            "lane_3": [(200, 454), (824, 454)],
        },
        "road": {
            "eastbound": [(220, 348), (804, 348)],
            "westbound": [(804, 420), (220, 420)],
        },
        "crosswalk": {
            "eastbound": [(220, 348), (804, 348)],
            "westbound": [(804, 420), (220, 420)],
        },
        "intersection": {
            "west_entry": [(120, 420), (420, 420)],
            "east_entry": [(904, 348), (604, 348)],
            "north_entry": [(560, 120), (560, 300)],
            "south_entry": [(468, 648), (468, 468)],
            "west_queue": [(40, 420), (280, 420)],
            "east_queue": [(984, 348), (744, 348)],
        },
        "t_junction": {
            "west_entry": [(120, 420), (420, 420)],
            "east_entry": [(904, 348), (604, 348)],
            "north_entry": [(750, 120), (750, 280)],
            "west_queue": [(40, 420), (280, 420)],
        },
        "roundabout": {
            "north_arc": [(512, 120), (650, 190), (760, 384)],
            "east_arc": [(860, 384), (760, 500), (512, 590)],
            "south_arc": [(512, 650), (360, 590), (260, 384)],
            "west_arc": [(160, 384), (260, 250), (512, 180)],
        },
    }
    return copy_lane_paths(paths.get(layout, paths["road"]))


def copy_lane_paths(
    paths: Mapping[str, list[tuple[int, int]] | list[tuple[float, float]]],
) -> dict[str, list[tuple[float, float]]]:
    copied: dict[str, list[tuple[float, float]]] = {}
    for key, value in paths.items():
        copied[key] = [(float(point[0]), float(point[1])) for point in value]
    return copied


def _static_anchors(layout: str) -> dict[str, tuple[float, float]]:
    anchors = {
        "road": {
            "roadside_top": (760, 250),
            "roadside_bottom": (250, 520),
            "sidewalk_top": (170, 300),
            "sidewalk_bottom": (860, 470),
            "crosswalk_center": (512, 384),
        },
        "highway": {
            "roadside_top": (840, 220),
            "roadside_bottom": (160, 550),
            "shoulder_top": (240, 250),
            "shoulder_bottom": (780, 520),
        },
        "crosswalk": {
            "roadside_top": (760, 250),
            "roadside_bottom": (250, 520),
            "sidewalk_top": (420, 292),
            "sidewalk_bottom": (604, 476),
            "crosswalk_center": (512, 384),
            "crosswalk_top": (512, 334),
            "crosswalk_bottom": (512, 434),
        },
        "intersection": {
            "signal_northeast": (760, 250),
            "signal_southwest": (250, 520),
            "sidewalk_northwest": (340, 270),
            "sidewalk_southeast": (680, 500),
        },
        "t_junction": {
            "signal_primary": (760, 250),
            "sidewalk_left": (330, 270),
            "sidewalk_right": (700, 500),
        },
        "roundabout": {
            "roadside_north": (820, 180),
            "roadside_south": (150, 160),
            "sidewalk_left": (300, 240),
            "sidewalk_right": (720, 520),
        },
    }
    return dict(anchors.get(layout, anchors["road"]))


def layout_planner_context() -> dict[str, Any]:
    templates = [
        {"template": "straight_road", "layoutKind": "road"},
        {"template": "highway_3_lane", "layoutKind": "highway"},
        {"template": "crosswalk_road", "layoutKind": "crosswalk"},
        {"template": "intersection", "layoutKind": "intersection"},
        {"template": "t_junction", "layoutKind": "t_junction"},
        {"template": "roundabout", "layoutKind": "roundabout"},
    ]
    return {
        "templates": [
            {
                "template": item["template"],
                "layoutKind": item["layoutKind"],
                "lanes": sorted(_lane_paths(item["layoutKind"]).keys()),
                "anchors": sorted(_static_anchors(item["layoutKind"]).keys()),
            }
            for item in templates
        ]
    }


def _sample_polyline(
    points: list[tuple[float, float]], s_value: float
) -> tuple[float, float, float]:
    if not points:
        return 512.0, 384.0, 0.0
    if len(points) == 1:
        return float(points[0][0]), float(points[0][1]), 0.0
    s_clamped = max(0.0, min(1.0, float(s_value)))
    lengths: list[float] = []
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        lengths.append(length)
        total += length
    if total <= 1e-6:
        return float(points[0][0]), float(points[0][1]), 0.0
    target = total * s_clamped
    walked = 0.0
    for index, length in enumerate(lengths):
        if walked + length >= target or index == len(lengths) - 1:
            start = points[index]
            end = points[index + 1]
            local = 0.0 if length <= 1e-6 else (target - walked) / length
            x = start[0] + (end[0] - start[0]) * local
            y = start[1] + (end[1] - start[1]) * local
            rotation = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
            return float(x), float(y), float(rotation)
        walked += length
    last = points[-1]
    prev = points[-2]
    rotation = math.degrees(math.atan2(last[1] - prev[1], last[0] - prev[0]))
    return float(last[0]), float(last[1]), float(rotation)


def _default_lane_for_kind(kind: str, layout: str) -> str:
    spec = asset_spec(kind)
    placement = str(spec.get("placement") or "")
    lanes = _lane_paths(layout)
    if layout == "highway":
        return "lane_2" if "lane_2" in lanes else next(iter(lanes.keys()), "lane_1")
    if placement == "lane_edge":
        return (
            "eastbound"
            if "eastbound" in lanes
            else next(iter(lanes.keys()), "eastbound")
        )
    if str(spec.get("assetClass")) in {"vehicle", "cyclist"}:
        return (
            "eastbound"
            if "eastbound" in lanes
            else next(iter(lanes.keys()), "eastbound")
        )
    return next(iter(lanes.keys()), "eastbound")


def _resolve_anchor(
    layout: str, item: dict[str, Any], index: int
) -> tuple[float, float]:
    anchors = _static_anchors(layout)
    anchor = str(item.get("anchor") or item.get("zone") or "").strip()
    if anchor in anchors:
        return anchors[anchor]
    ordered = list(anchors.values())
    if not ordered:
        return _layout_anchor(layout)
    return ordered[min(index, len(ordered) - 1)]


def _resolve_lane_name(layout: str, item: dict[str, Any], fallback: str) -> str:
    lanes = _lane_paths(layout)
    named_lane = str(item.get("lane") or "").strip()
    if named_lane in lanes:
        return named_lane
    lane_index_raw = item.get("laneIndex")
    if lane_index_raw is not None:
        try:
            lane_index = max(1, int(lane_index_raw))
            ordered = sorted(lanes.keys())
            if ordered:
                return ordered[min(lane_index - 1, len(ordered) - 1)]
        except Exception:
            pass
    return fallback


def _resolve_progress(item: dict[str, Any], index: int) -> float:
    s_raw = item.get("s")
    if s_raw is not None:
        return float(s_raw)
    slot_raw = item.get("slot")
    if slot_raw is not None:
        try:
            slot = max(1, int(slot_raw))
            slot_count = max(1, int(item.get("slotCount") or 5))
            return max(0.05, min(0.95, (slot - 0.5) / slot_count))
        except Exception:
            pass
    return min(0.25 + index * 0.18, 0.85)


def build_scene_from_layout_plan(
    layout_plan: dict[str, Any],
    prompt: str,
    current_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene = default_scene() if not current_scene else deep_copy_scene(current_scene)
    layout_value = layout_plan.get("layout")
    layout_info = layout_value if isinstance(layout_value, dict) else {}
    template = str(layout_info.get("template") or "straight_road")
    layout = _template_to_layout_kind(template)
    scene["elements"] = build_layout(layout)
    scene["title"] = str(layout_plan.get("title") or build_title(prompt))
    scene["prompt"] = prompt
    scene["warnings"] = list(layout_plan.get("warnings") or [])
    scene["plannerMode"] = "symbolic"
    scene["layoutTemplate"] = template

    dynamic_value = layout_plan.get("dynamic")
    static_value = layout_plan.get("static")
    annotation_value = layout_plan.get("annotations")
    dynamic_items: list[Any] = dynamic_value if isinstance(dynamic_value, list) else []
    static_items: list[Any] = static_value if isinstance(static_value, list) else []
    annotation_items: list[Any] = (
        annotation_value if isinstance(annotation_value, list) else []
    )

    placement_records: dict[str, dict[str, Any]] = {}
    lane_paths = _lane_paths(layout)

    for index, item in enumerate(static_items):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        x, y = _resolve_anchor(layout, item, index)
        spec = asset_spec(kind)
        element = make_element(
            kind,
            x=x,
            y=y,
            rotation=float(item.get("rotation") or spec.get("defaultRotation") or 0),
            scale=float(item.get("scale") or spec.get("defaultScale") or 1.0),
            color=item.get("color") or None,
            layer=int(spec.get("layer") or 10),
            label=str(item.get("label") or "") or None,
        )
        if item.get("id"):
            element["id"] = str(item["id"])
        scene["elements"].append(element)
        placement_records[element["id"]] = {"lane": None, "s": None, "kind": kind}

    pending_relations: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for index, item in enumerate(dynamic_items):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        spec = asset_spec(kind)
        lane = _resolve_lane_name(layout, item, _default_lane_for_kind(kind, layout))
        if lane not in lane_paths:
            lane = _default_lane_for_kind(kind, layout)
        s_value = _resolve_progress(item, index)
        x, y, rotation = _sample_polyline(lane_paths.get(lane, []), s_value)
        heading = str(item.get("heading") or "forward").strip().lower()
        if heading in {"reverse", "backward", "opposite"}:
            rotation = (rotation + 180.0) % 360.0
        element = make_element(
            kind,
            x=x,
            y=y,
            rotation=rotation,
            scale=float(item.get("scale") or spec.get("defaultScale") or 1.0),
            color=item.get("color") or None,
            layer=int(spec.get("layer") or 10),
            label=str(item.get("label") or "") or None,
        )
        if item.get("id"):
            element["id"] = str(item["id"])
        if isinstance(item.get("props"), dict):
            element["props"] = dict(item.get("props") or {})
        scene["elements"].append(element)
        placement_records[element["id"]] = {"lane": lane, "s": s_value, "kind": kind}
        relation = str(item.get("relation") or "").strip()
        if relation:
            pending_relations.append((item, element, relation))

    for item, element, relation in pending_relations:
        mode, _, target_id = relation.partition(":")
        target = next(
            (
                candidate
                for candidate in scene["elements"]
                if candidate.get("id") == target_id
            ),
            None,
        )
        target_record = placement_records.get(target_id)
        current_record = placement_records.get(element["id"])
        if (
            not target
            or not target_record
            or not current_record
            or not target_record.get("lane")
        ):
            continue
        lane = str(
            item.get("lane")
            or target_record.get("lane")
            or current_record.get("lane")
            or ""
        )
        if lane not in lane_paths:
            continue
        target_s = float(target_record.get("s") or 0.5)
        if mode == "behind":
            current_record["s"] = max(0.05, target_s - 0.16)
        elif mode == "ahead_of":
            current_record["s"] = min(0.95, target_s + 0.16)
        elif mode == "approaching":
            current_record["s"] = max(0.05, target_s - 0.12)
        elif mode == "next_to":
            current_record["s"] = target_s
        else:
            continue
        x, y, rotation = _sample_polyline(lane_paths[lane], current_record["s"])
        element["x"] = x
        element["y"] = y
        element["rotation"] = rotation

    for index, item in enumerate(annotation_items):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "arrow").strip() or "arrow"
        spec = asset_spec(kind)
        anchor_x, anchor_y = _resolve_anchor(layout, item, index)
        element = make_element(
            kind,
            x=anchor_x,
            y=anchor_y,
            rotation=float(item.get("rotation") or spec.get("defaultRotation") or 0),
            scale=float(item.get("scale") or spec.get("defaultScale") or 1.0),
            color=item.get("color") or None,
            layer=int(spec.get("layer") or 20),
            label=str(item.get("label") or "") or None,
            props=dict(item.get("props") or {}),
        )
        if item.get("id"):
            element["id"] = str(item["id"])
        scene["elements"].append(element)

    return normalize_scene(scene)


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
    if str(scene.get("layoutTemplate") or "") == "highway_3_lane":
        return "highway"
    for kind in ["roundabout", "intersection", "t_junction", "crosswalk", "road"]:
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
