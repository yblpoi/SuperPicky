"""
Model and resource download helpers for lightweight initialization.

This module prepares model files and local fallback resources needed by the
welcome onboarding flow. It emits structured progress events so callers can
aggregate real byte progress, item-level progress, and source retry state
without scraping ad-hoc log text.

轻量化初始化所需的模型与资源下载辅助模块。

此模块负责准备欢迎引导流程所需的模型文件与本地回退资源，并发出结构化进度事件，
以便调用方能够聚合真实字节进度、条目级进度以及镜像重试状态，而不必再解析零散日志文本。
"""

import hashlib
import importlib
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, cast


def _reconfigure_text_stream(stream: object) -> None:
    """Use UTF-8 output when the active stream implementation supports it."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict")


_reconfigure_text_stream(sys.stdout)
_reconfigure_text_stream(sys.stderr)

HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"
os.environ["HF_ENDPOINT"] = HF_MIRROR_ENDPOINT
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    hf_hub_download = None

try:
    from tqdm.auto import tqdm as tqdm_base
except ImportError:
    tqdm_base = None

try:
    from core.source_probe import pick_best_source, probe_sources
except Exception:
    pick_best_source = None
    probe_sources = None

from core.initialization_progress import (
    InitializationProgressEvent,
    PROGRESS_KIND_DOWNLOAD,
    STAGE_DOWNLOADING,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

DOWNLOAD_ENDPOINTS = [
    ("hf-mirror", HF_MIRROR_ENDPOINT),
    ("official", HF_OFFICIAL_ENDPOINT),
]

MODELS_TO_DOWNLOAD = [
    {
        "resource_id": "classification_model",
        "category": "Classification",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "model20240824.pth",
        "dest_dir": "models",
        "packaged_dest_dir": "models",
        "feature_tags": ["core_detection", "birdid"],
        "required": True,
        "sha256": None,
    },
    {
        "resource_id": "flight_model",
        "category": "Flight Detection",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "superFlier_efficientnet.pth",
        "dest_dir": "models",
        "packaged_dest_dir": "models",
        "feature_tags": ["flight"],
        "required": False,
        "sha256": None,
    },
    {
        "resource_id": "keypoint_model",
        "category": "Keypoint Detection",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "cub200_keypoint_resnet50_slim.pth",
        "dest_dir": "models",
        "packaged_dest_dir": "models",
        "feature_tags": ["keypoint"],
        "required": False,
        "sha256": None,
    },
    {
        "resource_id": "avonet_database",
        "category": "Database",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "avonet.db",
        "dest_dir": "birdid/data",
        "feature_tags": ["birdid"],
        "required": False,
        "sha256": None,
    },
    {
        "resource_id": "quality_model",
        "category": "Quality Assessment",
        "repo_id": "chaofengc/IQA-PyTorch-Weights",
        "filename": "cfanet_iaa_ava_res50-3cd62bb3.pth",
        "dest_dir": "models",
        "packaged_dest_dir": "models",
        "feature_tags": ["quality"],
        "required": False,
        "sha256": None,
    },
    {
        "resource_id": "yolo_segmentation",
        "category": "Segmentation",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "yolo11l-seg.pt",
        "dest_dir": "models",
        "packaged_dest_dir": "models",
        "feature_tags": ["core_detection"],
        "required": True,
        "sha256": None,
    },
]

OPTIONAL_LOCAL_RESOURCES = [
    {
        "resource_id": "bird_reference_sqlite",
        "filename": "bird_reference.sqlite",
        "dest_dir": "birdid/data",
        "feature_tags": ["birdid"],
        "required": False,
        "sha256": None,
        "copy_only": True,
    },
    {
        "resource_id": "birdname_db",
        "filename": "birdname.db",
        "dest_dir": "ioc",
        "feature_tags": ["birdid"],
        "required": False,
        "sha256": None,
        "copy_only": True,
    },
]


def get_project_root() -> Path:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return Path(os.path.abspath(os.path.join(script_dir, "..")))


def _format_download_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        message = repr(exc)
    return f"{type(exc).__name__}: {message}"


def _sha256_file(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_resource(resource: Dict[str, Any], file_path: Path) -> bool:
    expected_sha256 = resource.get("sha256")
    if not expected_sha256:
        return file_path.exists()
    return file_path.exists() and _sha256_file(file_path) == expected_sha256.lower()


def _resolve_hf_endpoints() -> List[Tuple[str, str]]:
    if probe_sources is None or pick_best_source is None:
        return list(DOWNLOAD_ENDPOINTS)

    probe_input = [{"name": name, "url": endpoint} for name, endpoint in DOWNLOAD_ENDPOINTS]
    results = probe_sources("huggingface-models", probe_input)
    successful = [item for item in results if item.ok]
    if not successful:
        return list(DOWNLOAD_ENDPOINTS)

    non_official = [item for item in successful if "official" not in item.name.lower()]
    preferred = non_official or successful
    ordered_results = sorted(preferred, key=lambda item: (item.total_ms, item.first_byte_ms))
    if non_official:
        return [(item.name, item.url) for item in ordered_results]

    return [(item.name, item.url) for item in ordered_results]


def _resource_matches_selection(resource: Dict[str, Any], selected: set[str]) -> bool:
    if resource.get("required"):
        return True
    feature_tags = set(resource.get("feature_tags", []))
    return not selected or bool(feature_tags & selected)


def _iter_selected_resources(
    resources: Iterable[Dict[str, Any]],
    selected_features: Optional[Iterable[str]],
) -> Iterator[Dict[str, Any]]:
    selected = set(selected_features or [])
    for item in resources:
        if _resource_matches_selection(item, selected):
            yield dict(item)


def resolve_download_plan(
    selected_features: Optional[Iterable[str]] = None,
    *,
    include_optional_local: bool = True,
) -> List[Dict[str, Any]]:
    plan = list(_iter_selected_resources(MODELS_TO_DOWNLOAD, selected_features))
    if include_optional_local:
        plan.extend(_iter_selected_resources(OPTIONAL_LOCAL_RESOURCES, selected_features))
    return plan


def _emit_resource_progress(
    progress_cb: Optional[Callable[[InitializationProgressEvent], None]],
    event: InitializationProgressEvent,
) -> None:
    if progress_cb:
        progress_cb(event)


def _build_resource_progress_event(
    resource: Dict[str, Any],
    message: str,
    *,
    ratio: float | None = None,
    bytes_done: int | None = None,
    bytes_total: int | None = None,
    source: str | None = None,
    is_terminal: bool = False,
) -> InitializationProgressEvent:
    """
    Create a structured progress payload for one resource update.

    为单个资源更新创建结构化进度负载。
    """
    return InitializationProgressEvent(
        stage=STAGE_DOWNLOADING,
        progress_kind=PROGRESS_KIND_DOWNLOAD,
        message=message,
        ratio=ratio,
        bytes_done=bytes_done,
        bytes_total=bytes_total,
        resource_id=resource.get("resource_id"),
        source=source,
        is_terminal=is_terminal,
    )


def resolve_resource_destination_dir(project_root: Path, resource: Dict[str, Any]) -> Path:
    dest_dir = resource["dest_dir"]
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        dest_dir = resource.get("packaged_dest_dir", dest_dir)
    return project_root / dest_dir


def _copy_local_resource(
    resource: Dict[str, Any],
    project_root: Path,
    progress_cb: Optional[Callable[[InitializationProgressEvent], None]] = None,
) -> Optional[Path]:
    """
    Copy a packaged local fallback resource into the expected destination.

    将打包时附带的本地回退资源复制到目标目录。
    """
    filename = resource["filename"]
    dest_dir = resolve_resource_destination_dir(project_root, resource)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / filename

    if destination.exists():
        existing_size = destination.stat().st_size
        _emit_resource_progress(
            progress_cb,
            _build_resource_progress_event(
                resource,
                f"{filename} already present",
                ratio=1.0,
                bytes_done=existing_size,
                bytes_total=existing_size,
                is_terminal=True,
            ),
        )
        return destination

    local_candidates = [
        resolve_resource_destination_dir(project_root, resource) / filename,
        project_root / "resources" / resource["dest_dir"] / filename,
    ]
    for candidate in local_candidates:
        if candidate.exists():
            if candidate.resolve() != destination.resolve():
                destination.write_bytes(candidate.read_bytes())
            copied_size = destination.stat().st_size
            _emit_resource_progress(
                progress_cb,
                _build_resource_progress_event(
                    resource,
                    f"{filename} copied from local fallback",
                    ratio=1.0,
                    bytes_done=copied_size,
                    bytes_total=copied_size,
                    is_terminal=True,
                ),
            )
            return destination
    return None


def _estimate_remote_file_size(repo_id: str, filename: str) -> int | None:
    """
    Estimate remote file size with `hf_hub_download(..., dry_run=True)`.

    通过 `hf_hub_download(..., dry_run=True)` 估算远端文件大小。
    """
    global hf_hub_download
    if hf_hub_download is None:
        return None

    for _source_name, endpoint in _resolve_hf_endpoints():
        try:
            _configure_hf_client_for_endpoint(endpoint)
            dry_run_info = cast(
                Any,
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    endpoint=endpoint,
                    dry_run=True,
                ),
            )
            file_size = getattr(dry_run_info, "file_size", None)
            if isinstance(file_size, int) and file_size > 0:
                return file_size
        except Exception:
            continue
    return None


def _build_download_tqdm_class(
    resource: Dict[str, Any],
    source_name: str,
    expected_bytes: int | None,
    progress_cb: Optional[Callable[[InitializationProgressEvent], None]],
):
    """
    Create a tqdm subclass that forwards byte-level download updates.

    创建一个把字节级下载更新转发为结构化事件的 tqdm 子类。
    """
    if progress_cb is None or tqdm_base is None:
        return None

    class ResourceDownloadTqdm(tqdm_base):
        """
        Progress tracker used internally by `hf_hub_download`.

        `hf_hub_download` 内部使用的进度跟踪器。
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            total = getattr(self, "total", None) or expected_bytes
            if isinstance(total, (int, float)) and total > 0:
                total = int(total)
            else:
                total = expected_bytes
            self._superpicky_total = total
            self._superpicky_last_n = 0
            _emit_resource_progress(
                progress_cb,
                _build_resource_progress_event(
                    resource,
                    f"{resource['filename']}: downloading from {source_name}",
                    ratio=0.0 if total else None,
                    bytes_done=0,
                    bytes_total=total,
                    source=source_name,
                ),
            )

        def update(self, n=1):
            result = super().update(n)
            current = int(getattr(self, "n", self._superpicky_last_n))
            total = getattr(self, "total", None) or self._superpicky_total
            if isinstance(total, (int, float)) and total > 0:
                total = int(total)
                ratio = current / total
            else:
                total = None
                ratio = None
            self._superpicky_last_n = current
            _emit_resource_progress(
                progress_cb,
                _build_resource_progress_event(
                    resource,
                    f"{resource['filename']}: downloading from {source_name}",
                    ratio=ratio,
                    bytes_done=current,
                    bytes_total=total,
                    source=source_name,
                    is_terminal=bool(total and current >= total),
                ),
            )
            return result

        def close(self):
            current = int(getattr(self, "n", self._superpicky_last_n))
            total = getattr(self, "total", None) or self._superpicky_total
            if isinstance(total, (int, float)) and total > 0:
                total = int(total)
                ratio = min(1.0, current / total)
            else:
                total = None
                ratio = None
            _emit_resource_progress(
                progress_cb,
                _build_resource_progress_event(
                    resource,
                    f"{resource['filename']}: download stream closed",
                    ratio=ratio,
                    bytes_done=current,
                    bytes_total=total,
                    source=source_name,
                    is_terminal=bool(total and current >= total),
                ),
            )
            return super().close()

    return ResourceDownloadTqdm


