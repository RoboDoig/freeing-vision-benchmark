# Plan: Low-Latency Planar Tracking Benchmark

## Goal

Estimate the position (and heading) of an object moving on a flat arena from a single **fixed, intrinsically calibrated overhead camera**, with as little latency as possible, and use that estimate to update a monitor placed beside the arena.

Setup:

- One static camera views a flat arena.
- Four ArUco markers sit at the arena corners. We know where they are relative to each other.
- A monitor beside the arena shows an ArUco marker of known physical size.
- A fast tracker (blob tracking or a minimal SLEAP model) returns image keypoints on the object, e.g. the two eyes of a mouse.

The main question: **given 2D image keypoints and the assumption that the object lies on (or at a known height above) the arena plane, how do we recover its metric position in the arena?**

Short answer: calibrate once to get the arena plane's pose relative to the camera. After that, each tracked point is undistorted and then intersected with the plane along its camera ray. That intersection reduces to one precomputed 3×3 matrix (a homography) per point height, so runtime cost is negligible and **no ArUco detection is needed at runtime**.

---

## 1. Coordinate frames

| Frame | Symbol | Definition |
|---|---|---|
| Image | `(u, v)` | Raw (distorted) pixel coordinates from the tracking camera. |
| Normalised camera | `(x_n, y_n)` | Undistorted pinhole coordinates, `K⁻¹[u v 1]ᵀ` after removing lens distortion. |
| Camera | `C` | OpenCV convention: origin at the optical centre, x right, y down, z forward. Metres. |
| Arena (plane) | `P` | Origin at the centre of corner marker 0, x towards marker 1, y in-plane, z = plane normal pointing **towards the camera**. Metres. The arena surface is `z = 0`. |
| Monitor | `M` | Origin at the screen centre, x along screen width, y along screen height, z out of the screen. Metres. |

Store every rigid transform as `T_A_B`, the 4×4 matrix that maps points in frame B to frame A (`X_A = T_A_B · X_B`).

---

## 2. Calibration (offline, once per session, while the camera is static)

### 2.1 Arena marker layout → plane coordinates

We need the 2D coordinates `(X_i, Y_i, 0)` of each corner marker in frame `P`.

- **If coordinates are measured directly** (e.g. markers placed on a ruled grid or a laser-cut template), use them as they are. This is the recommended option: a template removes most measurement error.
- **If only pairwise distances are measured** (6 distances for 4 markers), solve for coordinates:
  1. Put marker 0 at the origin and marker 1 at `(d01, 0)`.
  2. Trilaterate markers 2 and 3 from their distances to markers 0 and 1, choosing the sign of `y` from the known layout.
  3. Refine all coordinates with a small least-squares fit to all 6 distances. The residual is a useful check on measurement quality.
- **Recommended:** also record each marker's in-plane rotation and its known side length, so that all **16 marker corners**, not just the 4 centres, can serve as calibration correspondences. Measure positions at the printed surface. If the markers are raised on a substrate, either account for the substrate thickness or define the plane at the marker surface and offset the tracking height (§3.3).

**Bench-test sheet:** `scripts/generate_calibration_sheet.py` generates a printable sheet (A4 by default) with four corner markers and a square grid, plus a JSON sidecar giving every marker corner in the plane frame above (metres, OpenCV corner order). That JSON can go straight into `solvePnP`, and the grid intersections act as ground-truth points for §5. Example: `uv run scripts/generate_calibration_sheet.py --marker-size 30 --grid-size 5 --output local/sheet.pdf` (see `--help`). Print at 100% and check the scale bar with a ruler.

An alternative that needs no measurement is to print a single large ChArUco/GridBoard sheet covering the arena, or to use a rigid frame with markers at fixed positions. Marker positions then come from the design file.

### 2.2 Arena pose relative to the camera (extrinsics)

Use the existing **Bonsai.Aruco `DetectMarkers`** pipeline, as already used in `main.bonsai`. Given the intrinsics YAML (`CameraParameters`) and the physical marker size, it returns each detected marker's pose in the camera frame (rotation + translation), with lens distortion and intrinsics accounted for. Calibration then becomes a rigid fit between two known point sets:

