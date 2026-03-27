#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SuperPicky - 在线补丁管理器

职责：
- 从 GitHub Release 拉取 patch_meta.json，判断是否有新补丁
- 下载 code_patch_vX.Y.Z.zip 并解压到 code_updates/ 目录
- 写入本地 patch_meta.json 记录当前补丁状态
- 提供 clear_patch() 回滚接口

补丁只在 base_version 与当前应用版本匹配时才应用。
"""

import sys
import json
import ssl
import shutil
import zipfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Tuple


# GitHub Release Asset 文件名
PATCH_META_FILENAME = "patch_meta.json"

# GitCode（中国大陆优先 fallback）
GITCODE_FILE_BASE = "https://gitcode.com/Jamesphotography/SuperPicky/-/package_files/generic/release"

# 北京镜像服务器（最终兜底）
MIRROR_BASE_URL = "http://1.119.150.179:59080/superpicky"


def _get_app_data_dir() -> Path:
    """返回 SuperPicky 用户数据目录（跨平台）"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SuperPicky"
    elif sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "SuperPicky"
    else:
        return Path.home() / ".config" / "SuperPicky"


def get_patch_dir() -> Path:
    """返回补丁解压目录，注入 sys.path 时使用"""
    return _get_app_data_dir() / "code_updates"


def _get_local_meta_path() -> Path:
    return _get_app_data_dir() / "patch_meta.json"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_json(url: str, timeout: int = 10) -> Optional[dict]:
    """GET 请求并解析 JSON，失败返回 None"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SuperPicky-PatchManager"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _find_patch_meta_url(assets: list) -> Optional[str]:
    """在 Release assets 中找到 patch_meta.json 的下载链接"""
    for asset in assets:
        if asset.get("name", "") == PATCH_META_FILENAME:
            return asset.get("browser_download_url")
    return None


def _find_patch_zip_url(assets: list, patch_version: str) -> Optional[str]:
    """在 Release assets 中找到对应版本的 patch zip 下载链接"""
    target = f"code_patch_{patch_version}.zip"
    for asset in assets:
        if asset.get("name", "") == target:
            return asset.get("browser_download_url")
    # 兜底：找任意 code_patch_*.zip
    for asset in assets:
        name = asset.get("name", "")
        if name.startswith("code_patch_") and name.endswith(".zip"):
            return asset.get("browser_download_url")
    return None


def read_local_meta() -> Optional[Dict]:
    """读取本地 patch_meta.json，不存在返回 None"""
    path = _get_local_meta_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_local_meta(meta: dict) -> None:
    path = _get_local_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _download_to_temp(url: str, timeout: int = 60) -> Optional[Path]:
    """下载文件到临时路径，返回临时文件 Path，失败返回 None"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SuperPicky-PatchManager"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            suffix = Path(url).suffix or ".tmp"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                shutil.copyfileobj(resp, f)
                return Path(f.name)
    except Exception:
        return None


def apply_patch_file(zip_path: Path, meta: dict) -> bool:
    """
    解压 zip 到 code_updates/ 目录并写入 patch_meta.json。

    Args:
        zip_path: 本地 zip 文件路径（可以是下载的临时文件或本地测试文件）
        meta: 要写入的 patch_meta 字典

    Returns:
        True 表示成功，False 表示失败
    """
    patch_dir = get_patch_dir()
    try:
        # 先清空旧补丁
        if patch_dir.exists():
            shutil.rmtree(patch_dir)
        patch_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(patch_dir)

        _write_local_meta(meta)
        return True
    except Exception as e:
        print(f"[PatchManager] 解压失败: {e}")
        # 解压失败时清理残留
        if patch_dir.exists():
            shutil.rmtree(patch_dir, ignore_errors=True)
        return False


def clear_patch() -> None:
    """清除当前补丁（回滚到内置版本）"""
    patch_dir = get_patch_dir()
    meta_path = _get_local_meta_path()
    if patch_dir.exists():
        shutil.rmtree(patch_dir, ignore_errors=True)
    if meta_path.exists():
        meta_path.unlink(missing_ok=True)
    print("[PatchManager] 补丁已清除")


