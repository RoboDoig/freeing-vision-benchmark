import os

from ucl_open_freeing_vision_benchmark.rig import (
    UclOpenFreeingVisionPlaneBenchmarkModel,
    CalibratedSpinnakerCamera,
    ArucoCalibration
)
from open_rigs.devices.behavior_board import BehaviorBoard, CameraTriggerController
from open_rigs.video import SpinnakerCamera
from open_rigs.vision import Screen
from open_rigs.core import Vector3

rig = UclOpenFreeingVisionPlaneBenchmarkModel(
    root_path="../temp_data",
    screen = Screen(
        window_width=1920,
        window_height=1080,
        target_render_frequency=360,
        target_update_frequency=360,
        display_index=1
    ),
    aruco_1=ArucoCalibration(aruco_size=0.04, offset=Vector3(x=0.0, y=0.0, z=0.0)),
    aruco_2=ArucoCalibration(aruco_size=0.04, offset=Vector3(x=-0.0, y=0.0, z=0.0)),
    camera=CalibratedSpinnakerCamera(
        calibration_file="./intrinsics/camera_25224819/2026-11-19/2026-11-19T13-6-11_intrinsics.yml",
        serial_number="25224819",
        trigger_frequency=150,
        exposure_time=5000,
        binning=2
    )
)

def main(path_seed: str = "./local/PlaneRig.json"):
    os.makedirs(os.path.dirname(path_seed), exist_ok=True)
    models = [rig]

    for model in models:
        with open(path_seed.format(schema=model.__class__.__name__), "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()