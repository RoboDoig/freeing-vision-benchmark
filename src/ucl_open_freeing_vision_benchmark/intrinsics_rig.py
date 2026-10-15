from typing import Literal, Dict
from pydantic import Field, computed_field, BaseModel
import math

from open_rigs.core.rig import Rig
from open_rigs.devices.behavior_board import BehaviorBoard
from open_rigs.video import SpinnakerCamera
from open_rigs.vision import Screen

from ucl_open_freeing_vision_benchmark import __semver__

class IntrinsicsCalibrationRig(Rig):
    version: Literal[__semver__] = __semver__
    screen: Screen
    behavior_board: BehaviorBoard
    camera: SpinnakerCamera