def check_and_apply_patch_from_gitcode(
    gitcode_links: list,
    current_app_version: str,
    timeout: int = 30,
) -> Tuple[bool, str]:
    """
    从 GitCode release asset links 检查并应用补丁（GitHub API 不可达时使用）。

    Args:
        gitcode_links: GitCode release assets.links 列表（每项含 name + url）
        current_app_version: 当前应用版本号
        timeout: 超时秒数

    Returns:
        (patched, message)
    """
    # 找 patch_meta.json 链接
    meta_url = None
    for link in gitcode_links:
        if link.get("name", "") == PATCH_META_FILENAME:
            meta_url = link.get("url")
            break
    if not meta_url:
        return False, "GitCode release 中没有 patch_meta.json"

    remote_meta = _fetch_json(meta_url, timeout=10)
    if not remote_meta:
        return False, "拉取 GitCode patch_meta.json 失败"

    base_version = remote_meta.get("base_version", "")
    if base_version != current_app_version:
        return False, f"补丁 base_version={base_version} 与当前版本 {current_app_version} 不匹配"

    remote_patch_version = remote_meta.get("patch_version", "")
    local_meta = read_local_meta()
    local_patch_version = local_meta.get("patch_version", "") if local_meta else ""

    if remote_patch_version == local_patch_version:
        return False, f"补丁已是最新（{local_patch_version}）"

    # 找 zip 链接
    zip_url = None
    target = f"code_patch_{remote_patch_version}.zip"
    for link in gitcode_links:
        if link.get("name", "") == target:
            zip_url = link.get("url")
            break

    print(f"[PatchManager] 从 GitCode 下载补丁 {remote_patch_version} ...")
    tmp_path = _download_to_temp(zip_url, timeout=timeout) if zip_url else None
    if not tmp_path:
        mirror_zip_url = f"{MIRROR_BASE_URL}/code_patch_{remote_patch_version}.zip"
        print(f"[PatchManager] GitCode CDN 失败，尝试北京镜像: {mirror_zip_url}")
        tmp_path = _download_to_temp(mirror_zip_url, timeout=timeout)
    if not tmp_path:
        return False, "补丁 zip 下载失败（GitCode + 北京镜像均不可用）"

    try:
        success = apply_patch_file(tmp_path, remote_meta)
    finally:
        tmp_path.unlink(missing_ok=True)

    if success:
        return True, f"补丁 {remote_patch_version} 已从 GitCode 应用"
    else:
        return False, "补丁解压失败"


def check_and_apply_patch_from_mirror(
    current_app_version: str,
    timeout: int = 30,
) -> Tuple[bool, str]:
    """
    完全从镜像服务器检查并应用补丁（GitHub 不可达时使用）。

    Args:
        current_app_version: 当前应用版本号
        timeout: 超时秒数

    Returns:
        (patched, message)
    """
    meta_url = f"{MIRROR_BASE_URL}/patch_meta.json"
    remote_meta = _fetch_json(meta_url, timeout=10)
    if not remote_meta:
        return False, "镜像服务器不可用"

    base_version = remote_meta.get("base_version", "")
    if base_version != current_app_version:
        return False, f"补丁 base_version={base_version} 与当前版本 {current_app_version} 不匹配"

    remote_patch_version = remote_meta.get("patch_version", "")
    local_meta = read_local_meta()
    local_patch_version = local_meta.get("patch_version", "") if local_meta else ""

    if remote_patch_version == local_patch_version:
        return False, f"补丁已是最新（{local_patch_version}）"

    zip_url = f"{MIRROR_BASE_URL}/code_patch_{remote_patch_version}.zip"
    print(f"[PatchManager] 从镜像下载补丁 {remote_patch_version} ...")
    tmp_path = _download_to_temp(zip_url, timeout=timeout)
    if not tmp_path:
        return False, "镜像补丁 zip 下载失败"

    try:
        success = apply_patch_file(tmp_path, remote_meta)
    finally:
        tmp_path.unlink(missing_ok=True)

    if success:
        return True, f"补丁 {remote_patch_version} 已从镜像应用"
    else:
        return False, "补丁解压失败"


