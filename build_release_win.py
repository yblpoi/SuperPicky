#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SuperPicky 构建脚本

此脚本整合了原始批处理文件的构建功能：
- build_release_cpu_onnx.bat
- build_release_cpu.bat
- build_release_cuda.bat
- build_release.bat

使用方法：
    python build.py [选项]

选项：
    --build-type TYPE      构建类型：cpu, cuda, onnx, all (默认: cpu)
    --version VERSION      构建的基础版本号 (例如: 4.0.6)
    --copy-dir DIR     复制构建文件和压缩包的目标目录
    --no-zip           跳过创建压缩包
    --debug            调试模式
    --help            显示此帮助信息并退出
"""


import os
import sys
import argparse
import subprocess
import shutil
import tempfile
import logging
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = False

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(formatter)

# Clear existing handlers and add our console handler
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)
logger.addHandler(console_handler)

# Constants
APP_NAME = "SuperPicky"
ROOT_DIR = Path(__file__).parent.resolve()
INNO_DIR = ROOT_DIR / "inno"
BUILD_INFO_FILE = ROOT_DIR / "core" / "build_info.py"
DOWNLOAD_MODELS_SCRIPT = ROOT_DIR / "scripts" / "download_models.py"

# Load required models from download_models.py to ensure synchronization
def load_required_models():
    """
    Loads the list of required models from download_models.py to ensure synchronization.
    Falls back to a default list if download_models.py is not available.
    
    Returns:
        list: List of model dictionaries containing "filename" and "dest_dir"
    """
    try:
        # Add scripts directory to path for import
        scripts_dir = str(ROOT_DIR / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        
        from download_models import MODELS_TO_DOWNLOAD
        
        # Extract only the required fields for our build script
        required_models = []
        for model in MODELS_TO_DOWNLOAD:
            required_models.append({
                "filename": model["filename"],
                "dest_dir": model["dest_dir"]
            })
        
        logger.info("[成功] 已从 download_models.py 加载模型列表")
        return required_models
    except Exception as e:
        logger.warning(f"[警告] 无法从 download_models.py 加载模型列表: {e}")
        logger.warning("[警告] 将使用默认模型列表")
        
        # Fallback to default list in case of failure
        return [
            {
                "filename": "avonet.db",
                "dest_dir": "birdid/data",
            },
            {
                "filename": "yolo11l-seg.onnx",
                "dest_dir": "models",
            },
            {
                "filename": "cfanet_iaa_ava_res50.onnx",
                "dest_dir": "models",
            },
            {
                "filename": "cub200_keypoint_resnet50.onnx",
                "dest_dir": "models",
            },
            {
                "filename": "superFlier_efficientnet.onnx",
                "dest_dir": "models",
            },
            {
                "filename": "model20240824.onnx",
                "dest_dir": "models",
            },
        ]

# Load models at module initialization time
REQUIRED_MODELS = load_required_models()


class BuildConfig:
    """构建配置类
    
    此类用于存储构建配置信息，根据构建类型设置相应的参数。
    
    属性:
        build_type: str，构建类型（cpu, cuda, onnx, all）
        version: str，构建版本号
        copy_dir: str，复制构建文件和压缩包的目标目录
        no_zip: bool，是否跳过创建压缩包
        debug: bool，是否启用调试模式
        spec_file: str，PyInstaller spec文件路径
        dist_dir: str，分发目录
        build_suffix: str，构建后缀
        work_dir: str，工作目录
        output_exe_dir: Path，输出可执行文件目录
    """
    def __init__(self, build_type, version, copy_dir, no_zip, debug):
        self.build_type = build_type
        self.version = version
        self.copy_dir = copy_dir
        self.no_zip = no_zip
        self.debug = debug
        
        # 设置构建特定参数
        if build_type == "cpu":
            self.spec_file = "SuperPicky_win64.spec"
            self.dist_dir = "dist_cpu"
            self.build_suffix = "Win64_CPU"
        elif build_type == "cuda":
            self.spec_file = "SuperPicky_win64.spec"
            self.dist_dir = "dist_cuda"
            self.build_suffix = "_Win64_CUDA"
        elif build_type == "onnx":
            self.spec_file = "SuperPicky_win64_onnx.spec"
            self.dist_dir = "dist_cpu_onnx"
            self.build_suffix = "_Win64_CPU_ONNX"
        else:
            raise ValueError(f"无效的构建类型: {build_type}")
        
        self.work_dir = f"build_{self.dist_dir}"
        self.output_exe_dir = ROOT_DIR / self.dist_dir / APP_NAME

def parse_args(args=None):
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="SuperPicky 构建脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--build-type",
        choices=["cpu", "cuda", "onnx"],
        default="cpu",
        help="构建类型：cpu, cuda, onnx (默认: cpu)"
    )
    parser.add_argument(
        "--version",
        help="构建的基础版本号 (例如: 4.0.6)"
    )
    parser.add_argument(
        "--copy-dir",
        help="复制构建文件和压缩包的目标目录"
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="跳过创建压缩包"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式，输出详细的调试信息"
    )
    return parser.parse_args(args)

def clean_old_build_files(config):
    """清理旧的构建文件
    
    此函数会删除之前构建过程中生成的所有目录，包括：
    - 各种构建目录 (build_dist, build_dist_cpu, build_dist_cuda)
    - 各种分发目录 (dist, dist_cpu, dist_cuda)
    - 输出目录 (output)
    - 当前构建配置对应的工作目录和分发目录
    - 如果指定了copy_dir，也会清理该目录
    
    参数:
        config: BuildConfig对象，包含构建配置信息
    """
    logger.info("[========================================]")
    logger.info("步骤 1: 清理旧的构建文件")
    logger.info("[========================================]")
    
    if config.debug:
        logger.debug(f"清理配置: {config.__dict__}")
    
    # 要清理的目录列表
    directories_to_clean = [
        ROOT_DIR / "build_dist",
        ROOT_DIR / "build_dist_cpu",
        ROOT_DIR / "build_dist_cuda",
        ROOT_DIR / "dist",
        ROOT_DIR / "dist_cpu",
        ROOT_DIR / "dist_cuda",
        ROOT_DIR / config.work_dir,
        ROOT_DIR / config.dist_dir
    ]
    
    if config.debug:
        logger.debug(f"要清理的目录列表: {directories_to_clean}")
    
    for dir_path in directories_to_clean:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                logger.info(f"已清理: {dir_path}")
            except Exception as e:
                logger.warning(f"清理 {dir_path} 失败: {e}")
    
    # # 如果指定了copy_dir，也清理该目录
    # # 注意：这会删除所有包含构建版本号的子目录
    # # 请确保copy_dir是一个安全的目录，避免删除 unintended 目录
    # # 不要设置为项目根目录或重要系统目录
    # # 例如：C:\Windows、C:\Program Files 等
    # # 安全起见，我还是注释了这一功能

    # if config.copy_dir:
    #     zip_copy_path = Path(config.copy_dir)
    #     if config.debug:
    #         logger.debug(f"清理copy_dir: {zip_copy_path}")
    #     if zip_copy_path.exists():
    #         try:
    #             shutil.rmtree(zip_copy_path)
    #             logger.info(f"已清理: {zip_copy_path}")
    #         except Exception as e:
    #             logger.warning(f"清理 {zip_copy_path} 失败: {e}")
    
    logger.info("[成功] 已清理旧的构建文件")

def check_model_files():
    """检查所需模型文件是否完整
    
    此函数会检查所有必要的模型文件是否已下载并存在于正确位置。
    
    返回:
        tuple: (bool, list) - 是否完整，缺失文件列表
    """
    missing_files = []
    
    for model in REQUIRED_MODELS:
        model_path = ROOT_DIR / model["dest_dir"] / model["filename"]
        if not model_path.exists():
            missing_files.append(str(model_path))
            logger.debug(f"缺失模型文件: {model_path}")
    
    return len(missing_files) == 0, missing_files


def download_models_with_retry(max_retries=3):
    """下载模型文件，支持重试机制
    
    参数:
        max_retries: 最大重试次数
        
    返回:
        bool: 是否下载成功
    """
    if not DOWNLOAD_MODELS_SCRIPT.exists():
        logger.error(f"下载脚本不存在: {DOWNLOAD_MODELS_SCRIPT}")
        return False
    
    python_exe = sys.executable
    
    for attempt in range(1, max_retries + 1):
        logger.info(f"[信息] 尝试下载模型 (第 {attempt}/{max_retries} 次)...")
        
        try:
            result = subprocess.run(
                [python_exe, str(DOWNLOAD_MODELS_SCRIPT)],
                check=True,
                cwd=str(ROOT_DIR),
                text=True
            )
            
            if result.returncode == 0:
                logger.info("[成功] 模型下载完成")
                return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"模型下载失败 (尝试 {attempt}): {e}")
            if attempt < max_retries:
                logger.info(f"[信息] 将在 5 秒后重试...")
                import time
                time.sleep(5)
    
    logger.error(f"[错误] 模型下载失败，已尝试 {max_retries} 次")
    return False


def check_and_download_models():
    """检查并下载所需的模型文件
    
    此函数会:
    1. 检查模型文件是否存在
    2. 如果缺失，调用下载脚本
    3. 下载完成后重新验证
    
    异常:
        如果下载或验证失败，会退出程序
    """
    logger.info("[========================================]")
    logger.info("步骤 0: 检查并下载模型文件")
    logger.info("[========================================]")
    
    # 首先检查模型文件
    logger.info("[信息] 正在检查模型文件完整性...")
    is_complete, missing_files = check_model_files()
    
    if is_complete:
        logger.info("[成功] 所有模型文件已就绪")
        return
    
    # 模型文件不完整，需要下载
    logger.warning(f"[警告] 缺失 {len(missing_files)} 个模型文件")
    logger.info("[信息] 开始下载模型...")
    
    # 下载模型
    if not download_models_with_retry():
        logger.error("[错误] 无法完成模型下载，构建终止")
        sys.exit(1)
    
    # 下载完成后重新检查
    logger.info("[信息] 重新验证模型文件完整性...")
    is_complete, missing_files = check_model_files()
    
    if not is_complete:
        logger.error(f"[错误] 仍有 {len(missing_files)} 个模型文件缺失")
        for file in missing_files:
            logger.error(f"  - {file}")
        logger.error("[错误] 构建终止")
        sys.exit(1)
    
    logger.info("[成功] 所有模型文件已就绪")


def check_environment(config):
    """检查构建环境
    
    此函数会检查构建所需的环境条件：
    - 检查指定的spec文件是否存在
    - 检查Python是否可用
    - 检查PyInstaller是否已安装
    
    参数:
        config: BuildConfig对象，包含构建配置信息
    
    异常:
        如果环境检查失败，尝试修复环境
    """
    logger.info("[========================================]")
    logger.info("步骤 2: 检查环境")
    logger.info("[========================================]")
    if config.debug:
        logger.debug(f"检查环境配置: {config.__dict__}")
    
    # 检查spec文件
    spec_file_path = ROOT_DIR / config.spec_file
    if config.debug:
        logger.debug(f"检查spec文件: {spec_file_path}")
    if not spec_file_path.exists():
        logger.error(f"缺少spec文件: {config.spec_file}")
        sys.exit(1)
    logger.info(f"[成功] 找到spec文件: {config.spec_file}")
    
    # 检查Python
    python_exe = sys.executable
    logger.info(f"[信息] 检查Python: {python_exe}")
    if config.debug:
        logger.debug(f"Python可执行文件: {python_exe}")
    
    # 检查PyInstaller
    try:
        if config.debug:
            logger.debug("检查PyInstaller是否已安装")
        result = subprocess.run(
            [python_exe, "-c", "import PyInstaller"],
            check=True,
            capture_output=True,
            text=True
        )
        if config.debug:
            logger.debug(f"PyInstaller检查结果: {result.returncode}")
        logger.info("[成功] PyInstaller 可用")
    except subprocess.CalledProcessError:
        logger.error("环境中缺少PyInstaller，尝试修复...")
        try:
            if config.debug:
                logger.debug("尝试安装PyInstaller和lap")
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "pyinstaller", "lap"],
                check=True,
                capture_output=True,
                text=True
            )
            if config.debug:
                logger.debug(f"PyInstaller安装结果: {result.returncode}")
                logger.debug(f"安装输出: {result.stdout}")
            logger.info("[成功] 已安装PyInstaller")
        except subprocess.CalledProcessError as e:
            logger.error(f"安装PyInstaller失败: {e}")
            if config.debug:
                logger.debug(f"安装错误: {e}")
            sys.exit(1)

def resolve_version(config):
    """解析构建版本
    
    此函数会解析并生成最终的构建版本号：
     - 默认使用constants.py中的APP_VERSION
     - 如果指定了版本号，使用该版本号
     - 如果指定了构建类型，添加相应的后缀
     - 如果未指定构建类型，默认使用onnx后缀
    
    参数:
        config: BuildConfig对象，包含构建配置信息
    
    返回:
        str: 最终的构建版本号
    """
    logger.info("[========================================]")
    logger.info("步骤 3: 解析版本")
    logger.info("[========================================]")
    
    if config.debug:
        logger.debug(f"解析版本配置: {config.__dict__}")
    
    if config.version:
        version_base = config.version
        logger.info(f"[成功] 使用命令行参数中的基础版本: {version_base}")
        if config.debug:
            logger.debug(f"使用命令行指定的版本: {version_base}")
    else:
        # 从constants.py读取APP_VERSION
        try:
            constants_path = ROOT_DIR / "constants.py"
            if config.debug:
                logger.debug(f"从constants.py读取版本: {constants_path}")
            with open(constants_path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            match = re.search(r'APP_VERSION\s*=\s*["\']([0-9A-Za-z._-]+)["\']', content)
            if match:
                version_base = match.group(1)
                logger.info(f"[成功] 从constants.py获取版本: {version_base}")
                if config.debug:
                    logger.debug(f"从constants.py获取的版本: {version_base}")
            else:
                version_base = "0.0.0"
                logger.warning("未能从constants.py检测到APP_VERSION，使用0.0.0")
                if config.debug:
                    logger.debug("未能从constants.py检测到APP_VERSION")
        except Exception as e:
            version_base = "0.0.0"
            logger.warning(f"读取constants.py失败: {e}，使用0.0.0")
            if config.debug:
                logger.debug(f"读取constants.py失败: {e}")
    
    # 确定构建后缀
    build_suffix = config.build_suffix if config.build_type else "_Win64_CPU_ONNX"
    if config.debug:
        logger.debug(f"构建后缀: {build_suffix}")
    
    # 组合最终版本
    if not version_base.endswith(build_suffix):
        version = f"{version_base}{build_suffix}"
    else:
        version = version_base
    
    logger.info(f"[成功] 最终包版本: {version}")
    if config.debug:
        logger.debug(f"最终构建版本: {version}")
    return version

def inject_build_metadata():
    """注入构建元数据
    
    此函数会注入构建元数据，主要是提交哈希值：
    - 首先尝试从core.build_info_local或core.build_info模块读取COMMIT_HASH
    - 如果读取失败，尝试通过git命令获取当前提交的短哈希值
    - 备份build_info.py文件
    - 更新build_info.py文件中的COMMIT_HASH值
    
    返回:
        Path: 备份文件的路径
    
    异常:
        如果注入失败，会恢复备份并退出程序
    """
    logger.info("[========================================]")
    logger.info("步骤 4: 注入构建元数据")
    logger.info("[========================================]")
    
    # 备份build_info.py
    build_info_backup = BUILD_INFO_FILE.with_suffix(".py.backup")
    if BUILD_INFO_FILE.exists():
        logger.debug(f"备份build_info.py到: {build_info_backup}")
        shutil.copy2(BUILD_INFO_FILE, build_info_backup)
    
    # 使用update_build_info更新构建信息
    try:
        if update_build_info():
            logger.info("[成功] 已注入构建信息")
            return build_info_backup
        else:
            logger.error("注入构建信息失败")
            if build_info_backup.exists():
                logger.debug(f"恢复build_info.py从备份: {build_info_backup}")
                shutil.copy2(build_info_backup, BUILD_INFO_FILE)
            sys.exit(1)
    except Exception as e:
        logger.error(f"注入构建信息失败: {e}")
        logger.debug(f"注入构建信息异常: {e}")
        if build_info_backup.exists():
            logger.debug(f"恢复build_info.py从备份: {build_info_backup}")
            shutil.copy2(build_info_backup, BUILD_INFO_FILE)
        sys.exit(1)

def restore_build_info(backup_path):
    """从备份恢复构建信息
    
    此函数会从备份文件恢复build_info.py文件：
    - 如果备份文件存在，将其复制回build_info.py
    - 如果恢复失败，记录警告信息
    
    参数:
        backup_path: Path，备份文件的路径
    """
    if backup_path and backup_path.exists():
        try:
            logger.debug(f"从备份恢复构建信息: {backup_path}")
            shutil.copy2(backup_path, BUILD_INFO_FILE)
            logger.debug("构建信息恢复成功")
        except Exception as e:
            logger.warning(f"恢复构建信息失败: {e}")
            logger.debug(f"恢复构建信息异常: {e}")

def build_with_python(config, python_exe):
    """使用PyInstaller构建应用
    
    此函数会使用PyInstaller构建应用：
    - 清理工作目录和分发目录
    - 运行PyInstaller命令构建应用
    - 检查构建结果，确保可执行文件已生成
    
    参数:
        config: BuildConfig对象，包含构建配置信息
        python_exe: str，Python可执行文件的路径
    
    异常:
        如果构建失败，会退出程序
    """
    logger.info(f"构建: {config.build_type}")
    if config.debug:
        logger.debug(f"构建配置: {config.__dict__}")
        logger.debug(f"Python可执行文件: {python_exe}")
    
    work_dir = ROOT_DIR / config.work_dir
    dist_dir = ROOT_DIR / config.dist_dir
    spec_file = ROOT_DIR / config.spec_file
    
    if config.debug:
        logger.debug(f"工作目录: {work_dir}")
        logger.debug(f"分发目录: {dist_dir}")
        logger.debug(f"Spec文件: {spec_file}")
    
    # 清理目录
    if work_dir.exists():
        if config.debug:
            logger.debug(f"清理工作目录: {work_dir}")
        shutil.rmtree(work_dir)
    if dist_dir.exists():
        if config.debug:
            logger.debug(f"清理分发目录: {dist_dir}")
        shutil.rmtree(dist_dir)
    
    # 运行PyInstaller
    try:
        pyinstaller_cmd = [
            python_exe,
            "-m", "PyInstaller",
            str(spec_file),
            "--clean",
            "--noconfirm",
            f"--workpath={work_dir}",
            f"--distpath={dist_dir}"
        ]
        if config.debug:
            logger.debug(f"运行PyInstaller命令: {' '.join(pyinstaller_cmd)}")
        
        result = subprocess.run(
            pyinstaller_cmd,
            capture_output=True,
            text=True
        )
        
        logger.info(f"[信息] PyInstaller 进程返回码: {result.returncode}")
        if config.debug:
            logger.debug(f"PyInstaller 标准输出: {result.stdout}")
            logger.debug(f"PyInstaller 标准错误: {result.stderr}")
        
        if result.returncode != 0:
            logger.warning(f"PyInstaller 返回非零值: {result.returncode}")
        
        # 检查可执行文件是否生成
        exe_path = dist_dir / APP_NAME / f"{APP_NAME}.exe"
        if config.debug:
            logger.debug(f"检查可执行文件: {exe_path}")
        if not exe_path.exists():
            logger.error(f"缺少输出可执行文件: {exe_path}")
            sys.exit(1)
        
        logger.info(f"[成功] 构建完成 ({config.build_type})")
        if config.debug:
            logger.debug(f"构建完成，可执行文件: {exe_path}")
    except Exception as e:
        logger.error(f"构建失败: {e}")
        if config.debug:
            logger.debug(f"构建异常: {e}")
        sys.exit(1)

def zip_dir(src_dir, out_file):
    """从目录创建压缩文件
    
    此函数会从指定目录创建压缩文件：
    - 检查源目录是否存在
    - 删除已存在的压缩文件
    - 尝试使用7z命令创建压缩文件
    - 如果7z不可用，使用Python的zipfile模块创建压缩文件
    
    参数:
        src_dir: Path，源目录路径
        out_file: Path，输出压缩文件路径
    
    返回:
        bool: 创建成功返回True，失败返回False
    """
    if not src_dir.exists():
        logger.error(f"压缩源目录不存在: {src_dir}")
        return False
    
    logger.debug(f"创建压缩文件: 源目录={src_dir}, 输出文件={out_file}")
    
    # 删除已存在的压缩文件
    if out_file.exists():
        try:
            logger.debug(f"删除已存在的压缩文件: {out_file}")
            out_file.unlink()
        except Exception as e:
            logger.warning(f"删除已存在的压缩文件失败: {e}")
            logger.debug(f"删除压缩文件异常: {e}")
    
    # 尝试使用7z（如果可用）
    try:
        seven_zip_cmd = ["7z", "a", "-tzip", str(out_file), str(src_dir), "-r"]
        logger.debug(f"尝试使用7z命令: {' '.join(seven_zip_cmd)}")
        result = subprocess.run(
            seven_zip_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug(f"7z命令返回码: {result.returncode}")
        logger.debug(f"7z命令输出: {result.stdout}")
        logger.info(f"[成功] 创建压缩文件: {out_file}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.debug(f"7z不可用，回退到Python的zipfile模块: {e}")
        # 回退到Python的zipfile模块
        try:
            import zipfile
            import glob
            
            logger.debug(f"使用Python的zipfile模块创建压缩文件")
            with zipfile.ZipFile(out_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(src_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, src_dir.parent)
                        zipf.write(file_path, arcname)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"添加文件到压缩包: {arcname}")
            logger.info(f"[成功] 创建压缩文件: {out_file}")
            return True
        except Exception as e:
            logger.error(f"创建压缩文件失败: {e}")
            logger.debug(f"创建压缩文件异常: {e}")
            return False

def copy_dir(src_dir, dst_dir):
    """复制目录
    
    此函数会复制指定目录到目标位置：
    - 检查源目录是否存在
    - 如果目标目录不存在，创建它
    - 使用shutil.copytree复制目录及其内容
    
    参数:
        src_dir: Path，源目录路径
        dst_dir: Path，目标目录路径
    
    返回:
        bool: 复制成功返回True，失败返回False
    """
    if not src_dir.exists():
        logger.error(f"复制源目录不存在: {src_dir}")
        return False
    
    logger.debug(f"复制目录: 源={src_dir}, 目标={dst_dir}")
    
    if not dst_dir.exists():
        try:
            logger.debug(f"创建目标目录: {dst_dir}")
            dst_dir.mkdir(parents=True)
        except Exception as e:
            logger.error(f"创建目标目录失败: {e}")
            logger.debug(f"创建目标目录异常: {e}")
            return False
    
    try:
        logger.debug(f"开始复制目录内容")
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        logger.info(f"[成功] 复制目录: {src_dir} -> {dst_dir}")
        return True
    except Exception as e:
        logger.error(f"复制到 {dst_dir} 失败: {e}")
        logger.debug(f"复制目录异常: {e}")
        return False

def copy_file(src_file, dst_file):
    """复制文件
    
    此函数会复制指定文件到目标位置：
    - 检查源文件是否存在
    - 如果目标目录不存在，创建它
    - 使用shutil.copy2复制文件
    
    参数:
        src_file: Path，源文件路径
        dst_file: Path，目标文件路径
    
    返回:
        bool: 复制成功返回True，失败返回False
    """
    if not src_file.exists():
        logger.error(f"复制源文件不存在: {src_file}")
        return False
    
    logger.debug(f"复制文件: 源={src_file}, 目标={dst_file}")
    
    # 确保目标目录存在
    dst_dir = dst_file.parent
    if not dst_dir.exists():
        try:
            logger.debug(f"创建目标目录: {dst_dir}")
            dst_dir.mkdir(parents=True)
        except Exception as e:
            logger.error(f"创建目标目录失败: {e}")
            logger.debug(f"创建目标目录异常: {e}")
            return False
    
    try:
        logger.debug(f"开始复制文件")
        shutil.copy2(src_file, dst_file)
        logger.info(f"[成功] 复制文件: {src_file} -> {dst_file}")
        return True
    except Exception as e:
        logger.error(f"复制文件到 {dst_file} 失败: {e}")
        logger.debug(f"复制文件异常: {e}")
        return False

def get_commit_hash():
    """
    从 Python 代码读取 COMMIT_HASH（保证跨平台一致）
    优先读 build_info_local.py，其次 build_info.py，最后 fallback 到 git
    
    Returns:
        str: commit hash
    """
    # 优先从 Python 代码读取（保证跨平台一致）
    try:
        sys.path.insert(0, str(ROOT_DIR))
        try:
            from core.build_info_local import COMMIT_HASH
            if COMMIT_HASH:
                logger.info(f"使用 build_info_local.py 中的 COMMIT_HASH: {COMMIT_HASH}")
                return COMMIT_HASH
        except ImportError:
            pass
        from core.build_info import COMMIT_HASH as default_hash
        if default_hash:
            logger.info(f"使用 build_info.py 中的 COMMIT_HASH: {default_hash}")
            return default_hash
    except Exception as e:
        logger.warning(f"警告: 无法从 build_info 读取: {e}")
    
    # Fallback: git
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short=7', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def read_app_version():
    """
    从 constants.py 读取 APP_VERSION
    
    Returns:
        str: 应用版本
    """
    constants_path = ROOT_DIR / 'constants.py'
    
    try:
        with open(constants_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('APP_VERSION ='):
                    # 提取版本，处理引号
                    version = line.split('=', 1)[1].strip()
                    if version.startswith('"') and version.endswith('"'):
                        return version[1:-1]
                    elif version.startswith("'") and version.endswith("'"):
                        return version[1:-1]
                    return version
        logger.warning("未找到 APP_VERSION")
        return "0.0.0"
    except Exception as e:
        logger.warning(f"读取 constants.py 失败: {e}")
        return "0.0.0"


def update_build_info():
    """
    更新 core/build_info.py 中的 COMMIT_HASH
    """
    # 获取提交哈希
    commit_hash = get_commit_hash()
    logger.info(f"正在更新 build_info.py，提交哈希: {commit_hash}")
    
    # 定位 build_info.py
    build_info_path = ROOT_DIR / 'core' / 'build_info.py'
    
    try:
        # 读取文件内容
        with open(build_info_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 替换 COMMIT_HASH
        import re
        updated_content = re.sub(
            r'COMMIT_HASH\s*=\s*.*',
            f'COMMIT_HASH = "{commit_hash}"',
            content
        )
        
        # 写回文件
        with open(build_info_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        logger.info(f"成功更新 {build_info_path}")
        return True
    except Exception as e:
        logger.error(f"更新 {build_info_path} 失败: {e}")
        return False


def update_inno_version(config):
    """
    更新 inno/SuperPicky.iss 中的 AppVersion
    """
    # 获取版本和哈希
    app_version = read_app_version()
    commit_hash = get_commit_hash()
    
    # 组合版本字符串
    new_version = f"{app_version}-{commit_hash}"
    logger.info(f"正在更新版本为: {new_version}")
    
    # 定位 inno 文件
    inno_paths = [
        config.output_exe_dir / 'SuperPicky.iss',
    ]
    
    success = True
    for inno_path in inno_paths:
        if not inno_path.exists():
            logger.warning(f"跳过 {inno_path} - 文件未找到")
            continue
            
        try:
            # 读取文件内容
            with open(inno_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换 AppVersion
            import re
            updated_content = re.sub(
                r'AppVersion=.+',
                f'AppVersion={new_version}',
                content
            )
            
            # 替换 OutputBaseFilename
            build_type_suffix = config.build_type
            updated_content = re.sub(
                r'OutputBaseFilename=SuperPicky_Setup_Win64.*',
                f'OutputBaseFilename=SuperPicky_Setup_Win64_{app_version}_{commit_hash}_{build_type_suffix}',
                updated_content
            )
            
            # 写回文件
            with open(inno_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            logger.info(f"成功更新 {inno_path}")
        except Exception as e:
            logger.error(f"更新 {inno_path} 失败: {e}")
            success = False
    
    return success


def copy_inno_files(config, version):
    """复制Inno Setup文件
    
    此函数会复制Inno Setup相关文件到输出目录：
    - 检查Inno目录是否存在
    - 复制SuperPicky.iss文件，并更新其中的版本信息
    - 复制ChineseSimplified.isl文件
    
    参数:
        config: BuildConfig对象，包含构建配置信息
        version: str，构建版本号
    """
    if config.debug:
        logger.debug(f"复制Inno Setup文件配置: {config.__dict__}")
        logger.debug(f"版本: {version}")
    
    if not INNO_DIR.exists():
        logger.warning(f"Inno目录不存在: {INNO_DIR}")
        return
    
    # 复制SuperPicky.iss
    iss_file = INNO_DIR / "SuperPicky.iss"
    if iss_file.exists():
        try:
            if config.debug:
                logger.debug(f"复制SuperPicky.iss: {iss_file} -> {config.output_exe_dir}")
            shutil.copy2(iss_file, config.output_exe_dir)
            logger.info(f"[成功] 复制SuperPicky.iss到 {config.output_exe_dir}")
            
            # 更新iss文件中的版本信息
            iss_path = config.output_exe_dir / "SuperPicky.iss"
            if config.debug:
                logger.debug(f"更新iss文件中的版本信息: {iss_path}")
            with open(iss_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            import re
            new_content = re.sub(
                r'VersionInfoVersion=.*',
                f'VersionInfoVersion={version}',
                content
            )
            
            with open(iss_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info(f"[成功] 更新SuperPicky.iss中的版本为 {version}")
            if config.debug:
                logger.debug(f"已更新SuperPicky.iss中的版本为 {version}")
        except Exception as e:
            logger.error(f"复制SuperPicky.iss失败: {e}")
            if config.debug:
                logger.debug(f"复制SuperPicky.iss异常: {e}")
    else:
        logger.warning(f"SuperPicky.iss在 {INNO_DIR} 中不存在")
    
    # 复制ChineseSimplified.isl
    isl_file = INNO_DIR / "ChineseSimplified.isl"
    if isl_file.exists():
        try:
            if config.debug:
                logger.debug(f"复制ChineseSimplified.isl: {isl_file} -> {config.output_exe_dir}")
            shutil.copy2(isl_file, config.output_exe_dir)
            logger.info(f"[成功] 复制ChineseSimplified.isl到 {config.output_exe_dir}")
        except Exception as e:
            logger.error(f"复制ChineseSimplified.isl失败: {e}")
            if config.debug:
                logger.debug(f"复制ChineseSimplified.isl异常: {e}")
    else:
        logger.warning(f"ChineseSimplified.isl在 {INNO_DIR} 中不存在")

def build_single(config):
    """构建单个版本
    
    此函数会构建单个版本的应用：
    - 使用PyInstaller构建应用
    - 如果未跳过压缩，创建压缩文件
    - 复制Inno Setup文件到输出目录
    - 如果指定了copy_dir，复制构建文件和压缩文件到该目录
    - 显示构建结果信息
    
    参数:
        config: BuildConfig对象，包含构建配置信息
    
    异常:
        如果构建过程中出现错误，会退出程序
    """    
    python_exe = sys.executable
    if config.debug:
        logger.debug(f"构建单个版本配置: {config.__dict__}")
        logger.debug(f"Python可执行文件: {python_exe}")
    
    # 1. 首先执行打包操作
    logger.info("[========================================]")
    logger.info("步骤 6: 执行打包操作")
    logger.info("[========================================]")
    
    build_with_python(config, python_exe)
    
    # 2. 如果未跳过压缩，先创建压缩文件
    app_version = read_app_version()
    commit_hash = get_commit_hash()
    version = resolve_version(config)
    build_type_suffix = config.build_type

    if not config.no_zip:
        logger.info("[========================================]")
        logger.info("步骤 7: 创建压缩文件")
        logger.info("[========================================]")
        
        # 按照用户要求的格式命名压缩文件

        zip_name = f"{APP_NAME}_Win64_{app_version}_{commit_hash}_{build_type_suffix}.zip"
        zip_path = ROOT_DIR / config.dist_dir / zip_name
        if config.debug:
            logger.debug(f"创建压缩文件: {zip_path}")
        
        # 创建压缩文件
        if config.debug:
            logger.debug(f"开始创建压缩文件: {config.output_exe_dir} -> {zip_path}")
        if not zip_dir(config.output_exe_dir, zip_path):
            sys.exit(1)
    else:
        logger.info("[信息] 跳过创建压缩文件 (--no-zip)")
    
    # 3. 复制Inno Setup文件到exe目录
    logger.info("[========================================]")
    logger.info("步骤 8: 复制Inno Setup文件")
    logger.info("[========================================]")
    
    copy_inno_files(config, version)
    
    # 更新打包后临时目录中的iss文件
    logger.info("[========================================]")
    logger.info("步骤 9: 更新打包后临时目录中的iss文件")
    logger.info("[========================================]")
    
    update_inno_version(config)
    
    # 4. 如果指定了copy_dir，复制到该目录
    if config.copy_dir:
        logger.info("[========================================]")
        logger.info("步骤 10: 复制到copy_dir")
        logger.info("[========================================]")
        
        zip_copy_path = Path(config.copy_dir)
        if config.debug:
            logger.debug(f"复制到copy_dir: {zip_copy_path}")
        
        # 创建copy_dir目录
        if not zip_copy_path.exists():
            try:
                if config.debug:
                    logger.debug(f"创建复制根目录: {zip_copy_path}")
                zip_copy_path.mkdir(parents=True)
            except Exception as e:
                logger.error(f"创建复制根目录失败: {e}")
                if config.debug:
                    logger.debug(f"创建复制根目录异常: {e}")
                sys.exit(1)
        
        # 目标目录是copy_dir下的SuperPicky文件夹
        target_superpicky_dir = zip_copy_path / APP_NAME
        
        # 清理旧的SuperPicky目录
        if target_superpicky_dir.exists():
            try:
                if config.debug:
                    logger.debug(f"清理旧SuperPicky目录: {target_superpicky_dir}")
                shutil.rmtree(target_superpicky_dir)
            except Exception as e:
                logger.error(f"清理旧SuperPicky目录失败: {e}")
                if config.debug:
                    logger.debug(f"清理旧SuperPicky目录异常: {e}")
                sys.exit(1)
        
        # 复制SuperPicky文件夹到copy_dir
        if config.debug:
            logger.debug(f"复制文件: {config.output_exe_dir} -> {target_superpicky_dir}")
        if not copy_dir(config.output_exe_dir, target_superpicky_dir):
            logger.error(f"复制文件失败: {config.output_exe_dir} -> {target_superpicky_dir}")
            sys.exit(1)
        
        # 如果创建了压缩文件，也复制到copy_dir
        if zip_name and zip_path:
            target_zip_path = zip_copy_path / zip_name
            if config.debug:
                logger.debug(f"复制压缩文件: {zip_path} -> {target_zip_path}")
            if not copy_file(zip_path, target_zip_path):
                logger.error(f"复制压缩文件失败: {zip_path} -> {target_zip_path}")
                sys.exit(1)
        
        logger.info(f"[成功] 复制 {target_superpicky_dir} + {zip_name if zip_name else ''}")
    
    # 最终输出
    logger.info("[========================================]")
    logger.info("构建完成")
    logger.info("[========================================]")
    logger.info(f"可执行文件: {config.output_exe_dir / f'{APP_NAME}.exe'}")
    if zip_name:
        logger.info(f"压缩文件: {zip_path}")
        if config.copy_dir:
            logger.info(f"复制: {config.copy_dir}/{APP_NAME} + {zip_name}")
    else:
        logger.info("压缩文件: (已跳过)")

def main():
    """主函数
    
    此函数是脚本的入口点，执行以下操作：
    - 解析命令行参数
    - 创建构建配置
    - 清理旧的构建文件
    - 检查构建环境
    - 注入构建元数据
    - 根据构建类型执行构建
    - 恢复构建信息
    """
    # 检查是否有任何命令行参数
    if len(sys.argv) == 1:
        # 无参数输入，显示帮助信息
        parse_args(['--help'])
        sys.exit(0)
    
    # 解析命令行参数
    args = parse_args()
    
    # 根据debug参数设置日志级别
    if args.debug:
        # 修改logger和handler的级别为DEBUG
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
            # 修改格式为包含时间戳
            # handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.debug(f"调试模式已启用，命令行参数: {args}")
    
    # 创建构建配置
    config = BuildConfig(
        args.build_type,
        args.version,
        args.copy_dir,
        args.no_zip,
        args.debug
    )
    
    # 检查并下载模型文件
    check_and_download_models()
    
    # 清理旧文件
    clean_old_build_files(config)
    
    # 检查环境
    check_environment(config)
    
    # 注入构建元数据
    backup_path = inject_build_metadata()
    
    try:
        build_single(config)
    finally:
        # 恢复构建信息
        restore_build_info(backup_path)

if __name__ == "__main__":
    main()
