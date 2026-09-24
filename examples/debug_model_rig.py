import os

from ucl_open_freeing_vision_benchmark.rig import (
    UclOpenFreeingVisionBenchmarkRigDebugModel,
    CalibratedSpinnakerCamera,
    ArucoCalibration
)
from ucl_open.devices.behavior_board import BehaviorBoard, CameraTriggerController
from ucl_open.video import SpinnakerCamera
from ucl_open.vision import Screen
from ucl_open.core import Vector3

rig = UclOpenFreeingVisionBenchmarkRigDebugModel(
    root_path="../temp_data",
    screen = Screen(
        window_width=2560,
        window_height=1600,
        target_render_frequency=360,
        target_update_frequency=360,
        display_index=1
    ),
    aruco_1=ArucoCalibration(aruco_size=0.05, screen_diagonal=0.4064, offset=Vector3(x=0.15, y=0, z=0.0), aspect_width=16, aspect_height=10),
    aruco_2=ArucoCalibration(aruco_size=0.05, screen_diagonal=0.4064, offset=Vector3(x=-0.15, y=0.0, z=0.0), aspect_width=16, aspect_height=10),
    intrinsics_calibration="./intrinsics/camera_25224819/2026-7-16/2026-7-16T15-11-48_intrinsics.yml",
)

def main(path_seed: str = "./local/{schema}.json"):
    os.makedirs(os.path.dirname(path_seed), exist_ok=True)
    models = [rig]

    for model in models:
        with open(path_seed.format(schema=model.__class__.__name__), "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()