"""Grid-layout scene builder.

Converts a `layoutPlan` (grid-based, as produced by the LLM) into a scene dict
ready for rendering.  The only entry points callers need are:

  build_scene_from_layout_plan(layout_plan, prompt, current_scene=None)
  apply_spatial_layout(scene, prompt="")
  layout_planner_context() -> dict
"""
from __future__ import annotations
import math
from typing import Any

from .catalog import LAYER_GROUP_ORDER, asset_spec
from .normalize import (
    default_scene,
    deep_copy_scene,
    normalize_scene,
    make_element,
)


# ---------------------------------------------------------------------------
# LLM context helpers
# ---------------------------------------------------------------------------

def build_title(prompt: str) -> str:
    import re
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt[:80] if prompt else "ODD pictogram"


def layout_planner_context() -> dict[str, Any]:
    return {
        "grid": {
            "minCols": 10, "maxCols": 15,
            "minRows": 10, "maxRows": 15,
            "chooseSizeByComplexity": True,
        },
        "geometryPrimitives": [
            {"kind": "road", "notes": "Centered grid rectangle for straight corridors, or points[] for arterials and curved connectors."},
            {"kind": "topology", "notes": "For multi-road scenes add layoutPlan.topology.roads and .junctions first; keep geometry ids consistent."},
            {"kind": "crosswalk", "notes": "Overlay on road geometry, layer 2, full road width."},
            {"kind": "intersection", "notes": "Four-way junction geometry."},
            {"kind": "t_junction", "notes": "One road terminating into another."},
            {"kind": "roundabout", "notes": "Circular central-control geometry."},
        ],
        "layerGuide": {
            "roadBase": 1, "roadConnectors": 2, "roadMarkings": 3,
            "controls": 4, "environment": 5, "actors": 10, "annotations": 20,
        },
        "placementRules": [
            "Choose map size 10x10–15x15 based on scene complexity.",
            "Use geometry rectangles instead of semantic lane names wherever possible.",
            "For non-trivial networks include layoutPlan.topology with road ids, centerlines, road roles, and junction connectivity.",
            "Keep topology road ids aligned with geometry ids so actors can use pathId.",
            "points[] describe road centerline in grid space; the renderer builds a road ribbon from them.",
            "Cars occupy ~2x1 segments, trucks/buses ~3x1, pedestrians ~1x1.",
            "Actors may use direct grid placement or path-following with pathId, s (0–1), and laneIndex.",
        ],
    }


# ---------------------------------------------------------------------------
# Layer normalisation
# ---------------------------------------------------------------------------

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


def apply_spatial_layout(scene: dict[str, Any], prompt: str = "") -> None:
    """Post-process a scene built from a grid layout plan.

    Positions are already set by the grid builder; this only normalises layers.
    The prompt argument is kept for API compatibility.
    """
    _apply_layer_groups(scene)


# ---------------------------------------------------------------------------
# Topology → geometry conversion
# ---------------------------------------------------------------------------

def _topology_layer_for_role(role: str) -> int:
    role_key = str(role or "road").strip().lower()
    if role_key in {"arterial", "main", "main_road", "highway", "primary"}:
        return 1
    return 2


def _topology_width_segments(road: dict[str, Any]) -> float:
    width_segments = _grid_float(road, "widthSegments", 0.0)
    if width_segments > 0.0:
        return width_segments
    lane_count = _grid_int(road, "laneCount", 2, 1)
    return max(1.8, min(5.0, 1.2 + lane_count * 0.55))


