#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
递归目录扫描器
扫描根目录下的所有子目录，识别出包含照片的"原子目录"，
排除星级目录、隐藏目录、连拍目录等 SuperPicky 产物。
"""

import os
import platform
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import List, Optional, Set, Tuple

from constants import RAW_EXTENSIONS, JPG_EXTENSIONS, HEIF_EXTENSIONS, RATING_FOLDER_NAMES, RATING_FOLDER_NAMES_EN

# 所有照片扩展名（小写）
_PHOTO_EXTENSIONS: Set[str] = set(RAW_EXTENSIONS + JPG_EXTENSIONS + HEIF_EXTENSIONS)

# 星级目录名（中 + 英）
_RATING_DIR_NAMES: Set[str] = set(RATING_FOLDER_NAMES.values()) | set(RATING_FOLDER_NAMES_EN.values())

DEFAULT_SCAN_MAX_DEPTH = 16


@dataclass(frozen=True)
class ScannedDirectory:
    """扫描结果条目"""

    path: str
    depth: int
    photo_count: int


def is_excluded(dirname: str) -> bool:
    """判断目录是否应被排除（非用户照片目录）"""
    if dirname.startswith('.'):
        return True
    if dirname.startswith('burst_'):
        return True
    if dirname in _RATING_DIR_NAMES:
        return True
    if dirname in ('__pycache__', 'node_modules'):
        return True
    return False


def _is_nonempty_photo_file(entry: os.DirEntry[str]) -> bool:
    """判断目录项是否为非空照片文件。"""
    ext = os.path.splitext(entry.name)[1].lower()
    if ext not in _PHOTO_EXTENSIONS:
        return False

    try:
        return entry.stat(follow_symlinks=False).st_size > 0
    except OSError:
        return False


def _scan_directory_once(dir_path: str) -> Tuple[int, List[str]]:
    """单次扫描目录，返回直接照片数量与可继续扫描的子目录。"""
    photo_count = 0
    child_dirs: List[str] = []

    try:
        with os.scandir(dir_path) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    if _is_nonempty_photo_file(entry):
                        photo_count += 1
                    continue

                if not entry.is_dir(follow_symlinks=False):
                    continue
                if is_excluded(entry.name):
                    continue

                child_dirs.append(entry.path)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return 0, []

    child_dirs.sort(key=lambda value: os.path.basename(value).casefold())
    return photo_count, child_dirs


def _scan_directories_dfs(root: str, max_depth: int) -> List[ScannedDirectory]:
    root = os.path.abspath(root)
    if max_depth < 0:
        return []

    result: List[ScannedDirectory] = []
    stack: List[Tuple[str, int]] = [(root, 0)]
    while stack:
        dir_path, depth = stack.pop()
        photo_count, child_dirs = _scan_directory_once(dir_path)
        if photo_count > 0:
            result.append(ScannedDirectory(path=dir_path, depth=depth, photo_count=photo_count))
        if depth >= max_depth:
            continue
        for child_dir in reversed(child_dirs):
            stack.append((child_dir, depth + 1))
    result.sort(key=lambda item: item.path.casefold())
    return result


def _is_windows_path(path: str) -> bool:
    drive, _ = os.path.splitdrive(path)
    return bool(drive) or "\\" in path


def _is_subpath(candidate_parts: Tuple[str, ...], protected_parts: Tuple[str, ...]) -> bool:
    if len(candidate_parts) < len(protected_parts):
        return False
    return candidate_parts[:len(protected_parts)] == protected_parts


def is_dangerous_root(
    root: str,
    platform_name: Optional[str] = None,
    home_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    """判断根目录是否属于危险目录。"""
    platform_name = (platform_name or platform.system()).lower()
    home_dir = os.path.expanduser(home_dir or "~")

    if platform_name.startswith("win") or _is_windows_path(root):
        normalized = str(PureWindowsPath(os.path.realpath(os.path.abspath(root))))
        root_path = PureWindowsPath(normalized)
        anchor = root_path.anchor.rstrip("\\/")
        current = normalized.rstrip("\\/")
        if anchor and current.lower() == anchor.lower():
            return True, "磁盘根目录 / Drive root"

        protected_paths = [
            PureWindowsPath(os.path.realpath(os.environ.get("SystemRoot", "C:\\Windows"))),
            PureWindowsPath(os.path.realpath("C:\\Program Files")),
            PureWindowsPath(os.path.realpath("C:\\Program Files (x86)")),
            PureWindowsPath(os.path.realpath(os.path.join(home_dir, "AppData"))),
        ]
        root_parts = tuple(part.casefold() for part in root_path.parts)
        for protected in protected_paths:
            protected_parts = tuple(part.casefold() for part in protected.parts)
            if _is_subpath(root_parts, protected_parts):
                return True, f"受保护的系统或设置目录 / Protected path: {protected}"
        return False, ""

    normalized = str(PurePosixPath(os.path.realpath(os.path.abspath(root))))
    root_path = PurePosixPath(normalized)
    root_parts = tuple(root_path.parts)

    if normalized == "/":
        return True, "文件系统根目录 / Filesystem root"

    _raw_protected = [
        "/usr",
        "/etc",
        "/var",
        "/System",
        "/Library",
        os.path.join(home_dir, "Library"),
    ]
    protected_paths = [
        PurePosixPath(os.path.realpath(p)) for p in _raw_protected
    ]
    for protected in protected_paths:
        protected_parts = tuple(protected.parts)
        if _is_subpath(root_parts, protected_parts):
            return True, f"受保护的系统或设置目录 / Protected path: {protected}"
    if normalized in ("/home", os.path.realpath("/home")):
        return True, "系统用户根目录 / System user root"
    return False, ""


def has_photos(dir_path: str) -> bool:
    """判断目录是否直接包含至少 1 个照片文件"""
    photo_count, _ = _scan_directory_once(dir_path)
    return photo_count > 0


def is_processed(dir_path: str) -> bool:
    """判断目录是否已被 SuperPicky 处理过（存在 report.db）"""
    return os.path.exists(os.path.join(dir_path, '.superpicky', 'report.db'))


def scan_directories(
    root: str,
    max_depth: int = DEFAULT_SCAN_MAX_DEPTH,
) -> List[ScannedDirectory]:
    """扫描根目录，返回包含照片的目录摘要列表。"""
    return _scan_directories_dfs(root, max_depth)


def scan_dfs(root: str, max_depth: int = DEFAULT_SCAN_MAX_DEPTH) -> List[ScannedDirectory]:
    """使用 DFS 扫描根目录。"""
    return scan_directories(root, max_depth=max_depth)


def scan_recursive(root: str, max_depth: int = DEFAULT_SCAN_MAX_DEPTH) -> List[str]:
    """
    递归扫描根目录，返回所有原子目录（包含照片的非排除目录）的绝对路径列表。
    
    Args:
        root: 根目录路径
        max_depth: 最大递归深度（默认 16）
        
    Returns:
        原子目录绝对路径列表，按字母排序
    """
    return [item.path for item in scan_dfs(root, max_depth=max_depth)]


def count_photos(dir_path: str) -> int:
    """统计目录中直接包含的照片文件数量"""
    count, _ = _scan_directory_once(dir_path)
    return count
