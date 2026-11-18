# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python", "matplotlib"]
# ///
"""Generate a printable arena calibration sheet: four ArUco markers at the corners plus a square grid.

The sheet is a small-scale stand-in for the arena described in ``docs/plane-tracking-plan.md``. Alongside the
printable file (PDF by default, or SVG/PNG by extension) a JSON sidecar is written that holds the nominal
coordinates of every marker corner and grid intersection in the arena (plane) frame:

* origin at the centre of marker 0 (bottom-left of the page),
* +x towards marker 1 (bottom-right), +y towards marker 3 (top-left), +z out of the paper (towards the camera),
* units in metres.

Marker order around the sheet (counter-clockwise when viewed from above):

    3 ---- 2
    |      |
    0 ---- 1

Marker corners in the JSON are listed in OpenCV detection order (top-left, top-right, bottom-right,
bottom-left of the upright marker), so they can be passed directly to ``cv2.solvePnP`` together with the
output of ``cv2.aruco.ArucoDetector.detectMarkers``.

By default, the spacing between marker centres is snapped to a whole number of grid cells so that marker centres
lie exactly on grid intersections.

Always print at 100% / "actual size" and check the printed scale bar with a ruler before using the sheet.

Examples:
    uv run scripts/generate_calibration_sheet.py
    uv run scripts/generate_calibration_sheet.py --marker-size 30 --grid-size 5 --output local/sheet_30mm.pdf
    uv run scripts/generate_calibration_sheet.py --paper a3 --landscape --marker-ids 20 21 22 23
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

MM_PER_INCH = 25.4

PAPER_SIZES_MM = {
    "a4": (210.0, 297.0),
    "a3": (297.0, 420.0),
    "letter": (215.9, 279.4),
}

# Bonsai.Aruco (and the marker files in ./markers) use the original ArUco dictionary.
DEFAULT_DICTIONARY = "DICT_ARUCO_ORIGINAL"


@dataclass
class SheetLayout:
    """Geometry of the sheet, in page millimetres (origin top-left, y down)."""

    paper_w: float
    paper_h: float
    marker_size: float
    grid_size: float
    quiet_zone: float
    # Marker centres in page coordinates, ordered 0 (BL), 1 (BR), 2 (TR), 3 (TL).
    centres: list[tuple[float, float]]
    n_cells_x: int
    n_cells_y: int

    @property
    def grid_x0(self) -> float:
        return self.centres[0][0]

    @property
    def grid_y_bottom(self) -> float:
        return self.centres[0][1]

    @property
    def span_x(self) -> float:
        return self.centres[1][0] - self.centres[0][0]

    @property
    def span_y(self) -> float:
        return self.centres[0][1] - self.centres[3][1]

    def page_to_plane(self, x: float, y: float) -> tuple[float, float]:
        """Convert page mm (origin top-left, y down) to plane metres (origin marker 0, y up)."""
        return (x - self.grid_x0) / 1000.0, (self.grid_y_bottom - y) / 1000.0


def compute_layout(args: argparse.Namespace) -> SheetLayout:
    paper_w, paper_h = args.paper_size if args.paper_size else PAPER_SIZES_MM[args.paper]
    if args.landscape:
        paper_w, paper_h = max(paper_w, paper_h), min(paper_w, paper_h)

    s, m = args.marker_size, args.margin
    # Largest centre-to-centre spacing that keeps each marker fully inside the printable margin.
    max_span_x = paper_w - 2 * m - s
    max_span_y = paper_h - 2 * m - s
    if max_span_x <= 0 or max_span_y <= 0:
        raise SystemExit("Markers do not fit on the page: reduce --marker-size or --margin.")

    if args.no_snap:
        span_x, span_y = max_span_x, max_span_y
        n_x = math.floor(span_x / args.grid_size)
        n_y = math.floor(span_y / args.grid_size)
    else:
        n_x = math.floor(max_span_x / args.grid_size)
        n_y = math.floor(max_span_y / args.grid_size)
        span_x, span_y = n_x * args.grid_size, n_y * args.grid_size
    if n_x < 1 or n_y < 1:
        raise SystemExit("Grid size is larger than the marker spacing: reduce --grid-size.")

    if span_x < s + 2 * args.quiet_zone or span_y < s + 2 * args.quiet_zone:
        raise SystemExit("Markers would overlap: reduce --marker-size / --quiet-zone or use larger paper.")

    # Centre the marker rectangle on the page.
    left = (paper_w - span_x) / 2
    right = left + span_x
    top = (paper_h - span_y) / 2
    bottom = top + span_y
    centres = [(left, bottom), (right, bottom), (right, top), (left, top)]

    return SheetLayout(
        paper_w=paper_w,
        paper_h=paper_h,
        marker_size=s,
        grid_size=args.grid_size,
        quiet_zone=args.quiet_zone,
        centres=centres,
        n_cells_x=n_x,
        n_cells_y=n_y,
    )


def marker_bits(dictionary: cv2.aruco.Dictionary, marker_id: int) -> np.ndarray:
    """Return the marker as a boolean grid (True = white), including the black border cells."""
    n_cells = dictionary.markerSize + 2
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, n_cells, borderBits=1)
    return img > 127


def draw_marker(ax, bits: np.ndarray, cx: float, cy: float, size: float) -> None:
    """Draw a marker centred at (cx, cy) in page mm. Row 0 of ``bits`` is the top of the marker."""
    n = bits.shape[0]
    cell = size / n
    x0, y0 = cx - size / 2, cy - size / 2
    ax.add_patch(Rectangle((x0, y0), size, size, facecolor="black", edgecolor="none", antialiased=False))

    # Union of white cells as one compound path, so adjacent cells render without hairline seams.
    verts, codes = [], []
    for r in range(n):
        c = 0
        while c < n:
            if not bits[r, c]:
                c += 1
                continue
            start = c
            while c < n and bits[r, c]:
                c += 1
            xa, xb = x0 + start * cell, x0 + c * cell
            ya, yb = y0 + r * cell, y0 + (r + 1) * cell
            verts += [(xa, ya), (xb, ya), (xb, yb), (xa, yb), (xa, ya)]
            codes += [MplPath.MOVETO, MplPath.LINETO, MplPath.LINETO, MplPath.LINETO, MplPath.CLOSEPOLY]
    if verts:
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor="white", edgecolor="none", antialiased=False))


def draw_grid(ax, layout: SheetLayout, line_width_mm: float, major_every: int) -> None:
    lw_pt = line_width_mm / MM_PER_INCH * 72
    x_left, y_bottom = layout.grid_x0, layout.grid_y_bottom
    x_right = x_left + layout.n_cells_x * layout.grid_size
    y_top = y_bottom - layout.n_cells_y * layout.grid_size

    for i in range(layout.n_cells_x + 1):
        x = x_left + i * layout.grid_size
        major = major_every > 0 and i % major_every == 0
        ax.plot([x, x], [y_bottom, y_top], color="black", linewidth=lw_pt * (2 if major else 1), solid_capstyle="butt")
    for j in range(layout.n_cells_y + 1):
        y = y_bottom - j * layout.grid_size
        major = major_every > 0 and j % major_every == 0
        ax.plot([x_left, x_right], [y, y], color="black", linewidth=lw_pt * (2 if major else 1), solid_capstyle="butt")

    # Clear a quiet zone around each marker so the grid does not touch the marker border.
    half = layout.marker_size / 2 + layout.quiet_zone
    for cx, cy in layout.centres:
        ax.add_patch(
            Rectangle((cx - half, cy - half), 2 * half, 2 * half, facecolor="white", edgecolor="none", zorder=2)
        )


def draw_annotations(ax, layout: SheetLayout, args: argparse.Namespace, marker_ids: list[int]) -> None:
    font_pt = 6
    # Marker id labels, just inside each marker's quiet zone towards the sheet centre.
    offset = layout.marker_size / 2 + layout.quiet_zone + 1.0
    for idx, ((cx, cy), mid) in enumerate(zip(layout.centres, marker_ids, strict=True)):
        dy = -offset if idx in (0, 1) else offset
        va = "bottom" if idx in (0, 1) else "top"
        ax.text(cx, cy + dy, f"#{idx} (id {mid})", ha="center", va=va, fontsize=font_pt, zorder=3,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.5))

    # Scale bar plus parameter summary, in the strip below the grid between the two bottom markers.
    strip_left = layout.centres[0][0] + layout.marker_size / 2 + layout.quiet_zone + 1
    strip_right = layout.centres[1][0] - layout.marker_size / 2 - layout.quiet_zone - 1
    strip_top = layout.grid_y_bottom + 1
    strip_bottom = layout.grid_y_bottom + layout.marker_size / 2
    bar_len = args.scale_bar
    if strip_right - strip_left < bar_len or strip_bottom - strip_top < 8:
        print(f"Warning: no room for a {bar_len:g} mm scale bar between the bottom markers; skipping it "
              "(try a smaller --scale-bar).")
        return
    cx = (strip_left + strip_right) / 2
    bar_y = strip_bottom - 2.5
    bar_x0 = cx - bar_len / 2
    ax.add_patch(Rectangle((bar_x0, bar_y - 0.5), bar_len, 1.0, facecolor="black", edgecolor="none", zorder=3))
    for x in (bar_x0, bar_x0 + bar_len):
        ax.plot([x, x], [bar_y - 2, bar_y + 2], color="black", linewidth=0.5, zorder=3)
    summary = (
        f"scale bar {bar_len:g} mm - print at 100% / actual size\n"
        f"{args.dictionary}, marker {layout.marker_size:g} mm, grid {layout.grid_size:g} mm\n"
        f"marker centre spacing {layout.span_x:g} x {layout.span_y:g} mm"
    )
    ax.text(cx, bar_y - 2.5, summary, ha="center", va="bottom", fontsize=font_pt - 1, linespacing=1.2, zorder=3)


def build_metadata(layout: SheetLayout, args: argparse.Namespace, marker_ids: list[int]) -> dict:
    half = layout.marker_size / 2
    markers = []
    for idx, ((cx, cy), mid) in enumerate(zip(layout.centres, marker_ids, strict=True)):
        # OpenCV corner order for an upright marker: TL, TR, BR, BL (page y is down, so top = cy - half).
        corners_page = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
        markers.append(
            {
                "index": idx,
                "id": mid,
                "center": [round(v, 9) for v in layout.page_to_plane(cx, cy)] + [0.0],
                "corners": [[round(v, 9) for v in layout.page_to_plane(x, y)] + [0.0] for x, y in corners_page],
            }
        )

    return {
        "description": "Nominal arena-calibration sheet geometry. Plane frame: origin at marker 0 centre, "
        "+x towards marker 1, +y towards marker 3, +z out of the paper. Units: metres. Marker corners in "
        "OpenCV order (TL, TR, BR, BL).",
        "dictionary": args.dictionary,
        "paper_size_mm": [layout.paper_w, layout.paper_h],
        "marker_size": layout.marker_size / 1000.0,
        "grid_size": layout.grid_size / 1000.0,
        "grid_cells": [layout.n_cells_x, layout.n_cells_y],
        "grid_origin": [0.0, 0.0, 0.0],
        "grid_extent": [layout.n_cells_x * layout.grid_size / 1000.0, layout.n_cells_y * layout.grid_size / 1000.0],
        "marker_center_spacing": [layout.span_x / 1000.0, layout.span_y / 1000.0],
        "markers": markers,
    }


def render(layout: SheetLayout, args: argparse.Namespace, marker_ids: list[int], output: Path) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, args.dictionary))
    max_id = dictionary.bytesList.shape[0] - 1
    for mid in marker_ids:
        if not 0 <= mid <= max_id:
            raise SystemExit(f"Marker id {mid} is out of range for {args.dictionary} (0..{max_id}).")

    fig = plt.figure(figsize=(layout.paper_w / MM_PER_INCH, layout.paper_h / MM_PER_INCH))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, layout.paper_w)
    ax.set_ylim(layout.paper_h, 0)  # page coordinates: y down
    ax.set_aspect("equal")
    ax.axis("off")

    draw_grid(ax, layout, args.line_width, args.major_every)
    for (cx, cy), mid in zip(layout.centres, marker_ids, strict=True):
        bits = marker_bits(dictionary, mid)
        # Draw on top of the grid / quiet-zone patches.
        n_before = len(ax.patches)
        draw_marker(ax, bits, cx, cy, layout.marker_size)
        for p in ax.patches[n_before:]:
            p.set_zorder(3)
    if not args.no_annotations:
        draw_annotations(ax, layout, args, marker_ids)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=args.dpi, facecolor="white")
    plt.close(fig)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--output", type=Path, default=Path("markers/calibration_sheet.pdf"),
                   help="Output file; format from extension (.pdf, .svg, .png). JSON sidecar uses the same stem.")
    p.add_argument("--paper", choices=sorted(PAPER_SIZES_MM), default="a4", help="Paper size.")
    p.add_argument("--paper-size", type=float, nargs=2, metavar=("W_MM", "H_MM"), help="Custom paper size (overrides --paper).")
    p.add_argument("--landscape", action="store_true", help="Landscape orientation.")
    p.add_argument("--margin", type=float, default=10.0, help="Minimum distance (mm) from page edge to markers (printer margin).")
    p.add_argument("--marker-size", type=float, default=40.0, help="Marker side length (mm), outer black border included.")
    p.add_argument("--marker-ids", type=int, nargs=4, default=[10, 11, 12, 13], metavar=("ID0", "ID1", "ID2", "ID3"),
                   help="Marker ids for corners 0 (bottom-left), 1 (bottom-right), 2 (top-right), 3 (top-left).")
    p.add_argument("--dictionary", default=DEFAULT_DICTIONARY, help="OpenCV ArUco dictionary name.")
    p.add_argument("--grid-size", type=float, default=10.0, help="Grid cell size (mm).")
    p.add_argument("--major-every", type=int, default=5, help="Draw every Nth grid line thicker (0 disables).")
    p.add_argument("--line-width", type=float, default=0.15, help="Minor grid line width (mm).")
    p.add_argument("--quiet-zone", type=float, default=5.0, help="White border kept around each marker (mm).")
    p.add_argument("--no-snap", action="store_true",
                   help="Do not snap marker spacing to a whole number of grid cells (markers use the full page).")
    p.add_argument("--scale-bar", type=float, default=50.0, help="Length of the printed scale bar (mm).")
    p.add_argument("--no-annotations", action="store_true", help="Omit labels and scale bar.")
    p.add_argument("--dpi", type=int, default=600, help="Resolution for raster output (.png).")
    args = p.parse_args(argv)
    if not hasattr(cv2.aruco, args.dictionary):
        p.error(f"Unknown ArUco dictionary: {args.dictionary}")
    if len(set(args.marker_ids)) != 4:
        p.error("--marker-ids must be four distinct ids.")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    layout = compute_layout(args)
    render(layout, args, args.marker_ids, args.output)

    meta = build_metadata(layout, args, args.marker_ids)
    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Wrote {args.output} and {json_path}")
    print(f"  marker centre spacing: {layout.span_x:g} x {layout.span_y:g} mm, "
          f"grid: {layout.n_cells_x} x {layout.n_cells_y} cells of {layout.grid_size:g} mm")


if __name__ == "__main__":
    main()