def _download_with_fallback(
    resource: Dict[str, Any],
    repo_id: str,
    filename: str,
    full_dest_dir: str,
    *,
    expected_bytes: int | None = None,
    progress_cb: Optional[Callable[[InitializationProgressEvent], None]] = None,
) -> Optional[str]:
    """
    使用回退机制下载文件，支持重试和源切换。

    Download file with fallback mechanism, supporting retry and source switching.

    参数 Parameters:
        repo_id (str): Hugging Face 仓库 ID
        filename (str): 要下载的文件名
        full_dest_dir (str): 目标目录路径
        expected_bytes (int | None): 预估文件大小
        progress_cb (Optional[Callable[[InitializationProgressEvent], None]]): 进度回调函数

    返回 Returns:
        Optional[str]: 下载的文件路径，失败时返回 None
    """
    global hf_hub_download
    if hf_hub_download is None:
        try:
            from huggingface_hub import hf_hub_download as _hf_hub_download

            hf_hub_download = _hf_hub_download
        except Exception as exc:
            raise RuntimeError(f"huggingface_hub is not installed yet: {exc}") from exc

    errors = []
    endpoints = _resolve_hf_endpoints()
    max_retries = 3  # 每个源的最大重试次数

    for index, (source_name, endpoint) in enumerate(endpoints):
        logging.info("尝试从 %s (%s) 下载 %s", source_name, endpoint, filename)

        for retry_count in range(max_retries):
            _emit_resource_progress(
                progress_cb,
                _build_resource_progress_event(
                    resource,
                    f"{filename}: connecting {source_name} ({retry_count + 1}/{max_retries})",
                    ratio=0.0 if expected_bytes else None,
                    bytes_done=0,
                    bytes_total=expected_bytes,
                    source=source_name,
                ),
            )

            start_time = time.perf_counter()
            try:
                _configure_hf_client_for_endpoint(endpoint)
                download_kwargs: Dict[str, Any] = {
                    "repo_id": repo_id,
                    "filename": filename,
                    "local_dir": full_dest_dir,
                    "local_dir_use_symlinks": False,
                    "endpoint": endpoint,
                }
                tqdm_class = _build_download_tqdm_class(
                    resource,
                    source_name,
                    expected_bytes,
                    progress_cb,
                )
                if tqdm_class is not None:
                    download_kwargs["tqdm_class"] = tqdm_class
                try:
                    download_kwargs["resume_download"] = True
                except Exception:
                    pass

                downloaded_path = cast(Any, hf_hub_download)(**download_kwargs)
                elapsed_time = time.perf_counter() - start_time

                path_obj = Path(downloaded_path)
                file_size = path_obj.stat().st_size if path_obj.exists() else expected_bytes
                _emit_resource_progress(
                    progress_cb,
                    _build_resource_progress_event(
                        resource,
                        f"{filename}: downloaded via {source_name}",
                        ratio=1.0,
                        bytes_done=file_size,
                        bytes_total=file_size,
                        source=source_name,
                        is_terminal=True,
                    ),
                )

                logging.info(
                    "%s 已通过 %s 下载完成，耗时 %.2f 秒",
                    filename,
                    source_name,
                    elapsed_time
                )
                return downloaded_path

            except Exception as exc:
                elapsed_time = time.perf_counter() - start_time
                error_text = _format_download_error(exc)
                errors.append(f"{source_name} (尝试 {retry_count + 1}): {error_text}")

                logging.warning(
                    "%s 通过 %s 下载失败 (尝试 %d/%d): %s (耗时 %.2f 秒)",
                    filename,
                    source_name,
                    retry_count + 1,
                    max_retries,
                    error_text,
                    elapsed_time
                )

                _emit_resource_progress(
                    progress_cb,
                    _build_resource_progress_event(
                        resource,
                        f"{filename}: {source_name} failed ({retry_count + 1}/{max_retries})",
                        ratio=0.0 if expected_bytes else None,
                        bytes_done=0,
                        bytes_total=expected_bytes,
                        source=source_name,
                    ),
                )

                if retry_count < max_retries - 1:
                    base_delay = 2 ** retry_count
                    jitter = base_delay * 0.25 * (random.random() * 2 - 1)
                    delay = max(0.5, base_delay + jitter)
                    logging.info("等待 %.2f 秒后重试...", delay)
                    time.sleep(delay)
                else:
                    if index < len(endpoints) - 1:
                        next_source_name = endpoints[index + 1][0]
                        logging.info("(" + next_source_name + ") 切换到下一个源下载 %s...", filename)

    logging.error(
        "所有下载源均失败: %s 来自 %s。详细信息: %s",
        filename,
        repo_id,
        " | ".join(errors),
    )
    return None


