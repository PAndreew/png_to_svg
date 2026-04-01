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


class GridMapModel(BaseModel):
    cols: int = Field(default=10, ge=10, le=15)
    rows: int = Field(default=10, ge=10, le=15)


class GridPointModel(BaseModel):
    col: float = 0.0
    row: float = 0.0


class TopologyRoadModel(BaseModel):
    id: str
    roadRole: str | None = None
    fromJunction: str | None = None
    toJunction: str | None = None
    laneCount: int = Field(default=2, ge=1, le=6)
    widthSegments: float | None = Field(default=None, ge=1.0, le=6.0)
    points: list[GridPointModel] = Field(default_factory=list)
    props: dict[str, Any] = Field(default_factory=dict)


class TopologyJunctionModel(BaseModel):
    id: str
    kind: Literal[
        "intersection",
        "t_junction",
        "merge",
        "entry",
        "exit",
        "roundabout",
        "crossing",
        "bend",
    ] = "intersection"
    col: float = 0.0
    row: float = 0.0
    connectedRoadIds: list[str] = Field(default_factory=list)
    control: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class TopologyPlanModel(BaseModel):
    roads: list[TopologyRoadModel] = Field(default_factory=list)
    junctions: list[TopologyJunctionModel] = Field(default_factory=list)


class GridPlacementItemModel(BaseModel):
    id: str | None = None
    kind: str
    label: str | None = None
    col: int = Field(default=0, ge=0)
    row: int = Field(default=0, ge=0)
    colSpan: int = Field(default=1, ge=1)
    rowSpan: int = Field(default=1, ge=1)
    points: list[GridPointModel] = Field(default_factory=list)
    pathId: str | None = None
    s: float | None = None
    laneIndex: int | None = None
    laneCount: int | None = None
    laneOffset: float | None = None
    rotation: float | None = None
    scale: float | None = None
    layer: int | None = None
    color: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


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
    heading: str = "forward"
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
    map: GridMapModel | None = None
    topology: TopologyPlanModel | None = None
    geometry: list[GridPlacementItemModel] = Field(default_factory=list)
    environment: list[GridPlacementItemModel] = Field(default_factory=list)
    actors: list[GridPlacementItemModel] = Field(default_factory=list)
    layout: LayoutTemplateModel = Field(default_factory=LayoutTemplateModel)
    static: list[StaticPlanItemModel] = Field(default_factory=list)
    dynamic: list[DynamicPlanItemModel] = Field(default_factory=list)
    annotations: list[AnnotationPlanItemModel | GridPlacementItemModel] = Field(default_factory=list)
