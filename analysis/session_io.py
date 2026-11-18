"""Readers and loaders for freeing-vision-benchmark sessions.

Sessions are loaded with the swc-aeon API (`swc.aeon.io.api.load`) and the open-rigs readers, following
https://github.com/open-rigs/open-rigs/blob/aeon-api/examples/data_loading/load_dataset.ipynb.
The cameras in `main-debug-spinnaker.bonsai` are logged as a fixed `<Device>/<Device>.csv` (one Harp
timestamp per frame) next to `<Device>.avi`, which `aeon.load` cannot locate because the files do not
follow the `<Device>_<DateTime>` chunk naming, so `CameraVideo` reads them directly.
"""

from collections.abc import Callable
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd
import swc.aeon.io.api as aeon
from dotmap import DotMap
from swc.aeon.io.api import Reader
from swc.aeon.schema.streams import Device

from open_rigs.io.streams import harp_device

BEHAVIOR_DEVICE_SCHEMA_URL = "https://raw.githubusercontent.com/harp-tech/device.behavior/main/device.yml"
"""Device schema used when the session does not contain `BehaviorBoard/BehaviorBoard.yml`."""


def find_device_schema(root: Path, device: str = "BehaviorBoard", url: str = BEHAVIOR_DEVICE_SCHEMA_URL) -> Path:
    """Returns the Harp device schema for a device, downloading the default schema if it was not logged."""
    device_yml = root / device / f"{device}.yml"
    if device_yml.exists():
        return device_yml
    downloaded, _ = urlretrieve(url)
    return Path(downloaded)


class CameraVideo(Reader):
    """Frame metadata for a `<Device>/<Device>.csv` + `<Device>.avi` pair.

    Columns follow `open_rigs.io.reader.RawVideo` so the data frame works with `swc.aeon.io.video.frames`:
    `_frame` (frame index in the video file), `_path` (video file) and `_epoch` (session directory).
    """

    def __init__(self, pattern: str, video_extension: str = "avi"):
        """Initialize the object with the device name and the video file extension."""
        super().__init__(pattern, columns=("_frame", "_path", "_epoch"), extension="csv")
        self.video_extension = video_extension

    def read(self, path: Path) -> pd.DataFrame:
        """Reads the frame timestamps in the CSV file, one row per frame in the video next to it."""
        data = pd.read_csv(path, header=0, names=["time"])
        data["_frame"] = data.index
        data["_path"] = str(path.with_suffix(f".{self.video_extension}"))
        data["_epoch"] = path.parts[-3]
        return data.set_index("time")


def camera_video(video_extension: str = "avi") -> Callable[[str], dict[str, CameraVideo]]:
    """Declares a camera device logged as `<Device>/<Device>.csv` + `<Device>.avi`."""

    def streams(path: str) -> dict[str, CameraVideo]:
        return {path: CameraVideo(path, video_extension)}

    return streams


def load_camera(root: Path, reader: CameraVideo) -> pd.DataFrame:
    """Reads a camera stream, converting Harp seconds to UTC datetimes like `aeon.load`."""
    data = reader.read(root / reader.pattern / f"{reader.pattern}.{reader.extension}")
    data.index = aeon.to_datetime(data.index)
    data.index.name = "time"
    return data


def declare_experiment(device_yml: Path) -> DotMap:
    """Declares the devices recorded by `main-debug-spinnaker.bonsai`.

    `BehaviorBoard` is the Harp Behavior board, with one reader per register. `SubjectCamera` and
    `TrackCamera` are triggered by the board's `Camera0` and `Camera1` outputs respectively.
    """
    return DotMap(
        [
            Device("BehaviorBoard", harp_device(device_yml)),
            Device("SubjectCamera", camera_video()),
            Device("TrackCamera", camera_video()),
        ]
    )


def frame_count_check(video: pd.DataFrame, triggers: pd.DataFrame, cameras_started: pd.Timestamp) -> dict:
    """Checks that every trigger issued after `StartCameras` produced a logged frame.

    Frames timestamped before `StartCameras` are not trigger-driven (for example the register-dump read
    reply logged at startup) and are excluded. Triggers issued after the last logged frame are reported
    separately: the workflow stops before their frame arrives, so they are expected and not counted as
    dropped frames. The camera passes when the remaining counts are equal.
    """
    frames = int((video.index >= cameras_started).sum())
    trailing = int((triggers.index > video.index.max()).sum())
    expected = len(triggers) - trailing
    return {
        "frames after StartCameras": frames,
        "triggers": len(triggers),
        "triggers after last frame": trailing,
        "dropped frames": expected - frames,
        "pass": frames == expected,
    }