1. **Detect.** Run `DetectMarkers` on the static camera with `CameraParameters` set to the tracking camera's intrinsics YAML and `MarkerSize` set to the printed corner-marker size. Filter the output to the four arena-marker IDs.
2. **Average.** Collect N frames (e.g. 100–300) and average each marker's **translation** to get its centre `c_i^C` in the camera frame.
   - Use the median, or reject outliers, to drop occasional bad detections.
   - Ignore per-marker rotations: a single marker's orientation (and its pose ambiguity) is much noisier than its position, and four centres already define the plane.
3. **Rigid fit (Kabsch/Umeyama, no scale).** Find `R_C_P` and `t_C_P` that minimise `Σ ‖R·p_i + t − c_i^C‖²`, where `p_i = (X_i, Y_i, 0)` are the known arena coordinates from §2.1 (or from the calibration-sheet JSON). This gives `T_C_P` directly.
4. **Check the residuals:**
   - Per-marker fit residuals in mm.
   - Measured vs nominal distances between marker centres. A consistent scale error means the `MarkerSize` parameter does not match the printed size.
   - Plane flatness. Fitting a plane through the four centres should leave residuals of no more than about 1 mm.
   Steps 2–4 are implemented as Bonsai operators in `src/Extensions`: `RobustAverage` (per-marker batched average with MAD outlier rejection) and `KabschFit` (outputs a `RigidFit` with rotation, translation, OpenTK `Transform`, residuals and `ScaleRatio`). They are wired into `src/plane-benchmark.bonsai`.
5. **Optional refinement.** If the residuals are too large, also log the marker corner pixels from `DetectMarkers`. Then, offline in Python, run a joint `cv2.solvePnP` on all 16 corners at once (`SOLVEPNP_IPPE` + `solvePnPRefineLM`), initialised from the Kabsch result. A joint fit over the whole arena is better conditioned than four independent small-marker poses, especially in depth. Report the reprojection RMS in pixels.

Notes and checks for Bonsai.Aruco:

- **One marker size per node.** `DetectMarkers` assumes a single marker size. If the arena markers and the monitor marker differ in size, use a separate `DetectMarkers` node, or a separate calibration pass, per size. Alternatively, rescale the translations, since translation scales linearly with the assumed marker size.
- **Pose convention.** Confirm which axis convention and units Bonsai.Aruco uses for its output transform. The existing workflow feeds the transform into OpenGL rendering, which may use a different axis convention from OpenCV's camera frame. Do one sanity check: put a marker at a measured distance straight in front of the camera and verify the sign and magnitude of the translation. Convert to the frame conventions in §1 before fitting.
- **Detection parameters.** The same `Param1`/`Param2`/exposure tuning described in the README applies. The markers are static, so a longer exposure can be used during calibration if that helps detection.

Fitting through the 3D marker poses, rather than a raw 4-point `findHomography` on pixels, uses the known intrinsics and yields the full 3D pose. That pose is needed for the monitor (§2.3) and for height offsets (§3.3).

### 2.3 Monitor pose relative to the arena

The monitor marker is seen from an angle, and a single small, oblique marker gives a noisy pose with a possible flip ambiguity. Because we control the screen contents, the calibration should exploit that:

1. **Calibration-only screen pattern:** during calibration, draw several markers on the monitor (e.g. one near each screen corner, or a ChArUco board), with positions known in screen pixels.
2. Convert screen pixels to metres using the physical pixel pitch (screen width in m / horizontal resolution). The existing `ArucoCalibration` screen diagonal parameter already encodes this.
3. Get `T_C_M` from the screen markers' Bonsai.Aruco poses, using the same averaging and Kabsch fit as §2.2 against their known screen positions (z = 0 in frame `M`). The joint `solvePnP` refinement can be applied here too.
4. Compose the monitor pose in arena coordinates: `T_P_M = T_C_P⁻¹ · T_C_M`.
5. Sanity-check the result: the screen normal should be near-horizontal (a vertical monitor), the screen width should match its physical size, and its distance from the arena edge should match a tape measurement.

If only the single runtime marker can be used, apply its known offset to the screen centre, as the existing `ArucoCalibration.offset` does, and average its pose over many frames.

### 2.4 Calibration output

Write a calibration file (YAML/JSON, alongside the intrinsics) containing:

- intrinsics path, `K`, distortion coefficients, image size (including binning),
- marker IDs, sizes and plane coordinates,
- averaged per-marker camera-frame centres (from Bonsai.Aruco),
- `R_C_P`, `t_C_P`, the Kabsch fit residuals (and the reprojection RMS if refined),
- `T_P_M`, screen physical size and resolution,
- precomputed plane-to-image inverse homographies `G_h` for each tracked-point height `h` (see §3).