def check_and_apply_patch(
    release_assets: list,
    current_app_version: str,
    timeout: int = 30,
) -> Tuple[bool, str]:
    """
    检查 Release assets 中是否有可用补丁，有则下载并应用。

    Args:
        release_assets: GitHub Release 的 assets 列表（已由 update_checker 获取）
        current_app_version: 当前应用版本号（如 "4.2.5"）
        timeout: 下载超时秒数

    Returns:
        (patched, message)
        patched=True 表示成功应用了新补丁
    """
    # 1. 找到 patch_meta.json 的下载链接
    meta_url = _find_patch_meta_url(release_assets)
    if not meta_url:
        return False, "Release 中没有 patch_meta.json"

    # 2. 拉取远端 patch_meta.json
    remote_meta = _fetch_json(meta_url, timeout=10)
    if not remote_meta:
        return False, "拉取 patch_meta.json 失败"

    # 3. 检查 base_version 是否匹配当前应用版本
    base_version = remote_meta.get("base_version", "")
    if base_version != current_app_version:
        return False, f"补丁 base_version={base_version} 与当前版本 {current_app_version} 不匹配"

    # 4. 对比本地补丁版本
    remote_patch_version = remote_meta.get("patch_version", "")
    local_meta = read_local_meta()
    local_patch_version = local_meta.get("patch_version", "") if local_meta else ""

    if remote_patch_version == local_patch_version:
        return False, f"补丁已是最新（{local_patch_version}）"

    # 5. 找到 zip 下载链接
    zip_url = _find_patch_zip_url(release_assets, remote_patch_version)
    if not zip_url:
        return False, f"Release 中找不到 code_patch_{remote_patch_version}.zip"

    # 6. 下载 zip（三级降级：GitHub CDN → 北京镜像 → GitCode）
    print(f"[PatchManager] 下载补丁 {remote_patch_version} ...")
    tmp_path = _download_to_temp(zip_url, timeout=timeout)
    if not tmp_path:
        mirror_zip_url = f"{MIRROR_BASE_URL}/code_patch_{remote_patch_version}.zip"
        print(f"[PatchManager] GitHub CDN 失败，尝试北京镜像: {mirror_zip_url}")
        tmp_path = _download_to_temp(mirror_zip_url, timeout=timeout)
    if not tmp_path:
        gitcode_zip_url = f"{GITCODE_FILE_BASE}/{remote_patch_version}/code_patch_{remote_patch_version}.zip"
        print(f"[PatchManager] 北京镜像失败，尝试 GitCode: {gitcode_zip_url}")
        tmp_path = _download_to_temp(gitcode_zip_url, timeout=timeout)
    if not tmp_path:
        return False, "补丁 zip 下载失败（GitHub + 北京镜像 + GitCode 均不可用）"

    # 7. 解压并写入 meta
    try:
        success = apply_patch_file(tmp_path, remote_meta)
    finally:
        tmp_path.unlink(missing_ok=True)

    if success:
        return True, f"补丁 {remote_patch_version} 已应用"
    else:
        return False, "补丁解压失败"


# ── 独立运行测试 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SuperPicky PatchManager 测试工具")
    sub = parser.add_subparsers(dest="cmd")

    # 本地 zip 测试
    p_local = sub.add_parser("apply-local", help="应用本地 zip 文件（测试用）")
    p_local.add_argument("zip_path", help="本地 zip 文件路径")
    p_local.add_argument("--patch-version", default="test-patch", help="写入 meta 的 patch_version")

    # 清除补丁
    sub.add_parser("clear", help="清除当前补丁")

    # 查看本地 meta
    sub.add_parser("status", help="查看当前补丁状态")

    args = parser.parse_args()

    if args.cmd == "apply-local":
        from constants import APP_VERSION
        meta = {
            "patch_version": args.patch_version,
            "base_version": APP_VERSION,
            "applied_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        ok = apply_patch_file(Path(args.zip_path), meta)
        print(f"[PatchManager] {'成功' if ok else '失败'}，patch_dir={get_patch_dir()}")

    elif args.cmd == "clear":
        clear_patch()

    elif args.cmd == "status":
        meta = read_local_meta()
        if meta:
            print(json.dumps(meta, indent=2, ensure_ascii=False))
        else:
            print("无本地补丁")

    else:
        parser.print_help()
