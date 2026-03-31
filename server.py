"""
Pictogram Studio backend
========================

Primary flow
------------
Prompt -> structured scene JSON -> deterministic SVG renderer.

Fallbacks
---------
1. Local heuristic planner if the text model is unavailable or returns invalid JSON.
2. Existing image-generation + raster-to-SVG vectorisation pipeline for last-resort fallback.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / ".env")

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from convert import build_layer_path, build_svg, quantise
from scene_engine import (
    catalog,
    compact_json,
    generate_scene_heuristic,
    normalize_scene,
    render_scene_svg,
    summarize_scene,
)


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TEXT_MODEL = os.getenv("TEXT_MODEL", "openai/gpt-4.1-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-schnell")

SCENE_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a scene planner for automotive ODD pictograms.

    Produce JSON only. No markdown. No prose outside the JSON object.

    The output schema is:
    {
      "version": "odd.scene.v1",
      "canvas": {"width": 1024, "height": 768, "background": "#f8fafc"},
      "title": "short title",
      "prompt": "user prompt",
      "warnings": ["optional warning"],
      "elements": [
        {
          "id": "string",
          "kind": "road|intersection|t_junction|roundabout|crosswalk|car|truck|bus|pedestrian|bicycle|traffic_light|tree|arrow|placeholder",
          "label": "human readable label",
          "x": 0,
          "y": 0,
          "rotation": 0,
          "scale": 1,
          "layer": 0,
          "color": "#rrggbb",
          "props": {}
        }
      ]
    }

    Rules:
    - Use only the allowed kinds.
    - Prefer top-down, simple, flat pictogram scenes.
    - Keep the scene concise and editable.
    - If an asset is missing, emit kind="placeholder" with a short label.
    - Roads should be represented with road, intersection, t_junction, roundabout, or crosswalk assets.
    - Use arrow props.style values such as straight, left, right, merge, uturn.
    - Keep coordinates inside a 1024x768 canvas.
    """
).strip()

IMAGE_SYSTEM_PROMPT = textwrap.dedent(
    """
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
    """
).strip()


class ChatRequest(BaseModel):
    prompt: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ToSvgRequest(BaseModel):
    image: str
    colors: int = 10


class GenerateRequest(BaseModel):
    prompt: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    current_scene: dict[str, Any] | None = None
    planner: str | None = None


app = FastAPI(title="Pictogram Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    user_payload = {
        "prompt": req.prompt,
        "current_scene": req.current_scene,
        "recent_history": req.history[-6:],
        "allowed_assets": [item["kind"] for item in catalog()],
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
    planned.setdefault("prompt", req.prompt)
    return normalize_scene(planned)


async def generate_image_data(
    prompt: str, history: list[dict[str, Any]] | None = None
) -> str:
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


def vectorize_data_uri(data_uri: str, colors: int = 10) -> dict[str, Any]:
    _, _, encoded = data_uri.partition(",")
    image_bytes = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    array = np.array(image)
    labels, centers = quantise(array, max(2, min(32, colors)))
    _, counts = np.unique(labels, return_counts=True)
    order = np.argsort(-counts)

    layers = []
    for rank, idx in enumerate(order):
        color = centers[idx]
        color_hex = f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"
        mask = (labels == idx).astype(np.uint8)
        path_d = build_layer_path(mask, simplify_eps=1.0, min_area=16)
        layers.append(
            {
                "id": f"color-{rank}",
                "label": f"Layer {rank + 1}: {color_hex}",
                "color": color_hex,
                "path_d": path_d,
            }
        )

    svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + build_svg(
        image.width, image.height, layers
    )
    return {"svg": svg, "width": image.width, "height": image.height}


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
            req.prompt,
            history=req.history,
            current_scene=req.current_scene,
        )
        warnings.extend(heuristic_warnings)
        used = "heuristic"

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


@app.get("/")
def root() -> FileResponse:
    return FileResponse(HERE / "app.html")


@app.get("/api/assets")
def get_assets() -> JSONResponse:
    return JSONResponse({"assets": catalog()})


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> JSONResponse:
    try:
        return JSONResponse(await generate_structured_response(req))
    except Exception as structured_error:
        try:
            image = await generate_image_data(req.prompt, req.history)
            vectorized = vectorize_data_uri(image, colors=10)
            return JSONResponse(
                {
                    "mode": "fallback-image",
                    "planner": "image-vectorized",
                    "summary": "Raster fallback rendered and vectorized.",
                    "scene": None,
                    "svg": vectorized["svg"],
                    "warnings": [f"Structured generation failed: {structured_error}"],
                    "fallbackUsed": True,
                    "image": image,
                }
            )
        except Exception as fallback_error:
            raise HTTPException(
                status_code=500,
                detail=f"Structured generation failed ({structured_error}); fallback failed ({fallback_error})",
            ) from fallback_error


@app.post("/api/chat")
async def chat(req: ChatRequest) -> JSONResponse:
    try:
        return JSONResponse(
            {"image": await generate_image_data(req.prompt, req.history)}
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/to-svg")
async def to_svg(req: ToSvgRequest) -> JSONResponse:
    try:
        return JSONResponse(vectorize_data_uri(req.image, colors=req.colors))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