def _configure_hf_client_for_endpoint(endpoint: str) -> None:
    """
    强制 huggingface_hub 在当前尝试中保持选定的端点。

    官方文档说明 `HF_ENDPOINT` 会在导入时读取，因此这里同时设置环境变量与运行期常量，
    避免中国网络下已经导入过的客户端偷偷回退到默认官方端点。

    Force huggingface_hub to stay on the selected endpoint for the current attempt.

    The official documentation states that `HF_ENDPOINT` is read during import,
    so we set both environment variables and runtime constants here to prevent
    the already-imported client from silently falling back to the default official endpoint
    under Chinese network conditions.

    参数 Parameters:
        endpoint (str): 要使用的 Hugging Face 端点 URL
                      The Hugging Face endpoint URL to use
    """
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"

    try:
        constants_module = importlib.import_module("huggingface_hub.constants")
        if hasattr(constants_module, "ENDPOINT"):
            constants_module.ENDPOINT = endpoint
            logging.debug("已设置 huggingface_hub.constants.ENDPOINT = %s", endpoint)
    except Exception as exc:
        logging.debug("设置 huggingface_hub.constants.ENDPOINT 失败: %s", exc)

    try:
        file_download_module = importlib.import_module("huggingface_hub.file_download")
        if hasattr(file_download_module, "ENDPOINT"):
            file_download_module.ENDPOINT = endpoint
            logging.debug("已设置 huggingface_hub.file_download.ENDPOINT = %s", endpoint)
    except Exception as exc:
        logging.debug("设置 huggingface_hub.file_download.ENDPOINT 失败: %s", exc)


