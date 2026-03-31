import xml.etree.ElementTree as ET
from typing import Any

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)
ET.register_namespace(
    "sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
)


def build_svg(
    width: Any,
    height: Any,
    layers: list[dict[str, Any]],
    background: str | None = "#ffffff",
    embed_original=None,
    layered: bool = True,
):
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

    if background not in (None, "", "none", "transparent"):
        if layered:
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
        else:
            ET.SubElement(
                root,
                "rect",
                {"width": str(width), "height": str(height), "fill": background},
            )

    # Optional embedded original raster (for reference)
    if embed_original:
        data_uri, mime = embed_original
        if layered:
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
        else:
            ET.SubElement(
                root,
                "image",
                {
                    "x": "0",
                    "y": "0",
                    "width": str(width),
                    "height": str(height),
                    "href": f"data:{mime};base64,{data_uri}",
                    "preserveAspectRatio": "none",
                    "style": "display:none",
                },
            )

    # Colour layers (bottom to top → sorted by pixel count desc so large fills go first)
    for i, layer in enumerate(layers):
        if not layer.get("path_d"):
            continue
        if layered:
            g = ET.SubElement(
                root,
                "g",
                {
                    "id": f"layer-color-{i}",
                    f"{{{INKSCAPE_NS}}}label": layer["label"],
                    f"{{{INKSCAPE_NS}}}groupmode": "layer",
                },
            )
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
        else:
            ET.SubElement(
                root,
                "path",
                {
                    "id": f"color-path-{i}",
                    "d": layer["path_d"],
                    "fill": layer["color"],
                    "fill-rule": "evenodd",
                    "stroke": "none",
                },
            )

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _inject_inkscape_layers(svg_path):
    """Add inkscape:groupmode='layer' to all top-level <g> elements."""
    tree = ET.parse(svg_path)
    root = tree.getroot()

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
