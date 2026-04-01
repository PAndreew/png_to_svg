from __future__ import annotations
import json, re, textwrap
import os
from typing import Any
import httpx
from models import OPENROUTER_API_KEY, TEXT_MODEL, IMAGE_MODEL, REVIEW_MODEL, GenerateRequest
from scene_engine import catalog, compact_json, normalize_scene, layout_planner_context
from planning_agent import build_asset_registry_context, resolve_prompt_assets, validate_layout_plan
import base64

PLANNER_BACKEND = str(os.getenv("PLANNER_BACKEND", "direct") or "direct").strip().lower()
PI_AGENT_URL = str(os.getenv("PI_AGENT_URL", "http://localhost:8787/plan") or "http://localhost:8787/plan").strip()
PI_AGENT_REVIEW_URL = str(os.getenv("PI_AGENT_REVIEW_URL", PI_AGENT_URL.replace("/plan", "/review")) or PI_AGENT_URL.replace("/plan", "/review")).strip()

SCENE_SYSTEM_PROMPT = textwrap.dedent("""
    You are a scene planner for automotive ODD pictograms.
    Produce JSON only. No markdown. No prose outside the JSON object.
    Use a hybrid road-geometry plus object-placement plan.
    Think in two internal phases: first build road geometry, then place objects onto that geometry using the same JSON language.
    The output schema is:
    {
      "version": "odd.scene.v1",
      "canvas": {"width": 1024, "height": 768, "background": "#f8fafc"},
      "title": "short title",
      "prompt": "user prompt",
      "warnings": ["optional warning"],
            "layoutPlan": {
                "map": {"cols": 10, "rows": 10},
                "topology": {
                    "roads": [
                        {
                            "id": "arterial_main",
                            "roadRole": "arterial",
                            "fromJunction": "west_entry",
                            "toJunction": "east_entry",
                            "laneCount": 4,
                            "widthSegments": 3.5,
                            "points": [{"col": 0, "row": 4}, {"col": 11, "row": 4}],
                            "props": {}
                        }
                    ],
                    "junctions": [
                        {
                            "id": "west_entry",
                            "kind": "entry",
                            "col": 0,
                            "row": 4,
                            "connectedRoadIds": ["arterial_main"],
                            "control": null,
                            "props": {}
                        }
                    ]
                },
                "geometry": [
                    {
                        "id": "road_main",
                        "kind": "road|crosswalk|intersection|t_junction|roundabout",
                        "col": 1,
                        "row": 3,
                        "colSpan": 8,
                        "rowSpan": 4,
                        "points": [{"col": 0, "row": 4}, {"col": 11, "row": 4}],
                        "rotation": 0,
                        "laneCount": 4,
                        "layer": 1,
                        "props": {"roadRole": "arterial"}
                    }
                ],
                "environment": [
                    {
                        "id": "tree1",
                        "kind": "tree|traffic_light|placeholder",
                        "col": 0,
                        "row": 1,
                        "colSpan": 1,
                        "rowSpan": 1,
                        "rotation": 0,
                        "layer": 2,
                        "props": {}
                    }
                ],
                "actors": [
                    {
                        "id": "car1",
                        "kind": "car|truck|bus|pedestrian|bicycle|placeholder",
                        "col": 7,
                        "row": 4,
                        "colSpan": 2,
                        "rowSpan": 1,
                        "pathId": "road_main",
                        "s": 0.8,
                        "laneIndex": 3,
                        "rotation": 180,
                        "layer": 10,
                        "props": {}
                    }
                ],
                "annotations": [
                    {
                        "id": "arrow1",
                        "kind": "arrow|placeholder",
                        "col": 5,
                        "row": 2,
                        "rotation": 0,
                        "layer": 4,
                        "props": {}
                    }
                ]
            },
      "elements": [
        {
          "id": "string",
          "kind": "road|intersection|t_junction|roundabout|crosswalk|car|truck|bus|pedestrian|bicycle|traffic_light|tree|arrow|placeholder",
          "label": "human readable label",
          "x": 0, "y": 0, "rotation": 0, "scale": 1, "layer": 0,
          "color": "#rrggbb",
          "props": {}
        }
      ]
    }
    Rules:
    - Use only the allowed kinds.
    - Always provide `layoutPlan` unless the prompt truly cannot be expressed with the available assets.
    - Behave like an asset-aware planning agent: first use the asset registry and resolved prompt entities, then compose the scene plan.
    - Prefer top-down, simple, flat pictogram scenes.
    - Keep the scene concise and editable.
    - If an asset is missing, emit kind="placeholder" with a short label.
    - Use `layoutPlan.map.cols` and `layoutPlan.map.rows` between 10 and 15. Pick the smallest size that comfortably fits the scene.
    - For multi-road scenes, include `layoutPlan.topology` with canonical road ids, road roles, road centerlines, and junction connectivity.
    - Represent the scene as a hybrid segment map: geometry occupies grid rectangles or point-defined road centerlines, actors occupy grid cells/spans or follow a road path.
    - Keep `layoutPlan.topology.roads[].id` aligned with road ids used in `layoutPlan.geometry` and actor `pathId`.
    - For a complex arterial, staggered junction, or curved connector, use `geometry[].points` to define the road centerline in grid space.
    - `points` are grid coordinates along the road centerline. Use them for arterials, curved roads, side-road connectors, and staggered approaches.
    - Roads and crossings belong in `layoutPlan.geometry`, not `actors`.
    - Crosswalks are overlays on top of road geometry and should usually use layer 2.
    - Actors should usually use layer 10.
    - Controls like stop/yield signs and traffic lights should usually use layer 4; roadside environment like trees should usually use layer 5; annotations can use layer 20.
    - Use 0° for right/east, 90° for down/south, 180° for left/west, -90° for up/north.
    - Cars usually occupy 2x1 segments, trucks and buses 3x1, pedestrians 1x1.
    - For a crossing pedestrian, place the pedestrian on crosswalk segments with a crossing rotation instead of inventing lane semantics.
    - When an actor belongs on a road, prefer `pathId` + `s` + `laneIndex` over vague lane text.
    - Prefer direct segment placement over `lane`, `slot`, `heading`, or relation phrases.
    - Use arrow props.style values such as straight, left, right, merge, uturn.
    - If you include `elements`, keep them minimal and consistent with `layoutPlan`.
    - Respect each asset's default footprint, orientation, and placement guidance.
    - Respect each asset's catalog group, layer group, and allowed placements.
    - Use layered rendering consistently: arterial/base roads 1, connector roads 2, markings/crosswalks 3, controls 4, environment 5, actors 10, annotations 20.
""").strip()

