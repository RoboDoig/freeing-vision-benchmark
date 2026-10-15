import os

from ucl_open_freeing_vision_benchmark.rig import (
    UclOpenFreeingVisionBenchmarkRig,
    CalibratedSpinnakerCamera,
    ArucoCalibration
)
from open_rigs.devices.behavior_board import BehaviorBoard, CameraTriggerController
from open_rigs.video import SpinnakerCamera
from open_rigs.vision import Screen
from open_rigs.core import Vector3

subject_camera_trigger_frequency = 150
track_camera_trigger_frequency = 150

rig = UclOpenFreeingVisionBenchmarkRig(
    root_path="../temp_data",
    screen = Screen(
        window_width=1920,
        window_height=1080,
        target_render_frequency=360,
        target_update_frequency=360,
        display_index=1
    ),
    aruco_calibration_screen=ArucoCalibration(aruco_size=0.05, offset=Vector3(x=0.16, y=-0.08, z=0.0)),
    aruco_calibration_subject=ArucoCalibration(aruco_size=0.02, offset=Vector3(x=0.01, y=0.003, z=0.013)), # Here corresponds to marker's offset from optical axis of camera
    track_shape_scale=0.35,
    behavior_board=BehaviorBoard(
        port_name="COM4",
        camera_trigger_controller=CameraTriggerController(
            trigger0_frequency=subject_camera_trigger_frequency,
            trigger1_frequency=track_camera_trigger_frequency
        )
    ),
    subject_camera=CalibratedSpinnakerCamera(
        calibration_file="./intrinsics/camera_25224819/2026-7-16/2026-7-16T15-11-48_intrinsics.yml",
        serial_number="25224819",
        trigger_frequency=subject_camera_trigger_frequency,
        exposure_time=5000,
        binning=2
    ),
    track_camera=CalibratedSpinnakerCamera(
        calibration_file="./intrinsics/camera_25170682/2026-10-15/2026-10-15T12-12-48_intrinsics.yml",
        serial_number="25170682",
        trigger_frequency=track_camera_trigger_frequency,
        exposure_time=5000,
        binning=2
    ),
)

def main(path_seed: str = "./local/{schema}.json"):
    os.makedirs(os.path.dirname(path_seed), exist_ok=True)
    models = [rig]

    for model in models:
        with open(path_seed.format(schema=model.__class__.__name__), "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()