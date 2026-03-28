"""
SuperPicky 配置管理模块。
SuperPicky configuration management module.

本文件负责静态常量、路径约定、轻量运行时覆盖入口与共享懒加载注册器。
This file owns static constants, path conventions, lightweight runtime overrides, and the shared lazy registry.

维护分层：
Maintenance layering:
- `config.py`：公共读取入口与基础配置。
  `config.py`: shared read entry points and foundational configuration.
- `advanced_config.py`：高级持久化配置的默认值、读写、迁移与 UI 对接。
  `advanced_config.py`: defaults, persistence, migration, and UI integration for advanced persistent settings.
- 用户配置文件默认位于 `get_app_config_dir() / "advanced_config.json"`。
  The user config file defaults to `get_app_config_dir() / "advanced_config.json"`.

文档入口：
Documentation entry points:
- 维护指南：当前文件本身。
  Maintenance guide: this file itself.
- 中英对照配置指南：TODO - 待补正式路径。
  Bilingual configuration guide: TODO - add the final path later.
"""

import json
import os
import platform
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import torch


# =========================
# 基础路径工具
# =========================

# 这一层只定义路径约定，不负责真实配置读写。
# This layer only defines path conventions and does not implement actual config read/write behavior.


def resource_path(relative_path: str) -> str:
    """
    返回打包资源路径，兼容开发环境与 PyInstaller。
    Return a packaged resource path compatible with development mode and PyInstaller.

    `relative_path` 是资源相对路径，例如 `models/yolo11l-seg.pt`。
    `relative_path` is the resource-relative path, for example `models/yolo11l-seg.pt`.

    这里只用于内置资源定位，不能拿来定位用户配置或用户数据。
    This is only for bundled resource lookup and must not be used for user config or user data paths.
    """
    meipass = getattr(sys, '_MEIPASS', None)
    if isinstance(meipass, str):
        return os.path.join(meipass, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


def get_app_config_dir(app_name: str = 'SuperPicky') -> Path:
    """
    返回跨平台应用配置目录（存放 advanced_config.json、补丁等程序配置）。
    Return the cross-platform application config directory.

    ⚠️  与 get_app_data_dir() 完全不同的路径，请勿混用：
      macOS : ~/Library/Application Support/SuperPicky/
      Windows: ~/AppData/Local/SuperPicky/
      Linux  : ~/.config/SuperPicky/

    用途：advanced_config.json、code_updates/（补丁目录）等程序级配置。
    """
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / app_name
    if sys.platform == 'win32':
        return Path.home() / 'AppData' / 'Local' / app_name
    return Path.home() / '.config' / app_name


def get_app_data_dir(app_name: str = 'SuperPicky') -> Path:
    """
    返回跨平台用户数据目录（存放 birdid 设置等用户产物）。
    Return the cross-platform user data directory.

    ⚠️  与 get_app_config_dir() 完全不同的路径，请勿混用：
      所有平台：~/Documents/SuperPicky_Data/

    用途：birdid_dock_settings.json 等用户可见的数据文件。
    切勿用于存放补丁或程序内部配置（应使用 get_app_config_dir()）。
    """
    return Path.home() / 'Documents' / f'{app_name}_Data'


def get_patch_dir(app_name: str = 'SuperPicky') -> Path:
    """
    返回在线补丁目录。
    Return the online patch directory.

    补丁目录派生自配置目录。
    The patch directory is derived from the config directory.
    """
    return get_app_config_dir(app_name) / 'code_updates'


def get_birdid_settings_path(app_name: str = 'SuperPicky') -> Path:
    """
    返回 BirdID Dock 设置文件路径。
    Return the BirdID Dock settings file path.

    该文件属于用户数据，因此放在 app data 目录下。
    This file belongs to user data, so it lives under the app data directory.
    """
    return get_app_data_dir(app_name) / 'birdid_dock_settings.json'


# =========================
# 可覆盖配置（ENV + 配置文件）
# =========================

# 这里只读取覆盖值，不定义高级配置 schema。
# This layer only reads override values and does not define the advanced config schema.
# 优先级：ENV > advanced_config.json > 默认值。
# Priority: ENV > advanced_config.json > default value.

_override_cache: Optional[Dict[str, Any]] = None
_override_lock = threading.RLock()


def _load_override_file() -> Dict[str, Any]:
    """
    线程安全加载 advanced_config.json，并做进程内缓存。
    Load advanced_config.json in a thread-safe way and cache it per process.

    文件不存在或解析失败时返回空字典，让调用方回退默认值。
    Returns an empty dict when the file is missing or invalid so callers can fall back to defaults.
    """
    global _override_cache
    with _override_lock:
        if _override_cache is not None:
            return _override_cache

        cfg_path = get_app_config_dir() / 'advanced_config.json'
        if not cfg_path.exists():
            _override_cache = {}
            return _override_cache

        try:
            _override_cache = json.loads(cfg_path.read_text(encoding='utf-8'))
        except Exception:
            _override_cache = {}
        return _override_cache if _override_cache is not None else {}


def _parse_bool(value: Optional[str], default: bool) -> bool:
    """
    把字符串值解析为布尔值。
    Parse a string-like value into a boolean.

    支持 `1/true/yes/on` 和 `0/false/no/off`，否则返回默认值。
    Supports `1/true/yes/on` and `0/false/no/off`, otherwise returns the default.
    """
    if value is None:
        return default
    norm = str(value).strip().lower()
    if norm in {'1', 'true', 'yes', 'on'}:
        return True
    if norm in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _env_or_override(name: str, override_key: Optional[str], default: Any) -> Any:
    """
    按 ENV > JSON > 默认值 的优先级读取覆盖值。
    Read an override using the priority order ENV > JSON > default.

    这里不做类型转换，调用方自行转成 `int`、`float` 或 `str`。
    No type conversion is done here; callers should convert to `int`, `float`, or `str` themselves.
    """
    env_value = os.getenv(name)
    if env_value is not None and str(env_value).strip() != '':
        return env_value

    if override_key:
        loaded = _load_override_file()
        if override_key in loaded:
            return loaded.get(override_key)

    return default


# =========================
# 静态常量分层
# =========================

# 这些 dataclass 用来按领域收拢常量。
# These dataclasses group constants by domain.


@dataclass
class FileConfig:
    """
    文件处理相关静态配置。
    Static configuration related to file handling.

    这些列表会被 RAW/JPG 分类逻辑直接消费。
    These lists are consumed directly by RAW/JPG classification logic.
    """

    # RAW_EXTENSIONS：被视为 RAW 的扩展名列表。
    # RAW_EXTENSIONS: extensions treated as RAW files.
    RAW_EXTENSIONS: List[str] = field(default_factory=lambda: [
        '.nef', '.cr2', '.cr3', '.arw', '.raf',
        '.orf', '.rw2', '.pef', '.dng', '.3fr', '.iiq'
    ])
    # JPG_EXTENSIONS：被视为 JPG/JPEG 的扩展名列表。
    # JPG_EXTENSIONS: extensions treated as JPG/JPEG files.
    JPG_EXTENSIONS: List[str] = field(default_factory=lambda: ['.jpg', '.jpeg'])


@dataclass
class DirectoryConfig:
    """
    输出目录与报告文件命名配置。
    Naming configuration for output directories and report files.

    修改这些值会影响结果目录结构与报告文件名。
    Changing these values affects result folder layout and report filenames.
    """

    # 高质量照片目录。
    # Directory for excellent photos.
    EXCELLENT_DIR: str = '优秀'
    # 普通保留照片目录。
    # Directory for standard keepers.
    STANDARD_DIR: str = '标准'
    # 无鸟或废片目录。
    # Directory for no-bird or rejected photos.
    NO_BIRDS_DIR: str = '没鸟'
    # 内部临时目录。
    # Internal temporary directory.
    TEMP_DIR: str = '_temp'
    # 特定工作流使用的 Redbox 目录。
    # Redbox directory for specific workflows.
    REDBOX_DIR: str = 'Redbox'
    # 裁切临时目录。
    # Temporary crop directory.
    CROP_TEMP_DIR: str = '.crop_temp'

    # 旧算法优秀目录。
    # Old-algorithm excellent directory.
    OLD_ALGORITHM_EXCELLENT: str = '老算法优秀'
    # 新算法优秀目录。
    # New-algorithm excellent directory.
    NEW_ALGORITHM_EXCELLENT: str = '新算法优秀'
    # 双算法共同优秀目录。
    # Intersection directory for both algorithms.
    BOTH_ALGORITHMS_EXCELLENT: str = '双算法优秀'
    # 算法差异目录。
    # Directory for algorithm-difference samples.
    ALGORITHM_DIFF_DIR: str = '算法差异'

    # 处理日志文件名。
    # Processing log filename.
    LOG_FILE: str = '.process_log.txt'
    # 主报告 SQLite 文件名。
    # Primary SQLite report filename.
    REPORT_FILE: str = '.report.db'
    # 算法对比 CSV 文件名。
    # Algorithm comparison CSV filename.
    COMPARISON_REPORT_FILE: str = '.algorithm_comparison.csv'


@dataclass
class AIConfig:
    """
    AI 模型与推理相关静态配置。
    Static configuration related to AI models and inference.

    这些值服务于模型定位与基础推理行为，不替代高级用户参数。
    These values support model lookup and baseline inference behavior and do not replace advanced user-facing parameters.
    """

    # 主模型相对路径。
    # Relative path to the main model.
    MODEL_FILE: str = 'models/yolo11l-seg.pt'
    # “鸟”类别的 class id。
    # Class id for the "bird" category.
    BIRD_CLASS_ID: int = 14
    # 推理目标尺寸。
    # Target inference image size.
    TARGET_IMAGE_SIZE: int = 1024
    # 主体居中判断默认阈值。
    # Default threshold for centered-subject checks.
    CENTER_THRESHOLD: float = 0.15
    # 锐度归一化策略标识，默认不指定。
    # Sharpness normalization strategy marker, unset by default.
    SHARPNESS_NORMALIZATION: Optional[str] = None

    def get_model_path(self) -> str:
        """
        返回主模型的实际可访问路径。
        Return the actual accessible path to the main model.

        调用方不应自行拼 PyInstaller 临时目录。
        Callers should not manually stitch together PyInstaller temporary paths.
        """
        return resource_path(self.MODEL_FILE)


@dataclass
class UIConfig:
    """
    UI 展示层静态常量。
    Static constants for the UI presentation layer.

    这里只放显示缩放和进度边界，不放业务阈值。
    This group is for display scaling and progress bounds, not business thresholds.
    """

    # 置信度百分比缩放。
    # Percentage scale for confidence display.
    CONFIDENCE_SCALE: float = 100.0
    # 面积显示缩放。
    # Display scale for area values.
    AREA_SCALE: float = 1000.0
    # 锐度显示缩放。
    # Display scale for sharpness values.
    SHARPNESS_SCALE: int = 20
    # 进度条最小值。
    # Minimum progress-bar value.
    PROGRESS_MIN: int = 0
    # 进度条最大值。
    # Maximum progress-bar value.
    PROGRESS_MAX: int = 100
    # 默认提示音次数。
    # Default completion beep count.
    BEEP_COUNT: int = 3


@dataclass
class CSVConfig:
    """
    CSV 报告结构配置。
    CSV report structure configuration.

    `HEADERS` 定义导出列顺序，兼容性要求较高。
    `HEADERS` defines export-column order and carries relatively high compatibility requirements.
    """

    # 报告列名顺序定义。
    # Ordered definition of report header names.
    HEADERS: List[str] = field(default_factory=lambda: [
        'filename', 'found_bird', 'AI score', 'bird_centre_x',
        'bird_centre_y', 'bird_area', 's_bird_area',
        'laplacian_var', 'sobel_var', 'fft_high_freq', 'contrast',
        'edge_density', 'background_complexity', 'motion_blur',
        'normalized_new', 'composite_score', 'result_new',
        'dominant_bool', 'centred_bool', 'sharp_bool', 'class_id'
    ])


@dataclass
class ServerConfig:
    """
    BirdID 服务默认配置。
    Default configuration for the BirdID service.

    这些值可被 ENV 覆盖，并影响绑定地址、启动等待和健康检查节奏。
    These values can be overridden by ENV and affect bind address, startup wait, and health-check cadence.
    """

    # 默认监听地址。ENV: SUPERPICKY_SERVER_HOST
    # Default bind host. ENV: SUPERPICKY_SERVER_HOST
    HOST: str = '127.0.0.1'
    # 默认端口。ENV: SUPERPICKY_SERVER_PORT
    # Default port. ENV: SUPERPICKY_SERVER_PORT
    PORT: int = 5156
    # 单次健康检查超时。ENV: SUPERPICKY_SERVER_HEALTH_TIMEOUT
    # Single health-check timeout. ENV: SUPERPICKY_SERVER_HEALTH_TIMEOUT
    HEALTH_TIMEOUT_SECONDS: float = 2.0
    # 启动就绪总等待时间。ENV: SUPERPICKY_SERVER_STARTUP_WAIT
    # Total startup readiness wait time. ENV: SUPERPICKY_SERVER_STARTUP_WAIT
    STARTUP_WAIT_SECONDS: float = 10.0
    # 健康检查轮询间隔。ENV: SUPERPICKY_SERVER_POLL_INTERVAL
    # Health-check polling interval. ENV: SUPERPICKY_SERVER_POLL_INTERVAL
    POLL_INTERVAL_SECONDS: float = 0.5

    @classmethod
    def load(cls) -> 'ServerConfig':
        """
        按覆盖优先级构造 ServerConfig。
        Build ServerConfig using the override priority rules.

        类型转换统一在这里做，避免调用方重复解析 ENV。
        Type coercion is centralized here so callers do not repeat ENV parsing.
        """
        host = str(_env_or_override('SUPERPICKY_SERVER_HOST', None, cls.HOST))
        port = int(_env_or_override('SUPERPICKY_SERVER_PORT', None, cls.PORT))
        health_timeout = float(_env_or_override('SUPERPICKY_SERVER_HEALTH_TIMEOUT', None, cls.HEALTH_TIMEOUT_SECONDS))
        startup_wait = float(_env_or_override('SUPERPICKY_SERVER_STARTUP_WAIT', None, cls.STARTUP_WAIT_SECONDS))
        poll = float(_env_or_override('SUPERPICKY_SERVER_POLL_INTERVAL', None, cls.POLL_INTERVAL_SECONDS))
        return cls(
            HOST=host,
            PORT=port,
            HEALTH_TIMEOUT_SECONDS=health_timeout,
            STARTUP_WAIT_SECONDS=startup_wait,
            POLL_INTERVAL_SECONDS=poll,
        )


@dataclass
class EndpointConfig:
    """
    远程服务端点默认配置。
    Default configuration for remote service endpoints.

    这些 URL 会影响下载页、eBird 查询与 Nominatim 反查等网络行为。
    These URLs affect network behavior such as download pages, eBird queries, and Nominatim reverse lookups.
    """

    # 镜像或资源下载基础地址。
    # Base URL for mirrors or downloadable resources.
    MIRROR_BASE_URL: str = 'http://1.119.150.179:59080/superpicky'
    # 给用户打开的下载页面地址。
    # Download page URL opened for the user.
    UPDATE_DOWNLOAD_PAGE: str = 'https://superpicky.jamesphotography.com.au/#download'
    # eBird API 根地址。
    # Root URL for the eBird API.
    EBIRD_API_BASE: str = 'https://api.ebird.org/v2'
    # Nominatim 反向地理编码接口。
    # Reverse geocoding endpoint for Nominatim.
    NOMINATIM_REVERSE_URL: str = 'https://nominatim.openstreetmap.org/reverse'

    @classmethod
    def load(cls) -> 'EndpointConfig':
        """
        按覆盖优先级构造 EndpointConfig。
        Build EndpointConfig using the override priority rules.

        统一入口便于未来继续扩展 ENV 覆盖。
        A unified entry point makes future ENV override expansion easier.
        """
        return cls(
            MIRROR_BASE_URL=str(_env_or_override('SUPERPICKY_MIRROR_BASE_URL', None, cls.MIRROR_BASE_URL)),
            UPDATE_DOWNLOAD_PAGE=str(_env_or_override('SUPERPICKY_DOWNLOAD_PAGE', None, cls.UPDATE_DOWNLOAD_PAGE)),
            EBIRD_API_BASE=str(_env_or_override('SUPERPICKY_EBIRD_API_BASE', None, cls.EBIRD_API_BASE)),
            NOMINATIM_REVERSE_URL=str(_env_or_override('SUPERPICKY_NOMINATIM_REVERSE_URL', None, cls.NOMINATIM_REVERSE_URL)),
        )


class Config:
    """
    主配置聚合类。
    Main configuration aggregation class.

    这是项目中最常用的统一读取入口，用来整合不同层次的配置。
    This is the most common unified read entry point used to aggregate different configuration layers.
    """

    def __init__(self):
        """
        构造统一配置对象。
        Construct the unified configuration object.

        初始化时建立静态常量分组，并加载服务与端点配置。
        Initialization builds static config groups and loads service and endpoint configuration.
        """
        self.file = FileConfig()
        self.directory = DirectoryConfig()
        self.ai = AIConfig()
        self.ui = UIConfig()
        self.csv = CSVConfig()
        self.server = ServerConfig.load()
        self.endpoints = EndpointConfig.load()

    def get_directory_names(self) -> Dict[str, str]:
        """
        返回常用输出目录名映射。
        Return a mapping of commonly used output directory names.

        适合 UI 展示和流程内统一引用目录名。
        Useful for UI display and for consistent directory references inside processing flows.
        """
        return {
            'excellent': self.directory.EXCELLENT_DIR,
            'standard': self.directory.STANDARD_DIR,
            'no_birds': self.directory.NO_BIRDS_DIR,
            'temp': self.directory.TEMP_DIR,
            'redbox': self.directory.REDBOX_DIR,
            'crop_temp': self.directory.CROP_TEMP_DIR,
        }

    def is_raw_file(self, filename: str) -> bool:
        """
        判断文件名是否属于 RAW 扩展名集合。
        Check whether a filename belongs to the RAW extension set.

        这里只按扩展名判断，不检查内容或 MIME。
        This only checks file extensions and does not inspect content or MIME type.
        """
        _, ext = os.path.splitext(filename)
        return ext.lower() in self.file.RAW_EXTENSIONS

    def is_jpg_file(self, filename: str) -> bool:
        """
        判断文件名是否属于 JPG/JPEG 扩展名集合。
        Check whether a filename belongs to the JPG/JPEG extension set.

        这是轻量判断入口，不做内容探测。
        This is a lightweight classification entry and does not inspect file contents.
        """
        _, ext = os.path.splitext(filename)
        return ext.lower() in self.file.JPG_EXTENSIONS


# =========================
# 懒加载资源注册器
# =========================

# 这个注册器用于跨模块共享可缓存、可复用、构造成本高的对象。
# This registry is for cacheable, reusable, high-construction-cost objects shared across modules.
# 不适合用来存放短生命周期业务状态。
# It is not suitable for short-lived business state.

_MISSING = object()


class LazyRegistry:
    """
    线程安全懒加载注册器。
    Thread-safe lazy registry.

    目标是避免重复初始化重量级对象，并提供统一的共享入口。
    Its goal is to avoid repeated heavy initialization and provide a unified sharing entry point.
    """

    def __init__(self):
        """初始化内部存储和锁。 Initialize the internal storage and lock."""
        self._values: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        """
        读取缓存对象，不存在时在锁内创建并缓存。
        Read a cached object and create/cache it inside the lock if it is missing.

        采用无锁快速读取加锁内二次检查，避免并发重复创建。
        This uses a fast unlocked read plus a locked second check to avoid duplicate concurrent construction.
        """
        value = self._values.get(key, _MISSING)
        if value is not _MISSING:
            return value
        with self._lock:
            value = self._values.get(key, _MISSING)
            if value is _MISSING:
                value = factory()
                self._values[key] = value
            return value

    def get(self, key: str, default: Any = None) -> Any:
        """
        读取缓存值，不触发创建。
        Read a cached value without triggering creation.
        """
        with self._lock:
            return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        显式设置缓存值。
        Explicitly set a cached value.

        不要用它存放临时业务状态。
        Do not use this to stash temporary business state.
        """
        with self._lock:
            self._values[key] = value

    def clear(self, key: str) -> None:
        """
        清除单个缓存项。
        Clear a single cached item.

        适合测试隔离或强制下次重建。
        Useful for test isolation or forcing the next access to rebuild the object.
        """
        with self._lock:
            self._values.pop(key, None)

    def clear_all(self) -> None:
        """
        清空所有缓存项。
        Clear all cached items.

        若缓存对象持有外部资源，应先确保存在显式关闭流程。
        If cached objects hold external resources, make sure an explicit shutdown flow exists first.
        """
        with self._lock:
            self._values.clear()


_lazy_registry = LazyRegistry()


def get_lazy_registry() -> LazyRegistry:
    """
    返回全局懒加载注册器实例。
    Return the global lazy-registry instance.

    调用方应通过此入口获取共享注册器，避免自行新建导致缓存割裂。
    Callers should use this entry point to get the shared registry and avoid cache fragmentation caused by creating their own registries.
    """
    return _lazy_registry


# =========================
# 设备选择
# =========================

# 设备选择逻辑必须集中，避免不同模块各自判断 CUDA/MPS/CPU。
# Device selection must stay centralized so different modules do not each make their own CUDA/MPS/CPU decisions.
# 若打包版与源码行为不同，优先怀疑打包环境中的 Torch/CUDA 运行时差异。
# If packaged behavior differs from source behavior, suspect Torch/CUDA runtime differences in the packaged environment first.


def get_best_device():
    """
    返回当前环境下最合适的 Torch 设备对象。
    Return the most appropriate Torch device object for the current environment.

    顺序为：macOS 先 MPS 再 CPU，其他平台先 CUDA 再 CPU。
    The order is: on macOS use MPS then CPU, on other platforms use CUDA then CPU.

    任意检测异常时保守回退到 CPU。
    On any detection failure, conservatively fall back to CPU.
    """
    try:
        system = platform.system()
        if system == 'Darwin':
            if torch.backends.mps.is_available():
                return torch.device('mps')
            return torch.device('cpu')

        if torch.cuda.is_available():
            return torch.device('cuda')
        return torch.device('cpu')
    except Exception:
        return torch.device('cpu')


# 全局配置实例，供多数模块直接 import 使用。
# Global configuration instance intended for direct import by most modules.
config = Config()
