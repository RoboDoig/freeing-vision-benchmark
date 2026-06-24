from typing import Literal, Dict
from pydantic import Field

from ucl_open.core.rig import Rig

from ucl_open_freeing_vision_benchmark import __semver__


class UclOpenFreeingVisionBenchmarkRig(Rig):
    version: Literal[__semver__] = __semver__
    ...