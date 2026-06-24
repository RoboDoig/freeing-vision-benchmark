import os

from ucl_open_freeing_vision_benchmark.rig import (
    UclOpenFreeingVisionBenchmarkRig
)
from ucl_open.devices.behavior_board import BehaviorBoard, CameraTriggerController
from ucl_open.video import SpinnakerCamera

rig = UclOpenFreeingVisionBenchmarkRig(
    root_path="../temp_data",
    behavior_board=BehaviorBoard(
        port_name="COM13",
        camera_trigger_controller=CameraTriggerController(
            trigger0_frequency=150,
            trigger1_frequency=150
        )
    ),
    track_camera=SpinnakerCamera(
        serial_number="25224819",
        trigger_frequency=150,
        exposure_time=3000
    ),
    subject_camera=SpinnakerCamera(
        serial_number="18474551",
        trigger_frequency=150,
        exposure_time=3000
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