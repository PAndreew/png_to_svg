# PNG / JPG → Layered SVG Converter

Converts raster images into fully editable, **multi-layer SVG** files you can open directly in Inkscape, Affinity Designer, Adobe Illustrator, or any other vector editor.

## How it works

| Step | What happens |
|---|---|
| 1 | Load the image (PNG, JPG, BMP, WebP, …) |
| 2 | Reduce to *N* colours using k-means clustering |
| 3 | For each colour, trace the boundary with marching squares |
| 4 | Simplify paths with Ramer-Douglas-Peucker |
| 5 | Write an Inkscape-compatible SVG with one `<g>` layer per colour |

Alternatively the [vtracer](https://github.com/visioncortex/vtracer) backend (Rust, very fast) can be used for spline-quality paths.

## Installation

```bash
pip install -r requirements.txt

# Optional: faster/smoother vtracer backend
pip install vtracer
```

## Usage

```
python convert.py input.png                      # → input.svg, 8 colour layers
python convert.py photo.jpg -o out.svg           # custom output path
python convert.py logo.png -c 12                 # 12 colour layers
python convert.py art.png --simplify 2.0         # more aggressive path simplification
python convert.py img.png --backend vtracer      # use vtracer backend
python convert.py img.png --embed-reference      # include hidden raster reference layer
```

### All options

```
positional arguments:
  input                     Input image (PNG or JPG)

options:
  -o / --output PATH        Output SVG path  (default: same filename, .svg extension)
  -c / --colors N           Number of colour layers  (default: 8)
  --backend {auto,vtracer,custom}
                            Vectorisation backend  (default: auto)
  --background COLOR        Background fill colour  (default: #ffffff)
  --embed-reference         Embed original raster as a hidden reference layer

Custom-backend options:
  --simplify EPS            RDP epsilon — 0 = off, higher = fewer nodes  (default: 1.0)
  --min-area PX             Minimum contour area; removes noise specks  (default: 16)
  --max-size PX             Downscale longest edge before tracing  (default: 2048)

vtracer options (ignored for custom backend):
  --color-precision INT     (default: 6)
  --layer-difference INT    (default: 16)
  --corner-threshold INT    (default: 60)
  --length-threshold FLOAT  (default: 4.0)
  --splice-threshold INT    (default: 45)
```

## Output SVG structure

```xml
<svg xmlns:inkscape="…" width="…" height="…">
  <g inkscape:label="Background"           inkscape:groupmode="layer"> … </g>
  <g inkscape:label="Reference (raster)"   inkscape:groupmode="layer" style="display:none"> … </g>
  <g inkscape:label="Layer 1: #3a4f2c"     inkscape:groupmode="layer"> <path … /> </g>
  <g inkscape:label="Layer 2: #c8b87a"     inkscape:groupmode="layer"> <path … /> </g>
  …
</svg>
```

Each layer is a separate `<g>` group in paint order (largest area first).  
Shapes with holes use `fill-rule="evenodd"` so inner contours are automatically cut out.

## Tips

- **More colours → more detail**, but also larger SVG and longer processing time.  
  Good starting points: logos 4–8, illustrations 8–16, photos 16–24.
- **`--simplify`**: lower values preserve fidelity, higher values give smoother, simpler shapes.
- **`--max-size`**: reduce for faster results on large photos (the SVG viewport matches the processing resolution).
- Use **`--backend vtracer`** when you want smooth spline curves instead of polylines.

## Pictogram Studio web app

This repository now also contains the Pictogram Studio web app:

- Python/FastAPI app serving the editor and renderer
- symbolic scene planner in Python
- Dockerized TypeScript planner sidecar for asset-aware scene planning

### Planner architecture

The planning flow is now:

1. user prompt enters the FastAPI app
2. Python builds asset-registry context from the catalog
3. Python calls the TypeScript planner sidecar
4. the sidecar uses tool-style asset search against the catalog payload
5. the sidecar returns a symbolic `layoutPlan`
6. Python converts lane/slot/anchor placement into a first-pass scene
7. the first pass is rendered to SVG and rasterized to PNG
8. the PNG plus JSON are sent to the multimodal review pass
9. if needed, the review pass rewrites the symbolic JSON
10. Python renders the final reviewed scene

### Internal review loop

The app can run an internal second-pass review before returning a scene to the user.

User-visible generation stages:

- `fetching assets`
- `generating first pass`
- `reviewing`
- `final render`

The review pass uses:

- first-pass symbolic scene JSON
- first-pass rendered PNG
- the original prompt

If the reviewer finds issues, it can rewrite the symbolic layout plan and the corrected second pass is what the user receives.

The sidecar is intended for prompts like:

- `truck in lane 2 slot 3 on a highway`
- typo recovery such as `turck` → nearest matching asset via catalog search

### Run with Docker

1. Copy [.env.example](.env.example) to `.env`
2. Set `OPENROUTER_API_KEY`
3. Start the stack:

```bash
docker compose up --build
```

Services:

- app: http://localhost:8001
- planner sidecar: http://localhost:8787

### Docker services

- [Dockerfile](Dockerfile): Python/FastAPI app
- [planner-sidecar/Dockerfile](planner-sidecar/Dockerfile): TypeScript planning sidecar
- [docker-compose.yml](docker-compose.yml): full stack wiring