def _topology_to_hybrid_plan(layout_plan: dict[str, Any]) -> dict[str, Any]:
    """Promote topology road/junction definitions into geometry/environment lists."""
    topology_value = layout_plan.get("topology")
    topology = topology_value if isinstance(topology_value, dict) else {}
    roads_value = topology.get("roads")
    junctions_value = topology.get("junctions")
    roads: list[Any] = roads_value if isinstance(roads_value, list) else []
    junctions: list[Any] = junctions_value if isinstance(junctions_value, list) else []
    if not roads and not junctions:
        return layout_plan

    merged = dict(layout_plan)
    geometry = list(merged.get("geometry") or []) if isinstance(merged.get("geometry"), list) else []
    environment = list(merged.get("environment") or []) if isinstance(merged.get("environment"), list) else []
    geometry_ids = {str(item.get("id")) for item in geometry if isinstance(item, dict) and item.get("id")}
    environment_ids = {str(item.get("id")) for item in environment if isinstance(item, dict) and item.get("id")}

    for road in roads:
        if not isinstance(road, dict):
            continue
        road_id = str(road.get("id") or "").strip()
        if not road_id or road_id in geometry_ids:
            continue
        points_value = road.get("points")
        points = points_value if isinstance(points_value, list) else []
        if len(points) < 2:
            continue
        road_role = str(
            road.get("roadRole")
            or (road.get("props") or {}).get("roadRole") if isinstance(road.get("props"), dict) else ""
            or "road"
        ).strip().lower()
        lane_count = _grid_int(road, "laneCount", 2, 1)
        width_segments = _topology_width_segments(road)
        road_props = dict(road.get("props") or {}) if isinstance(road.get("props"), dict) else {}
        geometry.append({
            "id": road_id,
            "kind": "road",
            "points": points,
            "laneCount": lane_count,
            "rowSpan": max(2, int(round(width_segments))),
            "layer": _topology_layer_for_role(road_role),
            "props": {
                **road_props,
                "roadRole": road_role,
                "laneCount": lane_count,
                "widthSegments": width_segments,
                "fromJunction": road.get("fromJunction"),
                "toJunction": road.get("toJunction"),
                "topologyRoad": True,
            },
        })
        geometry_ids.add(road_id)

    for junction in junctions:
        if not isinstance(junction, dict):
            continue
        junction_id = str(junction.get("id") or "").strip()
        if not junction_id:
            continue
        control = str(junction.get("control") or "").strip().lower()
        if control not in {"signal", "traffic_light", "traffic signal"}:
            continue
        signal_id = f"{junction_id}_signal"
        if signal_id in environment_ids:
            continue
        environment.append({
            "id": signal_id,
            "kind": "traffic_light",
            "col": int(round(float(junction.get("col", 0.0)))),
            "row": max(0, int(round(float(junction.get("row", 0.0)))) - 1),
            "colSpan": 1, "rowSpan": 1, "layer": 4,
            "props": {
                "junctionId": junction_id,
                "connectedRoadIds": list(junction.get("connectedRoadIds") or []),
                **(dict(junction.get("props") or {}) if isinstance(junction.get("props"), dict) else {}),
            },
        })
        environment_ids.add(signal_id)

    merged["geometry"] = geometry
    merged["environment"] = environment
    return merged


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _grid_int(item: dict[str, Any], key: str, default: int, minimum: int = 0) -> int:
    props = item.get("props") if isinstance(item.get("props"), dict) else {}
    raw = item.get(key)
    if raw is None:
        raw = props.get(key)
    try:
        return max(minimum, int(raw if raw is not None else default))
    except Exception:
        return default


def _grid_float(item: dict[str, Any], key: str, default: float) -> float:
    props = item.get("props") if isinstance(item.get("props"), dict) else {}
    raw = item.get(key)
    if raw is None:
        raw = props.get(key)
    try:
        return float(raw if raw is not None else default)
    except Exception:
        return float(default)