---

## 3. Runtime: image keypoint → arena position

### 3.1 Undistort the points, not the image

Undistorting the full image (`remap`) costs time on every frame. Instead, run the tracker on the raw image and undistort **only the 2–3 output keypoints**. The SLEAP model was trained on raw images anyway.

```
(x_n, y_n) = cv2.undistortPoints([[u, v]], K, dist)   # normalised coords, no P matrix
```

That is a few microseconds for two points.

### 3.2 Ray–plane intersection as a homography

A point at height `h` above the arena surface satisfies `X_P = (X, Y, h)`. Projecting it into normalised camera coordinates:

```
[x_n, y_n, 1]ᵀ  ∝  R·[X, Y, h]ᵀ + t  =  [ r1  r2  (h·r3 + t) ] · [X, Y, 1]ᵀ
```

where `r1, r2, r3` are the columns of `R_C_P`. So

```
H_h = [ r1  r2  (h·r3 + t) ]      (3×3, plane-at-height-h → normalised image)
G_h = H_h⁻¹                        (precomputed at calibration)

[X', Y', W]ᵀ = G_h · [x_n, y_n, 1]ᵀ
X = X' / W,  Y = Y' / W
```

Per point at runtime this is **one 3×3 matrix–vector product and a divide**. It is exactly equivalent to intersecting the camera ray with the plane `z = h`.

Equivalent explicit form, useful for verification:

```
c_P = -Rᵀ t                  # camera centre in arena frame
d_P = Rᵀ [x_n, y_n, 1]ᵀ      # ray direction in arena frame
s   = (h - c_P.z) / d_P.z
X_P = c_P + s · d_P
```

### 3.3 Why the height offset matters (parallax)

The eyes of a mouse are not on the floor; they sit roughly 1–2 cm above it. If you assume `h = 0`, the position estimate is pushed **outward from the point directly below the camera (its nadir)** by

```
error ≈ h · r / H_cam
```

where `r` is the horizontal distance from the nadir and `H_cam` is the camera height. Example: `H_cam = 0.8 m`, `h = 15 mm`, `r = 0.3 m` gives an error of about 5.6 mm. That is systematic and position-dependent, so it should be corrected.

- Give each keypoint type its own height, e.g. `h_eye`, `h_nose`, `h_tailbase`, measured from the animal or estimated (see §5), and precompute a `G_h` for each.
- Residual error from height variation (rearing, head tilt) is `δh · r / H_cam`. Mounting the camera higher and keeping the arena near the nadir reduces it.

### 3.4 Position and heading from two eyes

