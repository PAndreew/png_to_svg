from pathlib import Path
import numpy as np
from PIL import Image
from .quantize import quantise
from .tracer import build_layer_path
from .svg_writer import build_svg, _inject_inkscape_layers, INKSCAPE_NS, SVG_NS


def _hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


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
