import os

from ucl_open_freeing_vision_benchmark.intrinsics_rig import (
    IntrinsicsCalibrationRig
)

from ucl_open.core.rig import Rig
from ucl_open.devices.behavior_board import BehaviorBoard, CameraTriggerController
from ucl_open.video import SpinnakerCamera
from ucl_open.vision import Screen

rig = IntrinsicsCalibrationRig(
    root_path="../temp_data",
    screen = Screen(
        window_width=1920,
        window_height=1080,
        target_render_frequency=240,
        target_update_frequency=240,
        display_index=0
    ),
    behavior_board=BehaviorBoard(
        port_name="COM3",
        camera_trigger_controller=CameraTriggerController(
            trigger0_frequency=150,
            trigger1_frequency=150
        )
    ),
    camera=SpinnakerCamera(
        serial_number="25224819",
        trigger_frequency=150,
        exposure_time=3000,
        binning=2
    )
)

def main(path_seed: str = "./local/{schema}.json"):
    os.makedirs(os.path.dirname(path_seed), exist_ok=True)
    models = [rig]

    for model in models:
        with open(path_seed.format(schema=model.__class__.__name__), "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()