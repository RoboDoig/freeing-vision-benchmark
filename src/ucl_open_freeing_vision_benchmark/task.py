# Import core types
from typing import Literal
from pydantic import Field

from swc.aeon.io import reader
from swc.aeon.schema import BaseSchema, data_reader

from ucl_open_freeing_vision_benchmark import __semver__

# TODO - should inherit from some TaskParameters base class rather than BaseSchema
class UclOpenFreeingVisionBenchmarkTaskParameters(BaseSchema):
    ...


class UclOpenFreeingVisionBenchmarkTaskLogic(BaseSchema):
    version: Literal[__semver__] = __semver__
    name: Literal["UclOpenFreeingVisionBenchmark"] = Field(default="UclOpenFreeingVisionBenchmark", description="Name of the task logic", frozen=True)
    task_parameters: UclOpenFreeingVisionBenchmarkTaskParameters = Field(description="Parameters of the task logic")
    ...