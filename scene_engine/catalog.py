from __future__ import annotations
from typing import Any
import copy

ASSET_CATALOG: list[dict[str, Any]] = [
    {"kind": "car", "label": "Car", "category": "vehicles", "description": "Compact passenger vehicle, top-down pictogram.", "defaultColor": "#2563eb"},
    {"kind": "truck", "label": "Truck", "category": "vehicles", "description": "Box truck / heavy vehicle, top-down pictogram.", "defaultColor": "#f97316"},
    {"kind": "bus", "label": "Bus", "category": "vehicles", "description": "Bus pictogram with windows and wheels.", "defaultColor": "#ef4444"},
    {"kind": "pedestrian", "label": "Pedestrian", "category": "actors", "description": "Walking pedestrian icon.", "defaultColor": "#111827"},
    {"kind": "bicycle", "label": "Bicycle", "category": "actors", "description": "Cyclist / bicycle actor.", "defaultColor": "#16a34a"},
    {"kind": "traffic_light", "label": "Traffic Light", "category": "infrastructure", "description": "Traffic signal pole with red/yellow/green lights.", "defaultColor": "#111827"},
    {"kind": "tree", "label": "Tree", "category": "environment", "description": "Simple roadside tree.", "defaultColor": "#16a34a"},
    {"kind": "arrow", "label": "Arrow", "category": "annotations", "description": "Movement arrow, straight or turning.", "defaultColor": "#22c55e"},
    {"kind": "crosswalk", "label": "Crosswalk", "category": "roads", "description": "Zebra crossing marking.", "defaultColor": "#ffffff"},
    {"kind": "road", "label": "Road", "category": "roads", "description": "Straight road segment.", "defaultColor": "#6b7280"},
    {"kind": "intersection", "label": "Intersection", "category": "roads", "description": "Four-way intersection.", "defaultColor": "#6b7280"},
    {"kind": "t_junction", "label": "T-Junction", "category": "roads", "description": "T-junction road layout.", "defaultColor": "#6b7280"},
    {"kind": "roundabout", "label": "Roundabout", "category": "roads", "description": "Roundabout road layout.", "defaultColor": "#6b7280"},
]

DEFAULT_CANVAS = {"width": 1024, "height": 768, "background": "#f8fafc"}
ALLOWED_KINDS = {item["kind"] for item in ASSET_CATALOG} | {"placeholder"}
COLOR_WORDS = {
    "red": "#ef4444", "blue": "#2563eb", "green": "#16a34a", "orange": "#f97316",
    "yellow": "#eab308", "purple": "#7c3aed", "black": "#111827", "white": "#ffffff",
    "gray": "#6b7280", "grey": "#6b7280",
}


def catalog() -> list[dict[str, Any]]:
    return copy.deepcopy(ASSET_CATALOG)


def default_color(kind: str) -> str:
    for item in ASSET_CATALOG:
        if item["kind"] == kind:
            return item["defaultColor"]
    return "#94a3b8"


def default_label(kind: str) -> str:
    return kind.replace("_", " ").title()
