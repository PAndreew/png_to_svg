#!/usr/bin/env python3
"""
PNG/JPG → Layered SVG Converter
================================
Converts raster images into editable, layered SVG files by:
  1. Quantising the image into N colour clusters (k-means)
  2. Tracing each colour layer's boundary with marching squares
  3. Simplifying the paths with Ramer-Douglas-Peucker
  4. Writing an Inkscape-compatible multi-layer SVG

Usage
-----
  python convert.py input.png -o output.svg
  python convert.py input.jpg -o output.svg --colors 12 --simplify 1.5
  python convert.py input.png --backend vtracer         # needs:  pip install vtracer

Dependencies
------------
  pip install pillow numpy scikit-learn scikit-image
  (optional high-quality backend)
  pip install vtracer
"""

import argparse
import sys
import os
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def rdp_simplify(points, epsilon=1.0):
    """Ramer-Douglas-Peucker path simplification."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist_sq_line = dx * dx + dy * dy

    def point_line_dist_sq(p):
        if dist_sq_line == 0:
            return (p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2
        t = ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / dist_sq_line
        t = max(0.0, min(1.0, t))
        px = start[0] + t * dx
        py = start[1] + t * dy
        return (p[0] - px) ** 2 + (p[1] - py) ** 2

    max_dist_sq = 0.0
    max_idx = 0
    eps_sq = epsilon * epsilon
    for i in range(1, len(points) - 1):
        d = point_line_dist_sq(points[i])
        if d > max_dist_sq:
            max_dist_sq = d
            max_idx = i

    if max_dist_sq > eps_sq:
        left = rdp_simplify(points[: max_idx + 1], epsilon)
        right = rdp_simplify(points[max_idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def contour_to_path(contour, simplify_eps=1.0):
    """Convert a skimage contour (row, col) array → SVG path string."""
    pts = [(float(c[1]), float(c[0])) for c in contour]
    if simplify_eps > 0:
        pts = rdp_simplify(pts, simplify_eps)
    if len(pts) < 2:
        return ""
    parts = [f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"]
    for x, y in pts[1:]:
        parts.append(f"L {x:.2f},{y:.2f}")
    parts.append("Z")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Colour quantisation
# ---------------------------------------------------------------------------


def quantise(img_array, n_colors, max_iter=100):
    """K-means colour quantisation. Returns (label_map, color_table)."""
    from sklearn.cluster import MiniBatchKMeans

    h, w, c = img_array.shape
    pixels = img_array.reshape(-1, c).astype(np.float32)

    km = MiniBatchKMeans(
        n_clusters=n_colors,
        random_state=42,
        max_iter=max_iter,
        n_init=3,
    )
    labels = km.fit_predict(pixels)
    centers = np.clip(km.cluster_centers_, 0, 255).astype(np.uint8)
    return labels.reshape(h, w), centers


# ---------------------------------------------------------------------------
# Contour tracing
# ---------------------------------------------------------------------------


def trace_mask(mask, min_area=4):
    """
    Return a list of (contour, is_hole) pairs for a binary mask.
    Uses scikit-image marching squares.
    `is_hole` is True when the contour winds clockwise (encloses background).
    """
    from skimage import measure

    # Pad so boundary objects get a closed contour
    padded = np.pad(mask, 1, constant_values=0)
    raw_contours = measure.find_contours(padded.astype(float), 0.5)

    result = []
    for c in raw_contours:
        # shift back for the pad
        c = c - 1.0
        # Area via shoelace
        area = 0.5 * abs(
            np.dot(c[:, 0], np.roll(c[:, 1], 1)) - np.dot(c[:, 1], np.roll(c[:, 0], 1))
        )
        if area < min_area:
            continue
        # Shoelace sign: positive → CCW (filled region), negative → CW (hole)
        signed = 0.5 * (
            np.dot(c[:, 0], np.roll(c[:, 1], 1)) - np.dot(c[:, 1], np.roll(c[:, 0], 1))
        )
        result.append((c, signed < 0))

    return result


def build_layer_path(mask, simplify_eps=1.0, min_area=4):
    """
    Build a compound SVG path for one colour layer.
    Holes are automatically handled by evenodd fill-rule.
    """
    pairs = trace_mask(mask, min_area=min_area)
    parts = []
    for contour, _is_hole in pairs:
        p = contour_to_path(contour, simplify_eps)
        if p:
            parts.append(p)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# SVG writer
# ---------------------------------------------------------------------------

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)
ET.register_namespace(
    "sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
)


def build_svg(width, height, layers, background="#ffffff", embed_original=None):
    """
    layers: list of dicts  { 'id', 'label', 'color', 'path_d' }
    embed_original: (b64_data_uri, mime) or None
    """
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": f"{width}px",
            "height": f"{height}px",
            "viewBox": f"0 0 {width} {height}",
            "version": "1.1",
        },
    )

    # Background layer
    bg_group = ET.SubElement(
        root,
        "g",
        {
            "id": "layer-background",
            f"{{{INKSCAPE_NS}}}label": "Background",
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
        },
    )
    ET.SubElement(
        bg_group,
        "rect",
        {"width": str(width), "height": str(height), "fill": background},
    )

    # Optional embedded original raster (for reference)
    if embed_original:
        data_uri, mime = embed_original
        ref_group = ET.SubElement(
            root,
            "g",
            {
                "id": "layer-reference",
                f"{{{INKSCAPE_NS}}}label": "Reference (raster)",
                f"{{{INKSCAPE_NS}}}groupmode": "layer",
                "style": "display:none",  # hidden by default
            },
        )
        ET.SubElement(
            ref_group,
            "image",
            {
                "x": "0",
                "y": "0",
                "width": str(width),
                "height": str(height),
                "href": f"data:{mime};base64,{data_uri}",
                "preserveAspectRatio": "none",
            },
        )

    # Colour layers (bottom to top → sorted by pixel count desc so large fills go first)
    for i, layer in enumerate(layers):
        g = ET.SubElement(
            root,
            "g",
            {
                "id": f"layer-color-{i}",
                f"{{{INKSCAPE_NS}}}label": layer["label"],
                f"{{{INKSCAPE_NS}}}groupmode": "layer",
            },
        )
        if layer.get("path_d"):
            ET.SubElement(
                g,
                "path",
                {
                    "d": layer["path_d"],
                    "fill": layer["color"],
                    "fill-rule": "evenodd",
                    "stroke": "none",
                },
            )

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# vtracer backend (optional)
# ---------------------------------------------------------------------------


def convert_vtracer(input_path, output_path, n_colors, args):
    """Use vtracer library for high-quality vectorisation."""
    import vtracer

    print(f"  [vtracer] tracing {input_path} …")
    vtracer.convert_image_to_svg_py(
        str(input_path),
        str(output_path),
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=args.min_area,
        color_precision=args.color_precision,
        layer_difference=args.layer_difference,
        corner_threshold=args.corner_threshold,
        length_threshold=args.length_threshold,
        max_iterations=10,
        splice_threshold=args.splice_threshold,
        path_precision=3,
    )
    print(f"  [vtracer] written → {output_path}")

    # Post-process: add Inkscape layer attributes to vtracer output
    _inject_inkscape_layers(output_path)


def _inject_inkscape_layers(svg_path):
    """Add inkscape:groupmode='layer' to all top-level <g> elements."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    ns = {"svg": SVG_NS}

    top_groups = [
        child for child in root if child.tag == f"{{{SVG_NS}}}g" or child.tag == "g"
    ]
    for i, g in enumerate(top_groups):
        g.set(f"{{{INKSCAPE_NS}}}groupmode", "layer")
        if not g.get(f"{{{INKSCAPE_NS}}}label"):
            g.set(f"{{{INKSCAPE_NS}}}label", f"Layer {i + 1}")

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.indent(root, space="  ")
    tree.write(svg_path, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# Custom tracer backend
# ---------------------------------------------------------------------------


def convert_custom(input_path, output_path, n_colors, args):
    """Pure-Python colour-quantise + marching-squares backend."""
    print(f"  [custom] loading image …")
    img = Image.open(input_path)

    # Optionally scale large images for speed
    max_dim = args.max_size
    if max(img.width, img.height) > max_dim:
        scale = max_dim / max(img.width, img.height)
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        print(f"  [custom] resizing to {new_w}×{new_h} for processing …")
        img = img.resize((new_w, new_h), Image.LANCZOS)
    else:
        new_w, new_h = img.width, img.height

    has_alpha = img.mode in ("RGBA", "LA", "P")
    if has_alpha:
        # Composite onto white to eliminate transparency
        bg = Image.new("RGB", img.size, (255, 255, 255))
        img_rgb = img.convert("RGBA")
        bg.paste(img_rgb, mask=img_rgb.split()[3])
        img = bg
    else:
        img = img.convert("RGB")

    arr = np.array(img)

    print(f"  [custom] quantising to {n_colors} colours …")
    labels, centers = quantise(arr, n_colors)

    # Sort layers: larger areas (more pixels) at the bottom
    unique, counts = np.unique(labels, return_counts=True)
    order = np.argsort(-counts)  # descending pixel count → paint order

    layers = []
    for rank, idx in enumerate(order):
        color = centers[idx]
        hex_color = _hex(*color)
        mask = (labels == idx).astype(np.uint8)
        pct = counts[order[rank]] / labels.size * 100

        print(
            f"  [custom] layer {rank + 1}/{n_colors}: "
            f"{hex_color}  ({pct:.1f}% of pixels) — tracing …"
        )
        path_d = build_layer_path(
            mask,
            simplify_eps=args.simplify,
            min_area=args.min_area,
        )
        layers.append(
            {
                "id": f"color-{rank}",
                "label": f"Layer {rank + 1}: {hex_color}",
                "color": hex_color,
                "path_d": path_d,
            }
        )

    # Embed original raster as hidden reference?
    embed = None
    if args.embed_reference:
        import base64, io

        buf = io.BytesIO()
        orig = Image.open(input_path)
        fmt = "PNG" if input_path.suffix.lower() == ".png" else "JPEG"
        mime = "image/png" if fmt == "PNG" else "image/jpeg"
        orig.save(buf, format=fmt)
        embed = (base64.b64encode(buf.getvalue()).decode(), mime)

    print(f"  [custom] writing SVG …")
    svg_str = build_svg(
        new_w,
        new_h,
        layers,
        background=args.background,
        embed_original=embed,
    )

    Path(output_path).write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + svg_str,
        encoding="utf-8",
    )
    print(f"  [custom] written → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Convert PNG/JPG to a layered, editable SVG file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ---- I/O ---------------------------------------------------------------
    parser.add_argument("input", help="Input image (PNG or JPG)")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output SVG path (default: same name as input with .svg)",
    )

    # ---- Common options ----------------------------------------------------
    parser.add_argument(
        "-c",
        "--colors",
        type=int,
        default=8,
        metavar="N",
        help="Number of colour layers (2–32)",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "vtracer", "custom"],
        default="auto",
        help="Vectorisation backend. "
        "'auto' tries vtracer first, falls back to custom.",
    )
    parser.add_argument(
        "--background",
        default="#ffffff",
        help="Background fill colour of the bottom layer",
    )
    parser.add_argument(
        "--embed-reference",
        action="store_true",
        help="Embed the original raster as a hidden reference layer "
        "(custom backend only)",
    )

    # ---- Custom backend options --------------------------------------------
    grp = parser.add_argument_group("Custom-backend options")
    grp.add_argument(
        "--simplify",
        type=float,
        default=1.0,
        metavar="EPS",
        help="Ramer-Douglas-Peucker epsilon for path simplification "
        "(0 = off, higher = simpler paths)",
    )
    grp.add_argument(
        "--min-area",
        type=int,
        default=16,
        metavar="PX",
        help="Minimum contour area in pixels (removes noise specks)",
    )
    grp.add_argument(
        "--max-size",
        type=int,
        default=2048,
        metavar="PX",
        help="Downscale the longest edge to this value before tracing "
        "(speeds processing; the SVG viewBox matches the scaled size)",
    )

    # ---- vtracer options (forwarded verbatim) ------------------------------
    grp2 = parser.add_argument_group("vtracer options (ignored for custom backend)")
    grp2.add_argument("--color-precision", type=int, default=6)
    grp2.add_argument("--layer-difference", type=int, default=16)
    grp2.add_argument("--corner-threshold", type=int, default=60)
    grp2.add_argument("--length-threshold", type=float, default=4.0)
    grp2.add_argument("--splice-threshold", type=int, default=45)

    args = parser.parse_args()

    # ---- Validate input ----------------------------------------------------
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    if input_path.suffix.lower() not in (
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".tiff",
        ".tif",
        ".webp",
    ):
        print(f"Warning: {input_path.suffix} may not be supported.", file=sys.stderr)

    n_colors = max(2, min(64, args.colors))

    output_path = Path(args.output) if args.output else input_path.with_suffix(".svg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nInput  : {input_path}")
    print(f"Output : {output_path}")
    print(f"Colors : {n_colors}")
    print(f"Backend: {args.backend}\n")

    # ---- Choose backend ----------------------------------------------------
    backend = args.backend

    if backend in ("auto", "vtracer"):
        try:
            import vtracer  # noqa: F401

            backend = "vtracer"
        except ImportError:
            if backend == "vtracer":
                print(
                    "Error: vtracer is not installed.\n"
                    "  Install it with:  pip install vtracer\n"
                    "  Or use --backend custom",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("  [auto] vtracer not found, using custom backend.\n")
            backend = "custom"

    if backend == "vtracer":
        convert_vtracer(input_path, output_path, n_colors, args)
    else:
        convert_custom(input_path, output_path, n_colors, args)

    print("\nDone.")


if __name__ == "__main__":
    main()
