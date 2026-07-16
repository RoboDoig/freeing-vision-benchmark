# Freeing Vision Benchmark

## Summary

This repo contains calibration and benchmarking procedures for the `freeing-vision` project.

## Procedure

### Connecting Cameras

Connect both the subject and tracking camera via USB. It is crucial that these cameras are connected with a camera / USB port / cable combination that allows them to achieve the maximum device link throughput. This can be confirmed by connecting a camera and checking the device link throughput limit property in `SpinView` (under the Settings tab). The value should be at least 500000000.

#### Configuring Camera (currently 'semi-manual' - rewrite when .NET SDK is installed on this machine)

Open `SpinView` and set up the camera to acquire at the desired frame rate, for this benchmark should be ~200Hz:

1. Set device link throughput limit to max
2. Exposure Mode --> Timed, Exposure auto --> Off
3. Image format to maximum size without binning or decimation
4. Manually configure exposure time and acquisition frame rate such that a clear picture is obtained at the maximum frame rate possible.
5. Check discrepancies between Processed FPS and Camera FPS to ensure frames are not being dropped.

Repeat this configuration for both cameras and record their serial numbers and final settings.

### Intrinsics Calibration (currently 'semi-manual' - rewrite when .NET SDK is installed on this machine)

Open `intrinsic-calibration.bonsai` and set the camera serial number for the camera to run intrinsic calibration on.

Run the workflow and ensure that the `CollectionVisualizer` is open. This will display the live camera stream. The workflow should also display a checkerboard calibration pattern fullscreen on a monitor.

To calibrate the camera, ensure that it is capturing the full checkerboard display and press `Sample` (or hit Space). Collect **10 samples** using different view angles and distances.

When the required image number has been reached, the visualizer will run calibration across all images and display the checkerboard with detected corners in the final panel of the visualizer.

Calibration results are saved as:

```text
src\intrinsics\camera_<serial>\<date>\<timestamp>_intrinsics.yml
```

Confirm that the YAML contains the correct image width and height. The workflow may crash after saving, so check that the YAML was created before repeating calibration.

Repeat the calibration for both cameras and make a note of each saved file for use in the benchmark.

### Tracking Benchmark (currently 'semi-manual' - rewrite when .NET SDK is installed on this machine)

#### Configuration

The benchmark is configured by writing a rig configuration `.json`, an example of which is provided in `examples/rig.py`. Key points:

* Tracking and Subject cameras refer, respectively, to the static camera recording the position of the free camera; and the free camera recording the screen.
* Confirm that each camera serial number is assigned to the correct role.
* Screen parameters must match the resolution, display index, and desired display rate of the monitor used for the benchmark.
* ArucoCalibration parameters must also be chosen to match the display parameters of the monitor used for the benchmark - in particular the screen diagonal must accurately match the true viewable area of the screen.
* The correct intrinsic calibration YAML must be loaded into `DetectMarkers`.

The standard `main.bonsai` workflow assumes that a behavior board is connected. If no board is available, use `main-no-board.bonsai` and its matching rig configuration.

Once a configuration `.json` has been produced, open the appropriate workflow and set the `RigPath` property to point to this file.

With the subject camera pointed at the screen, run the workflow. The benchmark monitor should display an Aruco marker, and a stimulus square should appear that follows the camera's field of view.

Check that the Aruco is being detected correctly by opening the visualizer for `DetectMarkers` in the `ArucoTracking` group workflow. Certain parameters need to be adjusted to ensure stable tracking of the marker:

* A good intrinsic calibration file for the camera must be specified. If all other parameters fail, you may need to rerun the intrinsic calibration.
* A combination of camera exposure, and `Param1`/`Param2` on `DetectMarkers`. The exposure of the camera must be high enough to show clear contrast on the Aruco marker, but low enough to maintain a high frame rate.
* Avoid placing the camera extremely close to the marker, as this may cause instability or crashes.

If all parameters are set correctly, the visualizer for `DetectMarkers` should display a consistent wireframe cube over the Aruco marker showing its location on screen and normal direction.

After running the benchmark, confirm that the expected output files were created in the configured output directory and are not empty.
