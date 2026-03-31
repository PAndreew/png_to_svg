from __future__ import annotations
import base64, io
from typing import Any
import numpy as np
from PIL import Image
from convert import build_layer_path, build_svg, quantise


def vectorize_data_uri(data_uri: str, colors: int = 10) -> dict[str, Any]:
    _, _, encoded = data_uri.partition(",")
    image_bytes = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    array = np.array(image)
    labels, centers = quantise(array, max(2, min(32, colors)))
    _, counts = np.unique(labels, return_counts=True)
    order = np.argsort(-counts)

    layers = []
    for rank, idx in enumerate(order):
        color = centers[idx]
        color_hex = f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"
        mask = (labels == idx).astype(np.uint8)
        path_d = build_layer_path(mask, simplify_eps=1.0, min_area=16)
        layers.append({
            "id": f"color-{rank}",
            "label": f"Layer {rank + 1}: {color_hex}",
            "color": color_hex,
            "path_d": path_d,
        })

    svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + build_svg(image.width, image.height, layers)
    return {"svg": svg, "width": image.width, "height": image.height}
