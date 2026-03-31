import numpy as np


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
