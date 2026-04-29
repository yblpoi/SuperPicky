import os
import site
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
import sys
sys.path.append(os.path.abspath('.'))
from constants import APP_VERSION


def _env_or_none(name):
    value = os.environ.get(name, "").strip()
    return value or None


def _optional_copy_metadata(package_name):
    try:
        return copy_metadata(package_name)
    except Exception:
        return []


APP_VERSION = os.environ.get("SUPERPICKY_APP_VERSION", APP_VERSION)

base_path = os.path.abspath('.')
sp = [p for p in site.getsitepackages() if os.path.isdir(p)]
site_packages = sp[0] if sp else site.getusersitepackages()

ultralytics_base = site_packages
if not os.path.exists(os.path.join(ultralytics_base, 'ultralytics')):
    try:
        import ultralytics
        ultralytics_base = os.path.dirname(os.path.dirname(ultralytics.__file__))
    except ImportError:
        pass

ultralytics_datas = collect_data_files('ultralytics')
imageio_datas = collect_data_files('imageio')
rawpy_datas = collect_data_files('rawpy')
pillow_heif_datas = collect_data_files('pillow_heif')

all_datas = [
    # Lite keeps the AI runtime bundled for startup stability while still
    # allowing the first-run flow to fetch missing resources on demand.
    (os.path.join(base_path, 'exiftools_mac'), 'exiftools_mac'),
    (os.path.join(base_path, 'img'), 'img'),
    (os.path.join(base_path, 'locales'), 'locales'),
    (os.path.join(base_path, 'locales', 'en.lproj'), 'en.lproj'),
    (os.path.join(base_path, 'locales', 'zh-Hans.lproj'), 'zh-Hans.lproj'),
    (os.path.join(base_path, 'models', 'yolo11l-seg.pt'), 'models'),
    (os.path.join(base_path, 'birdid', 'data', 'bird_reference.sqlite'), 'birdid/data'),
    (os.path.join(base_path, 'birdid', 'data', 'ebird_classid_mapping.json'), 'birdid/data'),
    (os.path.join(base_path, 'birdid', 'data', 'ebird_regions.json'), 'birdid/data'),
    (os.path.join(base_path, 'birdid', 'data', 'offline_ebird_data'), 'birdid/data/offline_ebird_data'),
    (os.path.join(ultralytics_base, 'ultralytics/cfg'), 'ultralytics/cfg'),
    (os.path.join(base_path, 'SuperBirdIDPlugin.lrplugin'), 'SuperBirdIDPlugin.lrplugin'),
    (os.path.join(base_path, 'ioc'), 'ioc'),
]

all_datas.extend(ultralytics_datas)
all_datas.extend(imageio_datas)
all_datas.extend(rawpy_datas)
all_datas.extend(pillow_heif_datas)
all_datas.extend(_optional_copy_metadata('imageio'))
all_datas.extend(_optional_copy_metadata('rawpy'))
all_datas.extend(_optional_copy_metadata('ultralytics'))
all_datas.extend(_optional_copy_metadata('pillow_heif'))
all_datas.extend(_optional_copy_metadata('pi_heif'))

app_hiddenimports = [
    'ultralytics',
    'torch',
    'torchvision',
    'torchvision.models',
    'torchvision.transforms',
    'torchvision.transforms.functional',
    'torchaudio',
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
    'pillow_heif',
    'pi_heif',
    'core',
    'core.burst_detector',
    'core.config_manager',
    'core.exposure_detector',
    'core.file_manager',
    'core.flight_detector',
    'core.focus_point_detector',
    'core.initialization_manager',
    'core.keypoint_detector',
    'core.photo_processor',
    'core.rating_engine',
    'core.source_probe',
    'core.stats_formatter',
    'multiprocessing',
    'multiprocessing.spawn',
    'tools.update_checker',
    'packaging',
    'packaging.version',
    'birdid',
    'birdid.bird_identifier',
    'birdid.ebird_country_filter',
    'birdid_server',
    'server_manager',
    'flask',
    'flask.json',
    'cryptography',
    'cryptography.fernet',
    '_telemetry_build',
    'app_user_stat._telemetry_build',
    'app_user_stat',
    'app_user_stat.telemetry',
    'app_user_stat.consent_texts',
    'app_user_stat.consent_texts.en_US',
    'app_user_stat.consent_texts.zh_CN',
]

a = Analysis(
    ['main.py'],
    pathex=[base_path],
    binaries=[],
    datas=all_datas,
    hiddenimports=app_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_cv2.py'] if os.path.exists('pyi_rth_cv2.py') else [],
    excludes=[
        'PyQt5', 'PyQt6', 'tkinter',
        'polars', 'numba', 'llvmlite', 'pyarrow', 'facexlib', 'datasets',
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
    name='SuperPickyLite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_env_or_none("SUPERPICKY_TARGET_ARCH"),
    codesign_identity=_env_or_none("SUPERPICKY_CODESIGN_IDENTITY"),
    entitlements_file=_env_or_none("SUPERPICKY_ENTITLEMENTS_FILE"),
    icon=os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns') if os.path.exists(os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SuperPickyLite',
)

app = BUNDLE(
    coll,
    name='SuperPickyLite.app',
    icon=os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns') if os.path.exists(os.path.join(base_path, 'img', 'SuperPicky-V0.02.icns')) else None,
    bundle_identifier='com.jamesphotography.superpicky.lite',
    info_plist={
        'CFBundleName': 'SuperPickyLite',
        'CFBundleDisplayName': 'SuperPickyLite',
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': '慧眼选鸟需要发送 AppleEvents 与其他应用通信。',
        'NSAppleScriptEnabled': False,
    },
)