IMAGE_SYSTEM_PROMPT = textwrap.dedent("""
    You are a pictogram generator for an automotive company.
    Create a flat, minimal vector-art style traffic pictogram.
    Style rules:
    - white background
    - maximum 8 distinct fill colours
    - bold solid fills
    - black outlines on every major shape
    - orthographic / top-down traffic scenario rendering
    - no shading, texture, or photorealism
    - no text labels
""").strip()


def openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Pictogram Studio",
        "Content-Type": "application/json",
    }


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("No JSON object found in planner response")
    return json.loads(match.group(0))


async def call_sidecar_scene_planner(user_payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(PI_AGENT_URL, json=user_payload)

    if response.status_code != 200:
        raise RuntimeError(f"Planner sidecar error: {response.text[:400]}")

    data = response.json()
    raw_json = data.get("raw_json") if isinstance(data.get("raw_json"), dict) else extract_json_object(str(data.get("raw_text") or ""))
    return {
        "scene": normalize_scene(raw_json),
        "raw_text": data.get("raw_text") or "",
        "raw_json": raw_json,
        "tool_trace": data.get("tool_trace") or [],
        "geometry_draft": data.get("geometry_draft") if isinstance(data.get("geometry_draft"), dict) else None,
    }


async def call_sidecar_scene_reviewer(review_payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(PI_AGENT_REVIEW_URL, json=review_payload)

    if response.status_code != 200:
        raise RuntimeError(f"Reviewer sidecar error: {response.text[:400]}")

    data = response.json()
    raw_json = data.get("raw_json") if isinstance(data.get("raw_json"), dict) else extract_json_object(str(data.get("raw_text") or ""))
    return {
        "raw_text": data.get("raw_text") or "",
        "raw_json": raw_json,
    }


async def call_scene_reviewer(review_payload: dict[str, Any]) -> dict[str, Any]:
    if PLANNER_BACKEND in {"sidecar", "pi-sidecar", "agent-sidecar"}:
        return await call_sidecar_scene_reviewer(review_payload)

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": textwrap.dedent(
                f"""
                You are a multimodal scene reviewer for automotive pictograms.
                Inspect the provided hybrid road-geometry scene JSON and the rendered PNG.
                If the scene is good, return:
                {{"approved": true, "issues": [], "summary": "..."}}
                If there are issues, return:
                {{"approved": false, "issues": ["..."], "layoutPlan": {{... corrected grid layout plan ...}}, "summary": "..."}}
                Prefer correcting topology road connectivity, road centerline points, road roles, pathId/s/laneIndex actor placement, grid segments, rotations, and layers.
                Output JSON only.

                Review payload:
                {compact_json(review_payload)}
                """
            ).strip(),
        },
    ]
    image_data = str(review_payload.get("image") or "")
    if image_data:
        content.append({"type": "image_url", "image_url": {"url": image_data}})

    payload = {
        "model": REVIEW_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=openrouter_headers(),
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Scene reviewer error: {response.text[:400]}")

    data = response.json()
    content_value = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    raw_json = extract_json_object(str(content_value))
    return {
        "raw_text": str(content_value),
        "raw_json": raw_json,
    }


async def call_text_scene_planner(req: GenerateRequest) -> dict[str, Any]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    asset_resolution = resolve_prompt_assets(req.prompt)
    user_payload = {
        "prompt": req.prompt,
        "current_scene": req.current_scene,
        "recent_history": req.history[-6:],
        "allowed_assets": [item["kind"] for item in catalog()],
        "asset_resolution": asset_resolution,
        "asset_registry": build_asset_registry_context(),
        "layout_templates": layout_planner_context(),
        "asset_specs": [
            {
                "kind": item.get("kind"),
                "label": item.get("label"),
                "footprint": item.get("footprint"),
                "defaultScale": item.get("defaultScale"),
                "defaultRotation": item.get("defaultRotation"),
                "placement": item.get("placement"),
                "allowedPlacements": item.get("allowedPlacements"),
                "orientation": item.get("orientation"),
                "catalogGroup": item.get("catalogGroup"),
                "view": item.get("view"),
                "role": item.get("role"),
                "layerGroup": item.get("layerGroup"),
                "assetClass": item.get("assetClass"),
                "mobility": item.get("mobility"),
                "layer": item.get("layer"),
            }
            for item in catalog()
        ],
    }

    tool_trace: list[dict[str, Any]] = []
    geometry_draft: dict[str, Any] | None = None
    if PLANNER_BACKEND in {"sidecar", "pi-sidecar", "agent-sidecar"}:
        sidecar_result = await call_sidecar_scene_planner(user_payload)
        planned = sidecar_result.get("raw_json") or {}
        content = str(sidecar_result.get("raw_text") or "")
        tool_trace = list(sidecar_result.get("tool_trace") or [])
        geometry_draft_value = sidecar_result.get("geometry_draft")
        geometry_draft = geometry_draft_value if isinstance(geometry_draft_value, dict) else None
    else:
        payload = {
            "model": TEXT_MODEL,
            "messages": [
                {"role": "system", "content": SCENE_SYSTEM_PROMPT},
                {"role": "user", "content": compact_json(user_payload)},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=openrouter_headers(),
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(f"Text planner error: {response.text[:400]}")

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        planned = extract_json_object(content)
    validated_layout_plan = validate_layout_plan(planned.get("layoutPlan"))
    if validated_layout_plan:
        planned["layoutPlan"] = validated_layout_plan
    planned.setdefault("prompt", req.prompt)
    return {
        "scene": normalize_scene(planned),
        "raw_text": content,
        "raw_json": planned,
        "asset_resolution": asset_resolution,
        "tool_trace": tool_trace,
        "geometry_draft": geometry_draft,
    }


async def generate_image_data(prompt: str, history: list[dict[str, Any]] | None = None) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    full_prompt = prompt
    if not history:
        full_prompt = f"{IMAGE_SYSTEM_PROMPT}\n\nUser request: {prompt}"

    payload = {
        "model": IMAGE_MODEL,
        "prompt": full_prompt,
        "n": 1,
        "size": "512x512",
        "response_format": "b64_json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/images/generations",
            headers=openrouter_headers(),
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Image generation error: {response.text[:400]}")

    data = response.json()
    image_b64 = data.get("data", [{}])[0].get("b64_json") or ""
    if not image_b64:
        url = data.get("data", [{}])[0].get("url")
        if not url:
            raise RuntimeError("No image payload returned by image model")
        async with httpx.AsyncClient(timeout=60) as client:
            image_response = await client.get(url)
        image_b64 = base64.b64encode(image_response.content).decode()

    return f"data:image/png;base64,{image_b64}"
