from __future__ import annotations
import base64
from typing import Any
from models import GenerateRequest, ENABLE_INTERNAL_REVIEW
from ai_client import call_text_scene_planner, call_scene_reviewer
from vectorizer import vectorize_data_uri
from scene_engine import (
    generate_scene_heuristic,
    normalize_scene,
    render_scene_svg,
    summarize_scene,
    build_scene_from_layout_plan,
)
from scene_engine.heuristic import apply_spatial_layout


def _render_png_data_uri(svg_text: str) -> str:
    try:
        import cairosvg  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"CairoSVG is not available: {exc}") from exc

    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"))
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _materialize_scene(scene: dict[str, Any], prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    materialized = normalize_scene(scene)
    scene_before_layout = normalize_scene(materialized)
    apply_spatial_layout(materialized, prompt)
    materialized = normalize_scene(materialized)
    materialized["prompt"] = prompt
    return materialized, scene_before_layout


async def generate_structured_response(req: GenerateRequest) -> dict[str, Any]:
    planner = req.planner or "auto"
    warnings: list[str] = []
    scene: dict[str, Any] | None = None
    used = "heuristic"
    planner_raw_text: str | None = None
    planner_raw_scene: dict[str, Any] | None = None
    planner_layout_plan: dict[str, Any] | None = None
    planner_asset_resolution: dict[str, Any] | None = None
    planner_tool_trace: list[dict[str, Any]] | None = None
    planner_used_layout_plan = False
    review_raw_text: str | None = None
    review_raw_json: dict[str, Any] | None = None
    review_applied = False
    review_summary: str | None = None
    first_pass_scene: dict[str, Any] | None = None
    first_pass_svg: str | None = None
    stage_log: list[dict[str, Any]] = []

    stage_log.append({"key": "fetching_assets", "label": "fetching assets", "status": "started"})

    if planner in {"auto", "llm"}:
        try:
            planned = await call_text_scene_planner(req)
            stage_log[-1]["status"] = "completed"
            stage_log.append({"key": "generating_first_pass", "label": "generating first pass", "status": "started"})
            if isinstance(planned, dict) and "scene" in planned:
                planner_raw_text = planned.get("raw_text")
                planner_raw_scene = planned.get("raw_json")
                planner_asset_resolution = planned.get("asset_resolution")
                planner_tool_trace = planned.get("tool_trace")
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
            stage_log[-1]["status"] = "failed"
            warnings.append(f"Text planner fallback used: {exc}")
            if planner == "llm":
                scene = None

    if scene is None:
        if stage_log and stage_log[0]["key"] == "fetching_assets" and stage_log[0]["status"] == "started":
            stage_log[0]["status"] = "completed"
        if not stage_log or stage_log[-1]["key"] != "generating_first_pass":
            stage_log.append({"key": "generating_first_pass", "label": "generating first pass", "status": "started"})
        scene, heuristic_warnings = generate_scene_heuristic(
            req.prompt, history=req.history, current_scene=req.current_scene,
        )
        warnings.extend(heuristic_warnings)
        used = "heuristic"
    if stage_log and stage_log[-1]["key"] == "generating_first_pass":
        stage_log[-1]["status"] = "completed"

    scene, scene_before_layout = _materialize_scene(scene, req.prompt)
    scene["warnings"] = list(dict.fromkeys([*scene.get("warnings", []), *warnings]))
    first_pass_scene = normalize_scene(scene)
    first_pass_svg = render_scene_svg(first_pass_scene)

    if ENABLE_INTERNAL_REVIEW and used == "llm":
        stage_log.append({"key": "reviewing", "label": "reviewing", "status": "started"})
        try:
            review_result = await call_scene_reviewer(
                {
                    "prompt": req.prompt,
                    "layoutPlan": planner_layout_plan,
                    "scene": first_pass_scene,
                    "warnings": scene.get("warnings", []),
                    "image": _render_png_data_uri(first_pass_svg),
                }
            )
            review_raw_text = str(review_result.get("raw_text") or "")
            review_raw_json = review_result.get("raw_json") if isinstance(review_result.get("raw_json"), dict) else None
            if review_raw_json:
                review_summary = str(review_raw_json.get("summary") or "") or None
                issues_value = review_raw_json.get("issues")
                issues: list[Any] = issues_value if isinstance(issues_value, list) else []
                warnings.extend(str(issue) for issue in issues if issue)
                revised_layout_plan = review_raw_json.get("layoutPlan") if isinstance(review_raw_json.get("layoutPlan"), dict) else None
                revised_scene = review_raw_json.get("scene") if isinstance(review_raw_json.get("scene"), dict) else None
                approved = bool(review_raw_json.get("approved", True))
                if not approved and revised_layout_plan:
                    planner_layout_plan = revised_layout_plan
                    scene = build_scene_from_layout_plan(
                        revised_layout_plan,
                        req.prompt,
                        current_scene=req.current_scene,
                    )
                    scene, scene_before_layout = _materialize_scene(scene, req.prompt)
                    review_applied = True
                elif not approved and revised_scene:
                    scene, scene_before_layout = _materialize_scene(revised_scene, req.prompt)
                    review_applied = True
            stage_log[-1]["status"] = "completed"
        except Exception as exc:
            stage_log[-1]["status"] = "failed"
            warnings.append(f"Internal review skipped: {exc}")
    else:
        stage_log.append({"key": "reviewing", "label": "reviewing", "status": "skipped"})

    stage_log.append({"key": "final_render", "label": "final render", "status": "completed"})
    scene["warnings"] = list(dict.fromkeys([*scene.get("warnings", []), *warnings]))
    final_svg = render_scene_svg(scene)

    return {
        "mode": "structured",
        "planner": used,
        "summary": summarize_scene(scene),
        "scene": scene,
        "sceneBeforeLayout": scene_before_layout,
        "svg": final_svg,
        "warnings": scene["warnings"],
        "fallbackUsed": used != "llm",
        "plannerRawText": planner_raw_text,
        "plannerRawScene": planner_raw_scene,
        "plannerLayoutPlan": planner_layout_plan,
        "plannerAssetResolution": planner_asset_resolution,
        "plannerToolTrace": planner_tool_trace,
        "plannerUsedLayoutPlan": planner_used_layout_plan,
        "firstPassScene": first_pass_scene,
        "firstPassSvg": first_pass_svg,
        "reviewRawText": review_raw_text,
        "reviewRawJson": review_raw_json,
        "reviewApplied": review_applied,
        "reviewSummary": review_summary,
        "stageLog": stage_log,
    }
