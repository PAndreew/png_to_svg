from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any

from models import AssetResolutionItem, AssetResolutionReport, LayoutPlanModel
from scene_engine import catalog, catalog_by_group

ALIASES: dict[str, dict[str, str]] = {
    "car": {"kind": "car", "category": "vehicles"},
    "vehicle": {"kind": "car", "category": "vehicles"},
    "ego": {"kind": "car", "category": "vehicles"},
    "truck": {"kind": "truck", "category": "vehicles"},
    "lorry": {"kind": "truck", "category": "vehicles"},
    "bus": {"kind": "bus", "category": "vehicles"},
    "bike": {"kind": "bicycle", "category": "actors"},
    "bicycle": {"kind": "bicycle", "category": "actors"},
    "cyclist": {"kind": "bicycle", "category": "actors"},
    "pedestrian": {"kind": "pedestrian", "category": "actors"},
    "walker": {"kind": "pedestrian", "category": "actors"},
    "person": {"kind": "pedestrian", "category": "actors"},
    "traffic light": {"kind": "traffic_light", "category": "infrastructure"},
    "traffic signal": {"kind": "traffic_light", "category": "infrastructure"},
    "tree": {"kind": "tree", "category": "environment"},
    "arrow": {"kind": "arrow", "category": "annotations"},
    "crosswalk": {"kind": "crosswalk", "category": "roads"},
    "pedestrian crossing": {"kind": "crosswalk", "category": "roads"},
    "zebra crossing": {"kind": "crosswalk", "category": "roads"},
    "road": {"kind": "road", "category": "roads"},
    "highway": {"kind": "road", "category": "roads"},
    "intersection": {"kind": "intersection", "category": "roads"},
    "t junction": {"kind": "t_junction", "category": "roads"},
    "t-junction": {"kind": "t_junction", "category": "roads"},
    "roundabout": {"kind": "roundabout", "category": "roads"},
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _catalog_index() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    assets = catalog()
    by_kind = {str(item.get("kind")): item for item in assets}
    by_term: dict[str, dict[str, Any]] = {}
    for item in assets:
        kind = _normalize(str(item.get("kind") or ""))
        label = _normalize(str(item.get("label") or ""))
        category = _normalize(str(item.get("category") or ""))
        for term in {kind, label, category, label.replace("_", " ")}:
            if term:
                by_term.setdefault(term, item)
    return assets, by_kind, by_term


def resolve_prompt_assets(prompt: str) -> dict[str, Any]:
    text = _normalize(prompt)
    assets, by_kind, by_term = _catalog_index()
    requested: list[AssetResolutionItem] = []
    seen_terms: set[str] = set()

    for phrase in sorted(ALIASES.keys(), key=len, reverse=True):
        if phrase in seen_terms:
            continue
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            payload = ALIASES[phrase]
            item = by_kind.get(payload["kind"])
            if item:
                requested.append(
                    AssetResolutionItem(
                        term=phrase,
                        kind=str(item.get("kind")),
                        label=str(item.get("label") or item.get("kind")),
                        source="alias",
                        category=str(item.get("category") or payload.get("category") or ""),
                        confidence=0.98,
                    )
                )
                seen_terms.add(phrase)

    token_candidates = re.findall(r"[a-zA-Z][a-zA-Z_\-]*", text)
    for token in token_candidates:
        if token in seen_terms:
            continue
        item = by_term.get(token)
        if item:
            requested.append(
                AssetResolutionItem(
                    term=token,
                    kind=str(item.get("kind")),
                    label=str(item.get("label") or item.get("kind")),
                    source="catalog",
                    category=str(item.get("category") or ""),
                    confidence=0.9,
                )
            )
            seen_terms.add(token)

    unique_requested: list[AssetResolutionItem] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in requested:
        pair = (item.term, item.kind)
        if pair in seen_pairs:
            continue
        unique_requested.append(item)
        seen_pairs.add(pair)

    missing: list[dict[str, Any]] = []
    if not unique_requested:
        words = [word for word in token_candidates if len(word) > 3]
        close = get_close_matches(" ".join(words[:2]), list(by_term.keys()), n=5, cutoff=0.7)
        if close:
            missing.append({"term": "prompt_entities", "alternatives": close})

    message = "All requested assets resolved." if not missing else "Some prompt terms need asset substitutions."
    report = AssetResolutionReport(
        ok=not missing,
        requested=unique_requested,
        missing=missing,
        message=message,
    )
    return report.model_dump()


def build_asset_registry_context() -> dict[str, Any]:
    grouped = catalog_by_group()
    summary: dict[str, list[dict[str, Any]]] = {}
    for group, items in grouped.items():
        summary[group] = [
            {
                "kind": item.get("kind"),
                "label": item.get("label"),
                "category": item.get("category"),
                "placement": item.get("placement"),
                "allowedPlacements": item.get("allowedPlacements"),
                "assetClass": item.get("assetClass"),
                "layerGroup": item.get("layerGroup"),
            }
            for item in items
        ]
    return {"groups": summary}


def validate_layout_plan(layout_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(layout_plan, dict):
        return None
    try:
        validated = LayoutPlanModel.model_validate(layout_plan)
    except Exception:
        return None
    return validated.model_dump(exclude_none=True)
