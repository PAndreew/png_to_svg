from __future__ import annotations
from collections import Counter
from typing import Any
from .normalize import normalize_scene


def _layout_kind(scene: dict[str, Any]) -> str:
    for kind in ("roundabout", "intersection", "t_junction", "crosswalk", "road"):
        if any(el["kind"] == kind for el in scene.get("elements", [])):
            return kind
    return "road"


def summarize_scene(scene: dict[str, Any]) -> str:
    scene = normalize_scene(scene)
    counts = Counter(element["kind"] for element in scene.get("elements", []))
    layout = _layout_kind(scene).replace("_", " ")
    parts = [f"{layout.title()} layout"]
    for kind in ["car", "truck", "bus", "pedestrian", "bicycle", "traffic_light"]:
        count = counts.get(kind)
        if count:
            label = kind.replace("_", " ")
            parts.append(f"{count} {label}{'' if count == 1 else 's'}")
    return " · ".join(parts)
