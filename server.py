"""Pictogram Studio — FastAPI server."""
from __future__ import annotations
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
sys.path.insert(0, str(HERE))

from models import ChatRequest, ToSvgRequest, GenerateRequest
from generator import generate_structured_response
from vectorizer import vectorize_data_uri
from ai_client import generate_image_data
from scene_engine import catalog

app = FastAPI(title="Pictogram Studio")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


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
            return JSONResponse({
                "mode": "fallback-image",
                "planner": "image-vectorized",
                "summary": "Raster fallback rendered and vectorized.",
                "scene": None,
                "svg": vectorized["svg"],
                "warnings": [f"Structured generation failed: {structured_error}"],
                "fallbackUsed": True,
                "image": image,
            })
        except Exception as fallback_error:
            raise HTTPException(
                status_code=500,
                detail=f"Structured generation failed ({structured_error}); fallback failed ({fallback_error})",
            ) from fallback_error


@app.post("/api/chat")
async def chat(req: ChatRequest) -> JSONResponse:
    try:
        return JSONResponse({"image": await generate_image_data(req.prompt, req.history)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/to-svg")
async def to_svg(req: ToSvgRequest) -> JSONResponse:
    try:
        return JSONResponse(vectorize_data_uri(req.image, colors=req.colors))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
