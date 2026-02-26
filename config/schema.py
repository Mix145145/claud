"""Configuration schema — dataclasses and enums for Tuposcan."""
from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Optional


class CameraBackendType(enum.Enum):
    AUTO = "auto"
    PICAMERA2 = "picamera2"
    V4L2 = "v4l2"
    GSTREAMER = "gstreamer"
    STUB = "stub"


class Resolution(enum.Enum):
    FHD = "1920x1080"
    QHD = "2560x1440"   # 2K
    UHD = "3840x2160"   # 4K

    @property
    def width(self) -> int:
        return int(self.value.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.value.split("x")[1])

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


class StitchAlgorithm(enum.Enum):
    FEATHER_BLEND = "feather_blend"
    MULTIBAND_BLEND = "multiband_blend"
    ECC_REFINEMENT = "ecc_refinement"
    OPENCV_FALLBACK = "opencv_fallback"


class EngineState(enum.Enum):
    UNINITIALIZED = "uninitialized"
    IDLE = "idle"
    HOMING = "homing"
    JOGGING = "jogging"
    CALIBRATING = "calibrating"
    SCANNING = "scanning"
    PAUSED = "paused"
    STITCHING = "stitching"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class CameraConfig:
    backend: CameraBackendType = CameraBackendType.AUTO
    resolution: Resolution = Resolution.FHD
    exposure_time_us: int = 0       # 0 = auto
    analogue_gain: float = 0.0      # 0 = auto
    awb_enable: bool = True
    device_path: str = "/dev/video0"
    preview_fps: int = 15
    capture_warmup_frames: int = 3


@dataclass
class SerialConfig:
    port: str = "auto"              # auto-detect or explicit path
    baudrate: int = 250_000
    timeout_s: float = 10.0
    feed_rate_xy: int = 3000        # mm/min
    feed_rate_z: int = 600          # mm/min
    settle_delay_s: float = 0.3     # delay after M400 before capture


@dataclass
class ScanConfig:
    overlap_pct: float = 20.0       # percent overlap between frames
    z_height_mm: float = 50.0       # camera height
    area_width_mm: float = 200.0
    area_height_mm: float = 200.0
    origin_x_mm: float = 0.0
    origin_y_mm: float = 0.0
    stitch_algorithm: StitchAlgorithm = StitchAlgorithm.FEATHER_BLEND
    auto_stitch: bool = True


@dataclass
class CalibrationConfig:
    marker_size_mm: float = 5.0
    num_frames: int = 8             # frames for statistical calibration
    aruco_dicts: list[str] = field(default_factory=lambda: [
        "DICT_4X4_50",
        "DICT_5X5_50",
        "DICT_6X6_50",
        "DICT_APRILTAG_36h11",
    ])
    use_clahe: bool = True
    clahe_clip: float = 2.0
    clahe_grid: int = 8
    use_threshold: bool = True
    threshold_block_size: int = 11
    threshold_c: int = 2


@dataclass
class PathsConfig:
    scans_dir: str = "scans"
    config_dir: str = "config"
    fov_profiles_file: str = "config/fov_profiles.json"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    auth_password: str = "tuposcan"
    session_timeout_min: int = 60


@dataclass
class TuposcanConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    web: WebConfig = field(default_factory=WebConfig)
