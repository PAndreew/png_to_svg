from __future__ import annotations
import os
from typing import Any
from pydantic import BaseModel, Field

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TEXT_MODEL = os.getenv("TEXT_MODEL", "openai/gpt-4.1-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-schnell")


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
