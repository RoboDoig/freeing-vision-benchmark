from typing import Literal, Dict
from pydantic import Field, computed_field, BaseModel
import math

from ucl_open.core.rig import Rig
from ucl_open.devices.behavior_board import BehaviorBoard
from ucl_open.video import SpinnakerCamera
from ucl_open.vision import Screen

from ucl_open_freeing_vision_benchmark import __semver__

class IntrinsicsCalibrationRig(Rig):
    version: Literal[__semver__] = __semver__
    screen: Screen
    behavior_board: BehaviorBoard
    camera: SpinnakerCamera