def download_resource(
    resource: Dict[str, Any],
    *,
    project_root: Optional[Path] = None,
    progress_cb: Optional[Callable[[InitializationProgressEvent], None]] = None,
) -> Path:
    """
    下载并验证资源文件。

    Download and verify resource file.

    参数 Parameters:
        resource (Dict[str, Any]): 资源元数据字典
        project_root (Optional[Path]): 项目根目录
        progress_cb (Optional[Callable[[InitializationProgressEvent], None]]): 进度回调函数

    返回 Returns:
        Path: 下载的文件路径

    异常 Raises:
        FileNotFoundError: 本地回退资源未找到
        RuntimeError: 下载失败或完整性验证失败
    """
    project_root = project_root or get_project_root()

    if resource.get("copy_only"):
        copied = _copy_local_resource(resource, project_root, progress_cb=progress_cb)
        if copied is None:
            raise FileNotFoundError(f"Local fallback resource not found: {resource['filename']}")
        return copied

    repo_id = resource["repo_id"]
    filename = resource["filename"]
    resource_id = resource.get("resource_id", "unknown")
    full_dest_dir = resolve_resource_destination_dir(project_root, resource)
    full_dest_dir.mkdir(parents=True, exist_ok=True)

    logging.info(
        "开始下载资源 [%s]: %s 来自仓库 %s",
        resource_id,
        filename,
        repo_id
    )
    expected_bytes = _estimate_remote_file_size(repo_id, filename)
    _emit_resource_progress(
        progress_cb,
        _build_resource_progress_event(
            resource,
            f"Preparing download for {filename}",
            ratio=0.0 if expected_bytes else None,
            bytes_done=0,
            bytes_total=expected_bytes,
        ),
    )

    download_start_time = time.perf_counter()
    downloaded_path = _download_with_fallback(
        resource=resource,
        repo_id=repo_id,
        filename=filename,
        full_dest_dir=str(full_dest_dir),
        expected_bytes=expected_bytes,
        progress_cb=progress_cb,
    )
    download_elapsed = time.perf_counter() - download_start_time

    if not downloaded_path:
        logging.error(
            "资源 [%s] 下载失败: %s 来自 %s，总耗时 %.2f 秒",
            resource_id,
            filename,
            repo_id,
            download_elapsed
        )
        raise RuntimeError(f"Failed to download {filename} from {repo_id}")

    path_obj = Path(downloaded_path)
    file_size = path_obj.stat().st_size if path_obj.exists() else 0

    logging.info(
        "资源 [%s] 下载文件大小: %d 字节 (%.2f MB)",
        resource_id,
        file_size,
        file_size / (1024 * 1024)
    )

    if not verify_resource(resource, path_obj):
        path_obj.unlink(missing_ok=True)
        logging.error(
            "资源 [%s] 完整性验证失败: %s",
            resource_id,
            filename
        )
        raise RuntimeError(f"Integrity verification failed for {filename}")

    logging.info(
        "资源 [%s] 下载并验证成功: %s，总耗时 %.2f 秒，文件大小 %.2f MB",
        resource_id,
        filename,
        download_elapsed,
        file_size / (1024 * 1024)
    )
    _emit_resource_progress(
        progress_cb,
        _build_resource_progress_event(
            resource,
            f"Validated {filename}",
            ratio=1.0,
            bytes_done=file_size,
            bytes_total=file_size,
            is_terminal=True,
        ),
    )
    return path_obj


