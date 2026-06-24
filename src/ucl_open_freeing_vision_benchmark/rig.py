from typing import Literal, Dict
from pydantic import Field

from ucl_open.core.rig import Rig
from ucl_open.devices.behavior_board import BehaviorBoard
from ucl_open.video import SpinnakerCamera

from ucl_open_freeing_vision_benchmark import __semver__


class UclOpenFreeingVisionBenchmarkRig(Rig):
    version: Literal[__semver__] = __semver__
    behavior_board: BehaviorBoard
    subject_camera: SpinnakerCamera
    track_camera: SpinnakerCamera