def _grid_rotation_value(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower()
    if not text:
        return float(default)
    aliases = {
        "east": 0.0, "right": 0.0, "eastbound": 0.0, "horizontal": 0.0,
        "west": 180.0, "left": 180.0, "westbound": 180.0,
        "south": 90.0, "down": 90.0, "southbound": 90.0, "vertical": 90.0,
        "north": -90.0, "up": -90.0, "northbound": -90.0,
    }
    return float(aliases.get(text, default))


def _grid_metrics(scene: dict[str, Any], layout_plan: dict[str, Any]) -> dict[str, float | int]:
    map_info = layout_plan.get("map") if isinstance(layout_plan.get("map"), dict) else {}
    cols = max(10, min(15, _grid_int(map_info, "cols", 10, 10)))
    rows = max(10, min(15, _grid_int(map_info, "rows", 10, 10)))
    canvas = scene.get("canvas") or {"width": 1024, "height": 768}
    width = float(canvas.get("width") or 1024)
    height = float(canvas.get("height") or 768)
    margin_x, margin_y = 96.0, 84.0
    cell = min((width - margin_x * 2) / cols, (height - margin_y * 2) / rows)
    grid_width = cols * cell
    grid_height = rows * cell
    return {
        "cols": cols, "rows": rows, "cell": cell,
        "origin_x": (width - grid_width) / 2.0,
        "origin_y": (height - grid_height) / 2.0,
    }


def _grid_point_to_canvas(col: float, row: float, metrics: dict[str, float | int]) -> tuple[float, float]:
    cell = float(metrics["cell"])
    x = float(metrics["origin_x"]) + (float(col) + 0.5) * cell
    y = float(metrics["origin_y"]) + (float(row) + 0.5) * cell
    return x, y


def _grid_path_points(item: dict[str, Any], metrics: dict[str, float | int]) -> list[tuple[float, float]]:
    points_value = item.get("points")
    if not isinstance(points_value, list):
        points_value = (item.get("props") or {}).get("points")
    if not isinstance(points_value, list):
        return []
    result: list[tuple[float, float]] = []
    for point in points_value:
        if not isinstance(point, dict):
            continue
        result.append(_grid_point_to_canvas(float(point.get("col", 0.0)), float(point.get("row", 0.0)), metrics))
    return result


def _grid_rect(item: dict[str, Any], metrics: dict[str, float | int]) -> tuple[float, float, float, float]:
    cell = float(metrics["cell"])
    cols = int(metrics["cols"])
    rows = int(metrics["rows"])
    col = min(cols - 1, _grid_int(item, "col", 0, 0))
    row = min(rows - 1, _grid_int(item, "row", 0, 0))
    col_span = max(1, min(cols - col, _grid_int(item, "colSpan", 1, 1)))
    row_span = max(1, min(rows - row, _grid_int(item, "rowSpan", 1, 1)))
    x = float(metrics["origin_x"]) + (col + col_span / 2.0) * cell
    y = float(metrics["origin_y"]) + (row + row_span / 2.0) * cell
    return x, y, col_span * cell, row_span * cell


def _grid_scale(kind: str, item: dict[str, Any], metrics: dict[str, float | int]) -> float:
    explicit = item.get("scale")
    if explicit is not None:
        try:
            return float(explicit)
        except Exception:
            pass
    _, _, width, height = _grid_rect(item, metrics)
    spec = asset_spec(kind)
    footprint = spec.get("footprint") if isinstance(spec.get("footprint"), dict) else {}
    base_width = float(footprint.get("width") or max(width, 1.0))
    base_height = float(footprint.get("height") or max(height, 1.0))
    cell = float(metrics["cell"])
    target_width = max(width * 0.82, cell * 0.72)
    target_height = max(height * 0.82, cell * 0.72)
    return max(0.35, min(target_width / max(base_width, 1.0), target_height / max(base_height, 1.0)))


def _grid_default_layer(kind: str, fallback: int = 3) -> int:
    _KIND_LAYERS: dict[str, int] = {
        "road": 1, "intersection": 1, "t_junction": 1, "roundabout": 1,
        "crosswalk": 3, "traffic_light": 4, "tree": 5,
        "car": 10, "truck": 10, "bus": 10, "pedestrian": 10, "bicycle": 10,
        "arrow": 20,
    }
    if kind in _KIND_LAYERS:
        return _KIND_LAYERS[kind]
    spec = asset_spec(kind)
    try:
        return int(spec.get("layer") or fallback)
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Path sampling
# ---------------------------------------------------------------------------

def _sample_polyline(points: list[tuple[float, float]], s_value: float) -> tuple[float, float, float]:
    if not points:
        return 512.0, 384.0, 0.0
    if len(points) == 1:
        return float(points[0][0]), float(points[0][1]), 0.0
    s_clamped = max(0.0, min(1.0, float(s_value)))
    lengths: list[float] = []
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        lengths.append(seg)
        total += seg
    if total <= 1e-6:
        return float(points[0][0]), float(points[0][1]), 0.0
    target = total * s_clamped
    walked = 0.0
    for i, length in enumerate(lengths):
        if walked + length >= target or i == len(lengths) - 1:
            start, end = points[i], points[i + 1]
            local = 0.0 if length <= 1e-6 else (target - walked) / length
            x = start[0] + (end[0] - start[0]) * local
            y = start[1] + (end[1] - start[1]) * local
            rotation = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
            return float(x), float(y), float(rotation)
        walked += length
    last, prev = points[-1], points[-2]
    rotation = math.degrees(math.atan2(last[1] - prev[1], last[0] - prev[0]))
    return float(last[0]), float(last[1]), float(rotation)


def _sample_grid_actor_on_path(
    item: dict[str, Any],
    path_points: list[tuple[float, float]],
    path_element: dict[str, Any],
    metrics: dict[str, float | int],
) -> tuple[float, float, float]:
    s_value = max(0.0, min(1.0, _grid_float(item, "s", 0.5)))
    x, y, rotation = _sample_polyline(path_points, s_value)
    path_props = path_element.get("props") if isinstance(path_element.get("props"), dict) else {}
    lane_count = max(1, _grid_int(item, "laneCount",
        _grid_int({"props": path_props}, "laneCount", int(path_props.get("lanes") or 2), 1), 1))
    lane_index = max(1, min(lane_count, _grid_int(item, "laneIndex", max(1, math.ceil(lane_count / 2)), 1)))
    explicit_offset = _grid_float(item, "laneOffset", 0.0)
    if abs(explicit_offset) <= 1e-6:
        half = (lane_count - 1) / 2.0
        lane_width = float(path_props.get("width") or float(metrics["cell"]) * 2.0) / lane_count
        explicit_offset = (lane_index - 1 - half) * lane_width
    angle = math.radians(rotation + 90.0)
    x += math.cos(angle) * explicit_offset
    y += math.sin(angle) * explicit_offset
    if item.get("rotation") is not None:
        rotation = _grid_rotation_value(item.get("rotation"), rotation)
    return x, y, rotation


# ---------------------------------------------------------------------------
# Element factory
# ---------------------------------------------------------------------------

def _make_grid_element(
    kind: str,
    item: dict[str, Any],
    metrics: dict[str, float | int],
    *,
    default_layer: int,
) -> dict[str, Any]:
    x, y, width, height = _grid_rect(item, metrics)
    rotation = _grid_rotation_value(item.get("rotation"), 0.0)
    layer = _grid_int(item, "layer", _grid_default_layer(kind, default_layer), 0)
    props = dict(item.get("props") or {}) if isinstance(item.get("props"), dict) else {}
    path_points = _grid_path_points(item, metrics)

    if kind == "road" and path_points:
        lane_count = _grid_int(item, "laneCount", _grid_int({"props": props}, "laneCount", 2, 1), 1)
        width_segments = _grid_float({"props": props}, "widthSegments", _grid_float(item, "rowSpan", 2.0))
        road_width = max(float(metrics["cell"]) * width_segments, float(metrics["cell"]) * 1.6)
        road_role = str(props.get("roadRole") or item.get("label") or "road").strip().lower()
        props = {**props, "pathPoints": path_points, "width": round(road_width, 2),
                 "lanes": lane_count, "roadRole": road_role}
        x, y, rotation = 0.0, 0.0, 0.0
        scale = 1.0
    elif kind in {"road", "crosswalk"}:
        if item.get("rotation") is None:
            rotation = 90.0 if height > width else 0.0
        major, minor = max(width, height), min(width, height)
        props = {**props, "length": round(major, 2), "width": round(minor, 2)}
        if kind == "road" and "lanes" not in props:
            props["lanes"] = max(1, min(4, int(round(minor / max(float(metrics["cell"]), 1.0)))))
        scale = 1.0
    else:
        scale = _grid_scale(kind, item, metrics)

    element = make_element(kind, x=x, y=y, rotation=rotation, scale=scale,
                           color=item.get("color") or None, layer=layer,
                           label=str(item.get("label") or "") or None, props=props)
    if item.get("id"):
        element["id"] = str(item["id"])
    return element


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def _is_grid_layout_plan(layout_plan: dict[str, Any]) -> bool:
    return any(key in layout_plan for key in ("map", "geometry", "environment", "actors"))


def build_scene_from_grid_layout_plan(
    layout_plan: dict[str, Any],
    prompt: str,
    current_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layout_plan = _topology_to_hybrid_plan(layout_plan)
    scene = default_scene() if not current_scene else deep_copy_scene(current_scene)
    scene["elements"] = []
    scene["title"] = str(layout_plan.get("title") or build_title(prompt))
    scene["prompt"] = prompt
    scene["warnings"] = list(layout_plan.get("warnings") or [])
    scene["plannerMode"] = "grid"
    map_info = layout_plan.get("map") if isinstance(layout_plan.get("map"), dict) else {}
    scene["layoutTemplate"] = f"grid_{_grid_int(map_info, 'cols', 10, 10)}x{_grid_int(map_info, 'rows', 10, 10)}"
    metrics = _grid_metrics(scene, layout_plan)

    geometry_items: list[Any] = layout_plan.get("geometry") if isinstance(layout_plan.get("geometry"), list) else []
    environment_items: list[Any] = layout_plan.get("environment") if isinstance(layout_plan.get("environment"), list) else []
    actor_items: list[Any] = layout_plan.get("actors") if isinstance(layout_plan.get("actors"), list) else []
    annotation_items: list[Any] = layout_plan.get("annotations") if isinstance(layout_plan.get("annotations"), list) else []

    path_index: dict[str, dict[str, Any]] = {}

    for items, default_layer in ((geometry_items, 1), (environment_items, 5)):
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            if not kind:
                continue
            element = _make_grid_element(kind, item, metrics, default_layer=default_layer)
            scene["elements"].append(element)
            props = element.get("props") if isinstance(element.get("props"), dict) else {}
            path_points_value = props.get("pathPoints")
            if item.get("id") and isinstance(path_points_value, list):
                path_points: list[tuple[float, float]] = [
                    (float(p[0]), float(p[1]))
                    for p in path_points_value
                    if isinstance(p, (tuple, list)) and len(p) >= 2
                ]
                if path_points:
                    path_index[str(item["id"])] = {"element": element, "points": path_points}

    for item in actor_items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        path_id = str(
            item.get("pathId")
            or (item.get("props") or {}).get("pathId")
            or (item.get("props") or {}).get("roadId")
            or (item.get("props") or {}).get("topologyRoadId")
            or ""
        ).strip()
        if path_id and path_id in path_index:
            rec = path_index[path_id]
            path_pts: list[tuple[float, float]] = rec["points"]
            path_el: dict[str, Any] = rec["element"]
            x, y, rotation = _sample_grid_actor_on_path(item, path_pts, path_el, metrics)
            scale = _grid_scale(kind, item, metrics)
            layer = _grid_int(item, "layer", _grid_default_layer(kind, 10), 0)
            props = dict(item.get("props") or {}) if isinstance(item.get("props"), dict) else {}
            element = make_element(kind, x=x, y=y, rotation=rotation, scale=scale,
                                   color=item.get("color") or None, layer=layer,
                                   label=str(item.get("label") or "") or None, props=props)
            if item.get("id"):
                element["id"] = str(item["id"])
            scene["elements"].append(element)
            continue
        scene["elements"].append(_make_grid_element(kind, item, metrics, default_layer=10))

    for item in annotation_items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        scene["elements"].append(_make_grid_element(kind, item, metrics, default_layer=20))

    return normalize_scene(scene)


def build_scene_from_layout_plan(
    layout_plan: dict[str, Any],
    prompt: str,
    current_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Entry point: always delegates to the grid builder."""
    return build_scene_from_grid_layout_plan(layout_plan, prompt, current_scene=current_scene)