def main():
    """
    Downloads required models and database files from Hugging Face Hub.
    Ensures files are placed in the correct directories for the application to function.
    """
    logging.info("Starting model download process...")
    if hf_hub_download is None:
        print("Error: huggingface_hub is not installed. Please run `pip install huggingface_hub tqdm` first.")
        sys.exit(1)

    project_root = get_project_root()
    os.chdir(project_root)
    logging.info("Working directory set to: %s", project_root)

    plan = resolve_download_plan(
        {"core_detection", "quality", "keypoint", "flight", "birdid"},
        include_optional_local=False,
    )
    success_count = 0

    for item in plan:
        logging.info("[%s] Retrieving %s...", item.get("category", "Resource"), item["filename"])
        try:
            downloaded_path = download_resource(item, project_root=project_root)
            logging.info("✓ Successfully downloaded/verified: %s", os.path.basename(downloaded_path))
            success_count += 1
        except Exception as exc:
            logging.error("✗ Failed to prepare %s: %s", item["filename"], _format_download_error(exc))

    if success_count == len(plan):
        logging.info("All %s files are ready.", len(plan))
        logging.info("Application resources are ready to run.")
        sys.exit(0)

    logging.error("Only %s/%s files were successfully prepared.", success_count, len(plan))
    sys.exit(1)


if __name__ == "__main__":
    main()
