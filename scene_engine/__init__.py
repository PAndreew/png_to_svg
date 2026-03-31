from .catalog import catalog, default_color, default_label, ASSET_CATALOG, ALLOWED_KINDS, DEFAULT_CANVAS, COLOR_WORDS
from .normalize import (
    normalize_scene, ensure_color, clamp_number, default_scene, new_id, xml_escape,
    compact_json, deep_copy_scene, build_transform, make_element, SVG_NS,
)
from .heuristic import (
    generate_scene_heuristic, looks_like_new_scene, detect_layout, build_layout,
    apply_prompt_modifiers, has_actor, current_layout_kind, needs_arrow,
    ensure_motion_arrow, dedupe_strings,
)
from .renderers import render_scene_svg, render_element
from .summary import summarize_scene

__all__ = [
    "catalog", "default_color", "default_label", "ASSET_CATALOG", "ALLOWED_KINDS",
    "DEFAULT_CANVAS", "COLOR_WORDS", "normalize_scene", "ensure_color", "clamp_number",
    "default_scene", "new_id", "xml_escape", "compact_json", "deep_copy_scene",
    "build_transform", "make_element", "SVG_NS", "generate_scene_heuristic",
    "render_scene_svg", "render_element", "summarize_scene",
]
