from __future__ import annotations
from typing import Any
from models import GenerateRequest
from ai_client import call_text_scene_planner
from vectorizer import vectorize_data_uri
from scene_engine import generate_scene_heuristic, normalize_scene, render_scene_svg, summarize_scene
from scene_engine.heuristic import apply_spatial_layout


async def generate_structured_response(req: GenerateRequest) -> dict[str, Any]:
    planner = req.planner or "auto"
    warnings: list[str] = []
    scene: dict[str, Any] | None = None
    used = "heuristic"

    if planner in {"auto", "llm"}:
        try:
            scene = await call_text_scene_planner(req)
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
    apply_spatial_layout(scene, req.prompt)
    scene = normalize_scene(scene)
    scene["prompt"] = req.prompt
    scene["warnings"] = list(dict.fromkeys([*scene.get("warnings", []), *warnings]))

    return {
        "mode": "structured",
        "planner": used,
        "summary": summarize_scene(scene),
        "scene": scene,
        "svg": render_scene_svg(scene),
        "warnings": scene["warnings"],
        "fallbackUsed": used != "llm",
    }
