from __future__ import annotations
import os
from typing import Any, Literal
from pydantic import BaseModel, Field

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TEXT_MODEL = os.getenv("TEXT_MODEL", "openai/gpt-4.1-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-schnell")
REVIEW_MODEL = os.getenv("REVIEW_MODEL", os.getenv("TEXT_MODEL", "openai/gpt-4.1-mini"))
ENABLE_INTERNAL_REVIEW = os.getenv("ENABLE_INTERNAL_REVIEW", "1").strip().lower() not in {"0", "false", "no", "off"}


class ChatRequest(BaseModel):
    prompt: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ToSvgRequest(BaseModel):
    image: str
    colors: int = 8
    transparent_background: bool = False
    alpha_threshold: int = 8


class SaveAssetRequest(BaseModel):
    name: str
    svg: str
    overwrite: bool = False
    orientation: str = "right"


class GenerateRequest(BaseModel):
    prompt: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    current_scene: dict[str, Any] | None = None
    planner: str | None = None


class AssetResolutionItem(BaseModel):
    term: str
    kind: str
    label: str
    source: Literal["alias", "catalog", "fallback"] = "catalog"
    category: str | None = None
    confidence: float = 1.0


class AssetResolutionReport(BaseModel):
    ok: bool = True
    requested: list[AssetResolutionItem] = Field(default_factory=list)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class LayoutTemplateModel(BaseModel):
    template: Literal[
        "straight_road",
        "crosswalk_road",
        "intersection",
        "t_junction",
        "roundabout",
        "highway_3_lane",
    ] = "straight_road"


class StaticPlanItemModel(BaseModel):
    id: str | None = None
    kind: str
    label: str | None = None
    anchor: str | None = None
    zone: str | None = None
    rotation: float | None = None
    scale: float | None = None
    color: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class DynamicPlanItemModel(BaseModel):
    id: str | None = None
    kind: str
    label: str | None = None
    lane: str | None = None
    laneIndex: int | None = None
    slot: int | None = None
    slotCount: int | None = None
    s: float | None = None
    heading: Literal["forward", "reverse"] = "forward"
    relation: str | None = None
    scale: float | None = None
    color: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class AnnotationPlanItemModel(BaseModel):
    id: str | None = None
    kind: str = "arrow"
    label: str | None = None
    anchor: str | None = None
    rotation: float | None = None
    scale: float | None = None
    color: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class LayoutPlanModel(BaseModel):
    title: str | None = None
    warnings: list[str] = Field(default_factory=list)
    layout: LayoutTemplateModel = Field(default_factory=LayoutTemplateModel)
    static: list[StaticPlanItemModel] = Field(default_factory=list)
    dynamic: list[DynamicPlanItemModel] = Field(default_factory=list)
    annotations: list[AnnotationPlanItemModel] = Field(default_factory=list)
