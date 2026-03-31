from __future__ import annotations
from typing import Any
from models import GenerateRequest
from ai_client import call_text_scene_planner
from vectorizer import vectorize_data_uri
from scene_engine import (
    generate_scene_heuristic,
    normalize_scene,
    render_scene_svg,
    summarize_scene,
    build_scene_from_layout_plan,
)
from scene_engine.heuristic import apply_spatial_layout


async def generate_structured_response(req: GenerateRequest) -> dict[str, Any]:
    planner = req.planner or "auto"
    warnings: list[str] = []
    scene: dict[str, Any] | None = None
    used = "heuristic"
    planner_raw_text: str | None = None
    planner_raw_scene: dict[str, Any] | None = None
    planner_layout_plan: dict[str, Any] | None = None
    planner_asset_resolution: dict[str, Any] | None = None
    planner_used_layout_plan = False

    if planner in {"auto", "llm"}:
        try:
            planned = await call_text_scene_planner(req)
            if isinstance(planned, dict) and "scene" in planned:
                planner_raw_text = planned.get("raw_text")
                planner_raw_scene = planned.get("raw_json")
                planner_asset_resolution = planned.get("asset_resolution")
                raw_scene_value = planned.get("raw_json")
                raw_scene = raw_scene_value if isinstance(raw_scene_value, dict) else {}
                layout_plan_value = raw_scene.get("layoutPlan")
                if isinstance(layout_plan_value, dict):
                    planner_layout_plan = layout_plan_value
                    scene = build_scene_from_layout_plan(
                        planner_layout_plan,
                        req.prompt,
                        current_scene=req.current_scene,
                    )
                    planner_used_layout_plan = True
                else:
                    scene = planned.get("scene")
            else:
                scene = planned
            used = "llm"
        except Exception as exc:
            warnings.append(f"Text planner fallback used: {exc}")
            if planner == "llm":
                scene = None

    if scene is None:
        scene, heuristic_warnings = generate_scene_heuristic(
            req.prompt, history=req.history, current_scene=req.current_scene,
        )
        warnings.extend(heuristic_warnings)
        used = "heuristic"

    scene = normalize_scene(scene)
    scene_before_layout = normalize_scene(scene)
    apply_spatial_layout(scene, req.prompt)
    scene = normalize_scene(scene)
    scene["prompt"] = req.prompt
    scene["warnings"] = list(dict.fromkeys([*scene.get("warnings", []), *warnings]))

    return {
        "mode": "structured",
        "planner": used,
        "summary": summarize_scene(scene),
        "scene": scene,
        "sceneBeforeLayout": scene_before_layout,
        "svg": render_scene_svg(scene),
        "warnings": scene["warnings"],
        "fallbackUsed": used != "llm",
        "plannerRawText": planner_raw_text,
        "plannerRawScene": planner_raw_scene,
        "plannerLayoutPlan": planner_layout_plan,
        "plannerAssetResolution": planner_asset_resolution,
        "plannerUsedLayoutPlan": planner_used_layout_plan,
    }
