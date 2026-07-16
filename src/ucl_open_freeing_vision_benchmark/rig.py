from typing import Literal, Dict
from pydantic import Field, computed_field, BaseModel
import math

from swc.aeon.schema import BaseSchema

from ucl_open.core.rig import Rig
from ucl_open.devices.behavior_board import BehaviorBoard
from ucl_open.video import SpinnakerCamera
from ucl_open.vision import Screen

from ucl_open_freeing_vision_benchmark import __semver__

class CalibratedSpinnakerCamera(SpinnakerCamera):
    calibration_file: str

class ArucoCalibration(BaseSchema):
    aruco_size: float = Field(description="The physical size of the aruco marker in meters", default=0.1)
    aspect_width: int = Field(description="The width of the display aspect ratio", default=16)
    aspect_height: int = Field(description="The height of the display aspect ration", default=9)
    screen_diagonal: float = Field(description="The diagonal of the viewable part of the screen/monitor in meters", default=0.684784)
    
    @computed_field
    @property
    def scale_factor(self) -> float:
        return math.sqrt(self.aspect_width**2 + self.aspect_height**2)
    
    @computed_field
    @property
    def view_width(self) -> float:
        return self.screen_diagonal * self.aspect_width / self.scale_factor
    
    @computed_field
    @property
    def view_height(self) -> float:
        return self.screen_diagonal * self.aspect_height / self.scale_factor
    
    @computed_field
    @property
    def extent_x(self) -> float:
        return self.aruco_size / self.view_width * 2
    
    @computed_field
    @property
    def extent_y(self) -> float:
        return self.aruco_size / self.view_height * 2

class UclOpenFreeingVisionBenchmarkRig(Rig):
    version: Literal[__semver__] = __semver__
    screen: Screen
    aruco_calibration: ArucoCalibration
    track_shape_scale: float
    behavior_board: BehaviorBoard
    subject_camera: CalibratedSpinnakerCamera
    track_camera: CalibratedSpinnakerCamera