from __future__ import annotations
import re
from typing import Any
from .catalog import ASSET_CATALOG, COLOR_WORDS, asset_spec
from .normalize import default_scene, deep_copy_scene, normalize_scene, make_element, new_id, ensure_color


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


def _vehicle_kinds() -> set[str]:
    return {"car", "truck", "bus", "bicycle"}


def _preferred_rotation(prompt_text: str, element: dict[str, Any], layout: str) -> float:
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


def _slot_distance(element: dict[str, Any], slot: dict[str, float | int | str]) -> float:
    return abs(float(element.get("x", 0)) - float(slot["x"])) + abs(float(element.get("y", 0)) - float(slot["y"]))


def _assign_vehicle_slots(scene: dict[str, Any], prompt_text: str, layout: str) -> None:
    slots = _layout_slots(layout)
    vehicles = [el for el in scene.get("elements", []) if el.get("kind") in _vehicle_kinds()]
    vehicles.sort(key=lambda el: ({"car": 0, "truck": 1, "bus": 2, "bicycle": 3}.get(el.get("kind"), 9), el.get("layer", 10), el.get("id", "")))
    used: set[int] = set()
    for element in vehicles:
        spec = asset_spec(str(element.get("kind")))
        element["scale"] = float(element.get("scale") or spec.get("defaultScale") or 1.0)
        preferred_rotation = _preferred_rotation(prompt_text, element, layout)
        ranked = sorted(
            enumerate(slots),
            key=lambda pair: _slot_distance(element, pair[1]) + abs(preferred_rotation - float(pair[1]["rotation"])) * 0.75,
        )
        chosen_index = next((index for index, _slot in ranked if index not in used), ranked[0][0] if ranked else None)
        if chosen_index is None:
            continue
        used.add(chosen_index)
        slot = slots[chosen_index]
        element["x"] = float(slot["x"])
        element["y"] = float(slot["y"])
        element["rotation"] = preferred_rotation if abs(preferred_rotation) > 1 else float(slot["rotation"])


def _place_static_assets(scene: dict[str, Any], layout: str) -> None:
    placements = {
        "traffic_light": {
            "road": [(850, 250)],
            "crosswalk": [(760, 250)],
            "intersection": [(760, 250), (250, 520)],
            "t_junction": [(760, 250)],
            "roundabout": [(820, 180)],
        },
        "tree": {
            "road": [(140, 190), (880, 580)],
            "crosswalk": [(150, 180), (880, 590)],
            "intersection": [(120, 160), (900, 620)],
            "t_junction": [(120, 160), (900, 620)],
            "roundabout": [(150, 160), (890, 620)],
        },
        "pedestrian": {
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
        if kind not in placements:
            continue
        options = placements[kind].get(layout) or placements[kind].get("road") or []
        index = counts.get(kind, 0)
        counts[kind] = index + 1
        if index >= len(options):
            index = len(options) - 1
        if index < 0:
            continue
        x, y = options[index]
        spec = asset_spec(kind)
        element["x"] = x
        element["y"] = y
        element["rotation"] = float(element.get("rotation") or spec.get("defaultRotation") or 0)
        element["scale"] = float(element.get("scale") or spec.get("defaultScale") or 1.0)


def apply_spatial_layout(scene: dict[str, Any], prompt: str = "") -> None:
    layout = current_layout_kind(scene)
    if layout == "road":
        layout = "road"
    prompt_text = prompt.lower()
    _assign_vehicle_slots(scene, prompt_text, layout)
    _place_static_assets(scene, layout)


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
