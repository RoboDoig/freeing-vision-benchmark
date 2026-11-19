# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib"]
# ///
"""Generate a printable tracking marker: a square tag with three symbols (centre, left, right) for SLEAP tracking.

The marker is a square of side ``--size`` with a thin outline for cutting. Three filled symbols are placed on
its horizontal centre line: one exactly at the centre, and one offset to the left and one to the right by
``--offset``. Several copies can be tiled on one page (``--copies``) to print spares.

Use a **different shape** for the left and right symbols (the default is triangle / square). If they are identical,
the marker looks the same when rotated by 180 degrees, so a pose model cannot tell left from right, and the
heading is ambiguous.

Alongside the printable file (PDF by default, or SVG/PNG by extension) a JSON sidecar is written with the
nominal symbol positions in the marker frame:

* origin at the marker centre (the centre symbol),
* +x towards the right symbol, +y towards the top edge of the printed marker, +z out of the paper,
* units in metres.

The symbol names in the JSON (``center``, ``left``, ``right``) are meant to be used as SLEAP skeleton node names.
"Left" and "right" are as seen when looking down at the printed marker. A camera looking down at it sees the same
arrangement (not mirrored).

Always print at 100% / "actual size" and check the printed scale bar with a ruler before using the marker.

Examples:
    uv run scripts/generate_tracking_marker.py
    uv run scripts/generate_tracking_marker.py --size 30 --offset 9 --symbol-size 5 --copies 12
    uv run scripts/generate_tracking_marker.py --shapes circle circle circle   # symmetric (not recommended)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

MM_PER_INCH = 25.4

PAPER_SIZES_MM = {
    "a4": (210.0, 297.0),
    "a3": (297.0, 420.0),
    "letter": (215.9, 279.4),
}

SHAPES = ("circle", "square", "triangle", "diamond", "cross", "ring")
SYMBOL_NAMES = ("center", "left", "right")


def add_symbol(ax, shape: str, cx: float, cy: float, size: float, color: str) -> None:
    """Draw a filled symbol whose geometric centre / centroid is at (cx, cy), in page mm (y down).

    ``size`` is the symbol's overall width (diameter for circles), in mm.
    """
    r = size / 2
    kw = dict(facecolor=color, edgecolor="none", zorder=3)
    if shape == "circle":
        ax.add_patch(Circle((cx, cy), r, **kw))
    elif shape == "ring":
        ax.add_patch(Circle((cx, cy), r, **kw))
        ax.add_patch(Circle((cx, cy), r * 0.5, facecolor="white", edgecolor="none", zorder=4))
    elif shape == "square":
        ax.add_patch(Rectangle((cx - r, cy - r), size, size, **kw))
    elif shape == "diamond":
        ax.add_patch(Polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], closed=True, **kw))
    elif shape == "triangle":
        # Equilateral triangle of width `size`, pointing to the top of the marker (page -y), placed so that its
        # centroid (which is what a blob/keypoint detector will find) sits exactly at (cx, cy).
        h = size * math.sqrt(3) / 2
        ax.add_patch(Polygon([(cx, cy - 2 * h / 3), (cx + r, cy + h / 3), (cx - r, cy + h / 3)], closed=True, **kw))
    elif shape == "cross":
        w = size / 3
        ax.add_patch(Rectangle((cx - r, cy - w / 2), size, w, **kw))
        ax.add_patch(Rectangle((cx - w / 2, cy - r), w, size, **kw))
    else:
        raise ValueError(f"Unknown shape: {shape}")


def symbol_extent(shape: str, size: float) -> float:
    """Half-extent of the symbol along x and y from its centre point (for fit checks)."""
    if shape == "triangle":
        return size * math.sqrt(3) / 3  # centroid to apex
    if shape == "diamond":
        return size / 2
    return size / 2


def draw_marker(ax, x0: float, y0: float, args: argparse.Namespace) -> None:
    """Draw one marker with its top-left corner at (x0, y0) in page mm."""
    s = args.size
    lw_pt = args.outline_width / MM_PER_INCH * 72
    ax.add_patch(Rectangle((x0, y0), s, s, facecolor=args.background, edgecolor="none", zorder=1))
    if args.outline_width > 0:
        # Outline drawn just outside the square so the cut edge keeps the full marker size.
        half = args.outline_width / 2
        ax.add_patch(Rectangle((x0 - half, y0 - half), s + 2 * half, s + 2 * half, facecolor="none",
                               edgecolor=args.outline_color, linewidth=lw_pt, zorder=2))

    cx, cy = x0 + s / 2, y0 + s / 2
    positions = {"center": (cx, cy), "left": (cx - args.offset, cy), "right": (cx + args.offset, cy)}
    for name, shape in zip(SYMBOL_NAMES, args.shapes, strict=True):
        px, py = positions[name]
        add_symbol(ax, shape, px, py, args.symbol_size, args.symbol_color)


def check_fit(args: argparse.Namespace) -> None:
    s, off = args.size, args.offset
    for name, shape in zip(SYMBOL_NAMES, args.shapes, strict=True):
        extent = symbol_extent(shape, args.symbol_size)
        dx = (off if name != "center" else 0) + extent
        if dx + args.edge_clearance > s / 2 or extent + args.edge_clearance > s / 2:
            raise SystemExit(
                f"The {name} symbol does not fit inside the {s:g} mm marker with {args.edge_clearance:g} mm clearance: "
                "reduce --offset / --symbol-size or increase --size."
            )
    gap = off - symbol_extent(args.shapes[0], args.symbol_size) - max(
        symbol_extent(sh, args.symbol_size) for sh in args.shapes[1:]
    )
    if gap < 1.0:
        raise SystemExit(f"Symbols are too close together ({gap:.1f} mm gap): increase --offset or reduce --symbol-size.")


def layout_copies(args: argparse.Namespace, paper_w: float, paper_h: float) -> list[tuple[float, float]]:
    """Top-left corners of each marker copy, centred on the page."""
    pitch = args.size + args.spacing
    usable_w = paper_w - 2 * args.margin
    usable_h = paper_h - 2 * args.margin - (12 if not args.no_annotations else 0)  # room for the caption
    n_cols = max(1, int((usable_w + args.spacing) // pitch))
    n_rows = max(1, int((usable_h + args.spacing) // pitch))
    if args.size > usable_w or args.size > usable_h:
        raise SystemExit("The marker does not fit on the page: reduce --size or --margin.")
    n = min(args.copies, n_cols * n_rows)
    if n < args.copies:
        print(f"Warning: only {n} copies fit on the page (requested {args.copies}).")
    n_cols = min(n_cols, n)
    n_rows = math.ceil(n / n_cols)
    block_w = n_cols * args.size + (n_cols - 1) * args.spacing
    block_h = n_rows * args.size + (n_rows - 1) * args.spacing
    left = (paper_w - block_w) / 2
    top = args.margin + (usable_h - block_h) / 2
    return [(left + (i % n_cols) * pitch, top + (i // n_cols) * pitch) for i in range(n)]


def draw_caption(ax, args: argparse.Namespace, paper_w: float, paper_h: float) -> None:
    bar_len = args.scale_bar
    bar_y = paper_h - args.margin - 2
    bar_x0 = (paper_w - bar_len) / 2
    ax.add_patch(Rectangle((bar_x0, bar_y - 0.5), bar_len, 1.0, facecolor="black", edgecolor="none"))
    for x in (bar_x0, bar_x0 + bar_len):
        ax.plot([x, x], [bar_y - 2, bar_y + 2], color="black", linewidth=0.5)
    shapes = ", ".join(f"{n}={sh}" for n, sh in zip(SYMBOL_NAMES, args.shapes, strict=True))
    caption = (
        f"scale bar {bar_len:g} mm - print at 100% / actual size\n"
        f"marker {args.size:g} mm, symbols {args.symbol_size:g} mm, left/right offset {args.offset:g} mm ({shapes})"
    )
    ax.text(paper_w / 2, bar_y - 2.5, caption, ha="center", va="bottom", fontsize=5, linespacing=1.2)


def build_metadata(args: argparse.Namespace, n_copies: int) -> dict:
    to_m = 1 / 1000.0
    positions = {"center": (0.0, 0.0), "left": (-args.offset, 0.0), "right": (args.offset, 0.0)}
    return {
        "description": "Nominal tracking-marker geometry. Marker frame: origin at the centre symbol, +x towards the "
        "right symbol, +y towards the top edge of the printed marker, +z out of the paper. Units: metres. "
        "Symbol positions are shape centroids.",
        "marker_size": args.size * to_m,
        "symbol_size": args.symbol_size * to_m,
        "offset": args.offset * to_m,
        "copies": n_copies,
        "symbols": [
            {"name": name, "shape": shape, "position": [positions[name][0] * to_m, positions[name][1] * to_m, 0.0]}
            for name, shape in zip(SYMBOL_NAMES, args.shapes, strict=True)
        ],
        "skeleton": {"nodes": list(SYMBOL_NAMES), "edges": [["left", "center"], ["center", "right"]]},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--output", type=Path, default=Path("markers/tracking_marker.pdf"),
                   help="Output file; format from extension (.pdf, .svg, .png). JSON sidecar uses the same stem.")
    p.add_argument("--size", type=float, default=40.0, help="Marker side length (mm).")
    p.add_argument("--offset", type=float, default=12.0, help="Distance (mm) from the centre symbol to the left and right symbols.")
    p.add_argument("--symbol-size", type=float, default=3.0, help="Symbol width (mm); diameter for circles.")
    p.add_argument("--shapes", nargs=3, choices=SHAPES, default=["circle", "cross", "diamond"],
                   metavar=("CENTER", "LEFT", "RIGHT"), help=f"Symbol shapes for centre, left, right. Choices: {', '.join(SHAPES)}.")
    p.add_argument("--symbol-color", default="black", help="Symbol colour (any matplotlib colour).")
    p.add_argument("--background", default="white", help="Marker background colour (any matplotlib colour).")
    p.add_argument("--outline-width", type=float, default=0.3, help="Width (mm) of the cutting outline drawn outside the square (0 disables).")
    p.add_argument("--outline-color", default="black", help="Outline colour (any matplotlib colour).")
    p.add_argument("--edge-clearance", type=float, default=2.0, help="Minimum gap (mm) between any symbol and the marker edge.")
    p.add_argument("--copies", type=int, default=1, help="Number of marker copies to tile on the page.")
    p.add_argument("--spacing", type=float, default=10.0, help="Gap (mm) between copies.")
    p.add_argument("--paper", choices=sorted(PAPER_SIZES_MM), default="a4", help="Paper size.")
    p.add_argument("--paper-size", type=float, nargs=2, metavar=("W_MM", "H_MM"), help="Custom paper size (overrides --paper).")
    p.add_argument("--landscape", action="store_true", help="Landscape orientation.")
    p.add_argument("--margin", type=float, default=10.0, help="Page margin (mm).")
    p.add_argument("--scale-bar", type=float, default=50.0, help="Length of the printed scale bar (mm).")
    p.add_argument("--no-annotations", action="store_true", help="Omit the caption and scale bar.")
    p.add_argument("--dpi", type=int, default=600, help="Resolution for raster output (.png).")
    args = p.parse_args(argv)
    if args.copies < 1:
        p.error("--copies must be at least 1.")
    if args.shapes[1] == args.shapes[2]:
        print("Warning: left and right symbols have the same shape; left/right (and heading) will be ambiguous "
              "under 180-degree rotation.")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    check_fit(args)

    paper_w, paper_h = args.paper_size if args.paper_size else PAPER_SIZES_MM[args.paper]
    if args.landscape:
        paper_w, paper_h = max(paper_w, paper_h), min(paper_w, paper_h)
    corners = layout_copies(args, paper_w, paper_h)

    fig = plt.figure(figsize=(paper_w / MM_PER_INCH, paper_h / MM_PER_INCH))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, paper_w)
    ax.set_ylim(paper_h, 0)  # page coordinates: y down
    ax.set_aspect("equal")
    ax.axis("off")
    for x0, y0 in corners:
        draw_marker(ax, x0, y0, args)
    if not args.no_annotations:
        draw_caption(ax, args, paper_w, paper_h)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=args.dpi, facecolor="white")
    plt.close(fig)

    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(build_metadata(args, len(corners)), indent=2), encoding="utf-8")
    print(f"Wrote {args.output} and {json_path} ({len(corners)} cop{'y' if len(corners) == 1 else 'ies'})")


if __name__ == "__main__":
    main()
