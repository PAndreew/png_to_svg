import argparse
import sys
from pathlib import Path
from .backends import convert_vtracer, convert_custom


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