1. Project **each eye separately** onto its plane, giving `E_L` and `E_R` in arena coordinates. Do not take the midpoint in the image: perspective does not preserve midpoints. The error is small for nearby points, but doing it correctly costs nothing.
2. Position: `p = (E_L + E_R) / 2`.
3. Heading: perpendicular to the inter-eye vector, `e = E_R − E_L`, `heading = rotate(e, +90°)` (or −90°, depending on the left/right convention).
   - Blob tracking cannot tell left from right, so the sign of the heading is ambiguous. Resolve it with a third point (nose or head centroid), or with temporal continuity (choose the heading closest to the previous frame's).
4. Optional sanity check: `|E_R − E_L|` should be close to the true inter-ocular distance. A large deviation flags a bad detection, so you can skip that update.

### 3.5 Transform into monitor coordinates

To drive the display, express the animal's position in the monitor frame:

```
X_M = T_P_M⁻¹ · [X, Y, h, 1]ᵀ
```

What is rendered depends on the experiment. Two options:

- **Simple:** map the arena position to a screen position (e.g. a stimulus that follows the animal along the screen's x axis). This needs only `X_M.x`.
- **Perspective-correct ("window into a virtual world"):** use the eye position `X_M` as the viewpoint for an off-axis projection (generalised perspective projection, Kooima 2008), with the screen corners known from `T_P_M` and the screen's physical size.

Precompute `T_P_M⁻¹` and fold it into the runtime pipeline as one more fixed matrix.

---

## 4. Latency considerations

The geometry described above adds microseconds. The latency budget is dominated by:

1. **Exposure + readout + transfer:** short exposure, ROI cropping of the sensor to the arena, binning, and hardware triggering (the existing behaviour board).
2. **Tracker inference:** blob tracking (threshold + moments on a cropped ROI) will beat any network. For SLEAP, use the smallest input size and a TensorRT engine (as already exported in `models/track_model_reduced`), with batch size 1.
3. **Render/present:** a 360 Hz display with vsync or tearing configuration, no visualisers open (see README notes).

Additional measures:

- **No ArUco detection on the critical path.** Corner markers are used only at calibration. Optionally, run detection in a separate, low-rate branch (e.g. 1 Hz) to detect camera bumps, and raise a warning if reprojection error jumps.
- **Optional forward prediction:** once the end-to-end latency `L` has been measured, extrapolate the position `L` seconds ahead with a constant-velocity or Kalman model. Report latency with and without prediction.
- **Timestamp every stage** (frame hardware timestamp, tracker output, projection output, render submit) through the existing logging, so latency can be broken down per stage in `analysis/latency_analysis.ipynb`.

---

## 5. Validation

1. **Calibration quality:** report the PnP reprojection RMS for arena markers and monitor markers. Leave one arena marker out of the fit, predict its position, and report the error.
2. **Planar accuracy (h = 0):** place a fifth ArUco marker or a flat target at a grid of measured positions across the arena (e.g. 3×3). Compare its projected centre with the ground truth and report RMS and max error in mm, plus a spatial error map.
3. **Height correction:** repeat with the target raised on a block of known height `h`. Compare the `h = 0` and `h`-corrected estimates to show that the parallax correction works.
4. **Eye-height estimation (optional):** with a stationary animal or a model head of known height, find the `h` that minimises the inter-ocular distance error across positions.
5. **End-to-end spatial and temporal accuracy:** move a target along a known path (e.g. on a motorised stage or a pendulum), render the estimated position on the monitor, and record both with an independent high-speed camera or a photodiode. That gives:
   - spatial error of the on-screen output,
   - motion-to-photon latency (the headline benchmark number).

---

## 6. Implementation steps

1. **Python prototype** (`analysis/plane_tracking.py` plus a notebook):
   - marker layout → plane coordinates (including the pairwise-distance solver),
   - calibration from logged Bonsai.Aruco poses: average, Kabsch fit, optional PnP refinement, monitor pose, write the calibration file,
   - a `project_points(uv, h)` function using the undistort + `G_h` pipeline, plus a ray-intersection reference implementation, with a unit test asserting they agree,
   - a synthetic test: build a known camera and plane, project known 3D points, add noise, recover them, and check the error.
2. **Rig schema:** extend `src/ucl_open_freeing_vision_benchmark/rig.py` with an `ArenaCalibration` model (marker IDs, size, coordinates or distances, point heights, monitor marker config, calibration file path). Regenerate the C# schema.
3. **Calibration workflow:** a Bonsai workflow in which `DetectMarkers` logs per-marker poses (and corner pixels) for N frames while the screen shows the calibration marker pattern. A Python step then averages the poses, runs the Kabsch fit (plus optional PnP refinement) and writes the calibration file. Once validated, the fit could move into a C# operator so that calibration runs entirely in Bonsai.
4. **Runtime operator:** a small C# operator in `src/Extensions` (OpenCV.Net `UndistortPoints` + 3×3 multiply) that loads the calibration file and maps tracker keypoints to arena/monitor coordinates. First check whether existing `Bonsai.Vision` / `OpenRigs.Vision` operators already cover undistorting points and the perspective transform.
5. **Runtime workflow:** camera → (ROI) → blob tracker or SLEAP (`sleap-detection.bonsai`) → projection operator → screen update, with per-stage timestamps logged.
6. **Validation sessions and analysis:** run §5 and add results to the analysis notebooks.

---

## 7. Open questions

- What is the target spatial accuracy (mm) and latency (ms)? These decide whether height correction, forward prediction and the SLEAP model are needed, versus blob tracking alone.
- Can the corner markers be fixed to a rigid template so their coordinates are known by design, or will they be measured by hand?
- What should the monitor display: a simple position-following stimulus or a perspective-correct view? This decides whether only `X_M.x` is needed or the full 3D eye position.
- Is a third keypoint available to resolve the head direction, or must heading be disambiguated over time?
- Will the camera be moved between sessions? If so, calibration must run at the start of every session, and a drift check is needed.
