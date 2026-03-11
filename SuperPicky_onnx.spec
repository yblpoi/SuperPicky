import os
import site
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
import sys
sys.path.append(os.path.abspath('.'))
from constants import APP_VERSION

# 获取当前工作目录
base_path = os.path.abspath('.')

# 动态获取 site-packages 路径
sp = site.getsitepackages()
site_packages = sp[1] if len(sp) > 1 else sp[0]

# 动态收集数据文件（ONNX 版本: 不再需要 ultralytics）
imageio_datas = collect_data_files('imageio')
rawpy_datas = collect_data_files('rawpy')
pillow_heif_datas = collect_data_files('pillow_heif')
onnxruntime_datas = collect_data_files('onnxruntime')

# ONNX 模型文件列表（只打包 .onnx，排除 .pth/.pt 节省 ~520MB）
onnx_model_files = [
    'yolo11l-seg.onnx',
    'cfanet_iaa_ava_res50.onnx',
    'cub200_keypoint_resnet50.onnx',
    'superFlier_efficientnet.onnx',
    'model20240824.onnx',           # BirdID OSEA 分类器
]

# 组合所有数据文件
all_datas = [
    # AI模型文件（只打包需要的模型，不打包整个 models/ 目录）
] + [
    (os.path.join(base_path, 'models', f), 'models') for f in onnx_model_files
    if os.path.exists(os.path.join(base_path, 'models', f))
] + [
    # ExifTool 完整打包
    (os.path.join(base_path, 'exiftools_mac'), 'exiftools_mac'),
    # 图片资源
    (os.path.join(base_path, 'img'), 'img'),
    # 国际化语言包
    (os.path.join(base_path, 'locales'), 'locales'),
    # macOS 本地化 (应用名称) - 必须放在 Resources 根目录
    (os.path.join(base_path, 'locales', 'en.lproj'), 'en.lproj'),
    (os.path.join(base_path, 'locales', 'zh-Hans.lproj'), 'zh-Hans.lproj'),
    # V4.0.0: 鸟类识别模块数据
    (os.path.join(base_path, 'birdid/data'), 'birdid/data'),
    # V4.0.0: Lightroom 插件
    (os.path.join(base_path, 'SuperBirdIDPlugin.lrplugin'), 'SuperBirdIDPlugin.lrplugin'),
    # V4.2.x: 鸟名查询数据库 (ioc/birdname.db)
    (os.path.join(base_path, 'ioc'), 'ioc'),
]

# 添加动态收集的数据
all_datas.extend(imageio_datas)
all_datas.extend(rawpy_datas)
all_datas.extend(pillow_heif_datas)
all_datas.extend(onnxruntime_datas)
# 添加包元数据
all_datas.extend(copy_metadata('imageio'))
all_datas.extend(copy_metadata('rawpy'))
all_datas.extend(copy_metadata('pillow_heif'))
all_datas.extend(copy_metadata('onnxruntime'))

a = Analysis(
    ['main.py'],
    pathex=[base_path],
    binaries=[],
    datas=all_datas,
    hiddenimports=[
        # ONNX Runtime (替代 torch + ultralytics)
        'onnxruntime',
        'PIL',
        'cv2',
        'numpy',
        'yaml',
        'matplotlib',
        'matplotlib.pyplot',
        'matplotlib.backends.backend_agg',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'timm',
        'timm.models',
        'timm.models.resnet',
        'imageio',
        'rawpy',
        'imagehash',
        'pywt',
        'pillow_heif',   # HEIF/HIF 支持
        'core',
        'core.burst_detector',
        'core.config_manager',
        'core.exposure_detector',
        'core.file_manager',
        'core.flight_detector_onnx',
        'core.focus_point_detector',
        'core.keypoint_detector_onnx',
        'core.photo_processor',
        'core.rating_engine',
        'core.stats_formatter',
        'multiprocessing',
        'multiprocessing.spawn',
        # V3.9.5: 更新检测模块
        'update_checker',
        'packaging',
        'packaging.version',
        # V4.0.0: 鸟类识别模块 (ONNX)
        'birdid',
        'birdid.bird_identifier_onnx',
        'birdid.ebird_country_filter',
        'birdid_server',
        'server_manager',
        'flask',
        'flask.json',
        'cryptography',
        'cryptography.fernet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_cv2.py'] if os.path.exists('pyi_rth_cv2.py') else [],
    excludes=[
        'PyQt5', 'PyQt6', 'tkinter',
        # ONNX 版本: 排除 PyTorch 和 ultralytics
        'torch', 'torchvision', 'torchaudio',
        'ultralytics',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuperPicky',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns') if os.path.exists(os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuperPicky',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='SuperPicky.app',
    icon=os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns') if os.path.exists(os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns')) else None,
    bundle_identifier='com.jamesphotography.superpicky',
    info_plist={
        'CFBundleName': 'SuperPicky',
        'CFBundleDisplayName': 'SuperPicky',
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': '慧眼选鸟需要发送 AppleEvents 与其他应用通信。',
        'NSAppleScriptEnabled': False,
    },
)
