"""
SuperPicky BirdID 模块
鸟类识别核心功能
"""

from birdid.bird_identifier import (
    identify_bird,
    quick_identify,
    predict_bird,
    load_image,
    extract_gps_from_exif,
    get_classifier,
    get_database_manager,
    get_yolo_detector,
    YOLOBirdDetector,
    YOLO_AVAILABLE,
    RAW_SUPPORT
)

__version__ = "1.0.0"
__all__ = [
    'identify_bird',
    'quick_identify',
    'predict_bird',
    'load_image',
    'extract_gps_from_exif',
    'get_classifier',
    'get_database_manager',
    'get_yolo_detector',
    'YOLOBirdDetector',
    'YOLO_AVAILABLE',
    'RAW_SUPPORT'
]
