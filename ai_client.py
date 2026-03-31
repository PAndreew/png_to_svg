from __future__ import annotations
import json, re, textwrap
from typing import Any
import httpx
from models import OPENROUTER_API_KEY, TEXT_MODEL, IMAGE_MODEL, GenerateRequest
from scene_engine import catalog, compact_json, normalize_scene, layout_planner_context
from planning_agent import build_asset_registry_context, resolve_prompt_assets, validate_layout_plan
import base64

SCENE_SYSTEM_PROMPT = textwrap.dedent("""
    You are a scene planner for automotive ODD pictograms.
    Produce JSON only. No markdown. No prose outside the JSON object.
        Prefer symbolic placement over raw coordinates.
        The output schema is:
    {
      "version": "odd.scene.v1",
      "canvas": {"width": 1024, "height": 768, "background": "#f8fafc"},
      "title": "short title",
      "prompt": "user prompt",
      "warnings": ["optional warning"],
            "layoutPlan": {
                "layout": {"template": "straight_road|crosswalk_road|intersection|t_junction|roundabout|highway_3_lane"},
                "static": [
                    {
                        "id": "string",
                        "kind": "traffic_light|tree|placeholder|...",
                        "label": "human readable label",
                        "anchor": "template anchor name",
                        "scale": 1,
                        "rotation": 0,
                        "color": "#rrggbb",
                        "props": {}
                    }
                ],
                "dynamic": [
                    {
                        "id": "string",
                        "kind": "car|truck|bus|pedestrian|bicycle|placeholder",
                        "label": "human readable label",
                        "lane": "template lane name",
                        "laneIndex": 1,
                        "slot": 1,
                        "slotCount": 5,
                        "s": 0.0,
                        "heading": "forward|reverse",
                        "relation": "behind:other_id|ahead_of:other_id|approaching:other_id|next_to:other_id",
                        "scale": 1,
                        "color": "#rrggbb",
                        "props": {}
                    }
                ],
                "annotations": [
                    {
                        "id": "string",
                        "kind": "arrow|placeholder",
                        "anchor": "template anchor name",
                        "rotation": 0,
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
    - Always provide `layoutPlan` unless the prompt truly cannot be expressed with the available templates.
    - Behave like an asset-aware planning agent: first use the asset registry and resolved prompt entities, then compose the scene plan.
    - Prefer top-down, simple, flat pictogram scenes.
    - Keep the scene concise and editable.
    - If an asset is missing, emit kind="placeholder" with a short label.
    - Roads should be represented through `layoutPlan.layout.template`; only use raw road elements as fallback.
    - Use arrow props.style values such as straight, left, right, merge, uturn.
    - In `layoutPlan.dynamic`, use `lane` plus progress `s` from 0.0 to 1.0 instead of `x` and `y`.
    - Prefer `laneIndex` + `slot` for vehicles when a laneed road/highway template is used.
    - `slot` means ordinal position along the lane, not pixel coordinates.
    - In `layoutPlan.static`, bind assets to named anchors instead of inventing coordinates.
    - If you include `elements`, keep them minimal and consistent with `layoutPlan`.
    - Respect each asset's default footprint, orientation, and placement guidance.
    - Respect each asset's catalog group, layer group, and allowed placements.
    - Use layer bands consistently: layout near 0-1, environment near 4-5, traffic near 10-11, actors near 12-13, props near 16, annotations near 20+.
    - Vehicles should be centered on lanes, not stacked side-by-side without road alignment.
    - Trucks and buses should occupy more space than cars; pedestrians belong beside roads or on crossings.
    - Use rotation to align vehicles with road direction: 0/180 for horizontal travel, 90/-90 for vertical travel.
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
