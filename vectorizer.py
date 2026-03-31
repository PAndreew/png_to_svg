from __future__ import annotations
import base64, io
from typing import Any
import numpy as np
from PIL import Image, ImageFilter
from convert import build_layer_path, build_svg
from skimage.feature import canny
from skimage.filters import gaussian
from skimage.filters.rank import modal
from skimage.measure import label as measure_label
from skimage.morphology import closing, dilation, disk


def _palette_quantize_pixels(
    pixels: np.ndarray, colors: int
) -> tuple[np.ndarray, np.ndarray]:
    if pixels.size == 0:
        return np.empty((0,), dtype=np.uint8), np.empty((0, 3), dtype=np.uint8)

    n_colors = max(1, min(10, max(8, int(colors))))
    if len(pixels) == 1:
        return np.zeros(1, dtype=np.uint8), pixels.astype(np.uint8)

    image = Image.fromarray(pixels.reshape((-1, 1, 3)).astype(np.uint8), mode="RGB")
    quantized = image.quantize(
        colors=min(n_colors, len(np.unique(pixels, axis=0))),
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    labels = np.array(quantized, dtype=np.uint8).reshape(-1)
    palette = np.array(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)
    centers = palette[: int(labels.max()) + 1]
    return labels, centers


def _palette_quantize_image(
    image: Image.Image, colors: int
) -> tuple[np.ndarray, np.ndarray]:
    n_colors = max(1, min(10, max(8, int(colors))))
    filtered = image.filter(ImageFilter.MedianFilter(size=5))
    quantized = filtered.quantize(
        colors=n_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    labels = np.array(quantized, dtype=np.uint8)
    palette = np.array(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)
    centers = palette[: int(labels.max()) + 1]
    return labels, centers


def _detect_white_background(rgb: np.ndarray, alpha: np.ndarray, threshold: int) -> np.ndarray:
    brightness = rgb.mean(axis=2)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    white_like = (brightness >= threshold) & (spread <= 18) & (alpha >= max(1, threshold // 2))
    components = np.asarray(measure_label(white_like, connectivity=1), dtype=np.int32)
    background = np.zeros(rgb.shape[:2], dtype=bool)
    for component_id in range(1, int(components.max()) + 1):
        component = components == component_id
        touches_border = (
            component[0, :].any()
            or component[-1, :].any()
            or component[:, 0].any()
            or component[:, -1].any()
        )
        if touches_border:
            background |= component
    return background


def _crop_to_visible(rgb: np.ndarray, visible_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    ys, xs = np.where(visible_mask)
    if len(xs) == 0 or len(ys) == 0:
        return rgb, visible_mask, (0, 0)
    min_x, max_x = int(xs.min()), int(xs.max())
    min_y, max_y = int(ys.min()), int(ys.max())
    cropped_rgb = rgb[min_y:max_y + 1, min_x:max_x + 1]
    cropped_mask = visible_mask[min_y:max_y + 1, min_x:max_x + 1]
    return cropped_rgb, cropped_mask, (min_x, min_y)


def _merge_similar_colors(
    labels: np.ndarray,
    centers: np.ndarray,
    visible_mask: np.ndarray,
    distance_threshold: float = 26.0,
) -> tuple[np.ndarray, np.ndarray]:
    if centers.size == 0:
        return labels, centers

    counts = np.bincount(labels[visible_mask].reshape(-1), minlength=len(centers))
    order = np.argsort(-counts)
    mapping = np.arange(len(centers), dtype=np.int32)

    for source in order[::-1]:
        if counts[source] == 0:
            continue
        best_target = source
        best_count = counts[source]
        for target in order:
            if target == source or counts[target] == 0:
                continue
            distance = float(np.linalg.norm(centers[source].astype(np.float32) - centers[target].astype(np.float32)))
            if distance <= distance_threshold and counts[target] >= best_count:
                best_target = target
                best_count = counts[target]
        mapping[source] = best_target

    remapped = labels.astype(np.int32).copy()
    remapped[visible_mask] = mapping[labels[visible_mask]]
    unique_targets = [idx for idx in order if counts[idx] > 0 and mapping[idx] == idx]
    if not unique_targets:
        unique_targets = [int(order[0])]
    reindex = {target: new_idx for new_idx, target in enumerate(unique_targets)}
    merged_labels = labels.astype(np.uint8).copy()
    for target, new_idx in reindex.items():
        merged_labels[remapped == target] = new_idx
    merged_centers = np.array([centers[target] for target in unique_targets], dtype=np.uint8)
    return merged_labels, merged_centers


def _normalize_regions(labels: np.ndarray, rgb: np.ndarray, visible_mask: np.ndarray) -> np.ndarray:
    if not visible_mask.any():
        return labels

    normalized = labels.copy()
    luminance = np.dot(rgb.astype(np.float32), np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)) / 255.0
    blurred = gaussian(luminance, sigma=1.0, preserve_range=True)
    edges = canny(blurred, sigma=1.2, low_threshold=0.04, high_threshold=0.14)

    label_boundaries = np.zeros_like(visible_mask, dtype=bool)
    label_boundaries[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    label_boundaries[1:, :] |= labels[1:, :] != labels[:-1, :]

    blocked = dilation(edges | label_boundaries, footprint=disk(1))
    regions = np.asarray(measure_label(visible_mask & ~blocked, connectivity=1), dtype=np.int32)
    for region_id in range(1, int(regions.max()) + 1):
        region = regions == region_id
        region_size = int(region.sum())
        if region_size < 24:
            continue
        region_labels = labels[region]
        if region_labels.size == 0:
            continue
        dominant = int(np.bincount(region_labels, minlength=int(labels.max()) + 1).argmax())
        normalized[region] = dominant

    return normalized


def _smooth_labels(
    labels: np.ndarray, visible_mask: np.ndarray | None = None
) -> np.ndarray:
    if labels.size == 0:
        return labels
    if visible_mask is not None:
        seeded = labels.astype(np.uint8).copy()
        visible_values = seeded[visible_mask]
        fallback = int(np.bincount(visible_values).argmax()) if visible_values.size else 0
        seeded[~visible_mask] = fallback
        smoothed = modal(seeded, disk(2))
        smoothed = np.where(visible_mask, smoothed, labels)
    else:
        smoothed = modal(labels.astype(np.uint8), disk(2))
    return smoothed.astype(np.uint8)


def _clean_mask(mask: np.ndarray, min_area: int) -> np.ndarray:
    cleaned = np.zeros_like(mask, dtype=bool)
    labeled = np.asarray(measure_label(mask.astype(bool), connectivity=1), dtype=np.int32)
    for component_id in range(1, int(labeled.max()) + 1):
        component = np.asarray(labeled == component_id, dtype=bool)
        if int(component.sum()) >= min_area:
            cleaned |= component

    inverse = ~cleaned
    holes = np.asarray(measure_label(inverse, connectivity=1), dtype=np.int32)
    for component_id in range(1, int(holes.max()) + 1):
        component = np.asarray(holes == component_id, dtype=bool)
        touches_border = (
            component[0, :].any()
            or component[-1, :].any()
            or component[:, 0].any()
            or component[:, -1].any()
        )
        if not touches_border and int(component.sum()) <= min_area:
            cleaned |= component

    cleaned = closing(cleaned, footprint=disk(1))
    return cleaned.astype(np.uint8)


def vectorize_data_uri(
    data_uri: str,
    colors: int = 8,
    transparent_background: bool = False,
    alpha_threshold: int = 8,
) -> dict[str, Any]:
    _, _, encoded = data_uri.partition(",")
    image_bytes = base64.b64decode(encoded)
    rgba_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = rgba_image.size
    rgba = np.array(rgba_image)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    warnings: list[str] = []
    target_colors = max(8, min(10, int(colors)))

    if np.any(alpha < 255):
        visible_mask = alpha >= max(0, min(255, alpha_threshold))
    else:
        white_background = _detect_white_background(rgb, alpha, threshold=246)
        visible_mask = ~white_background

    if not transparent_background and np.any(alpha < 255):
        visible_mask = np.ones((height, width), dtype=bool)

    working_rgb, visible_mask, (offset_x, offset_y) = _crop_to_visible(rgb, visible_mask)
    width, height = working_rgb.shape[1], working_rgb.shape[0]

    visible_pixels = working_rgb[visible_mask]

    if visible_pixels.size == 0:
        svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + build_svg(
            width,
            height,
            [],
            background=None if transparent_background else "#ffffff",
            layered=False,
        )
        return {
            "svg": svg,
            "width": width,
            "height": height,
            "colors": 0,
            "warnings": ["The uploaded PNG is fully transparent."],
        }

    if transparent_background:
        filtered_pixels = np.array(
            Image.fromarray(
                visible_pixels.reshape((-1, 1, 3)).astype(np.uint8), mode="RGB"
            ).filter(ImageFilter.MedianFilter(size=5))
        ).reshape(-1, 3)
        label_values, centers = _palette_quantize_pixels(filtered_pixels, target_colors)
        full_labels = np.full((height, width), 255, dtype=np.uint8)
        full_labels[visible_mask] = label_values
        full_labels, centers = _merge_similar_colors(full_labels, centers, visible_mask)
        full_labels = _normalize_regions(full_labels, working_rgb, visible_mask)
        full_labels = _smooth_labels(full_labels, visible_mask=visible_mask)
        label_values = full_labels[visible_mask]
        counts = np.bincount(label_values, minlength=len(centers))
        labels = full_labels
    else:
        labels, centers = _palette_quantize_image(
            Image.fromarray(working_rgb.astype(np.uint8), mode="RGB"), target_colors
        )
        labels, centers = _merge_similar_colors(labels, centers, visible_mask)
        labels = _normalize_regions(labels, working_rgb, visible_mask)
        labels = _smooth_labels(labels)
        label_values = labels[visible_mask]
        counts = np.bincount(label_values.reshape(-1), minlength=len(centers))

    order = np.argsort(-counts)
    cleanup_min_area = max(32, (width * height) // 2500)

    layers = []
    for rank, idx in enumerate(order):
        color = centers[idx]
        color_hex = f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"
        if transparent_background:
            mask = np.zeros((height, width), dtype=np.uint8)
            mask[visible_mask] = (label_values == idx).astype(np.uint8)
        else:
            mask = (labels == idx).astype(np.uint8)
        mask = _clean_mask(mask, cleanup_min_area)
        path_d = build_layer_path(mask, simplify_eps=1.6, min_area=24)
        if not path_d:
            continue
        layers.append(
            {
                "id": f"color-{rank}",
                "label": f"Layer {rank + 1}: {color_hex}",
                "color": color_hex,
                "path_d": path_d,
            }
        )

    if transparent_background:
        warnings.append("Transparent pixels were preserved as SVG transparency.")
        warnings.append("Border-connected white was converted to transparency and cropped to the object bounds.")
    warnings.append("Color regions were smoothed to reduce JPEG and tracing artifacts.")
    warnings.append(f"Normalized to {len(layers)} solid color shape(s).")

    svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + build_svg(
        width,
        height,
        layers,
        background=None if transparent_background else "#ffffff",
        layered=False,
    )
    return {
        "svg": svg,
        "width": width,
        "height": height,
        "colors": len(layers),
        "warnings": warnings,
        "offsetX": offset_x,
        "offsetY": offset_y,
    }
