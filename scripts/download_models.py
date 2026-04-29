import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Optional, cast


def _reconfigure_text_stream(stream: object) -> None:
    """Use UTF-8 output when the active stream implementation supports it."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict")


_reconfigure_text_stream(sys.stdout)
_reconfigure_text_stream(sys.stderr)

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    hf_hub_download = None

try:
    from core.source_probe import pick_best_source, probe_sources
except Exception:
    pick_best_source = None
    probe_sources = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"
DOWNLOAD_ENDPOINTS = [
    ("hf-mirror", HF_MIRROR_ENDPOINT),
    ("official", HF_OFFICIAL_ENDPOINT),
]

# NOTE:
# The old MODELS_TO_DOWNLOAD entrypoint is intentionally kept for CLI compatibility.
# New initialization code uses the richer resource metadata and filtering helpers below.
MODELS_TO_DOWNLOAD = [
    {
        "resource_id": "classification_model",
        "category": "Classification",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "model20240824.pth",
        "dest_dir": "models",
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


def _resolve_hf_endpoints() -> list[tuple[str, str]]:
    if probe_sources is None or pick_best_source is None:
        return list(DOWNLOAD_ENDPOINTS)

    probe_input = [{"name": name, "url": endpoint} for name, endpoint in DOWNLOAD_ENDPOINTS]
    results = probe_sources("huggingface-models", probe_input)
    best = pick_best_source(results)
    if best is None:
        return list(DOWNLOAD_ENDPOINTS)

    ordered = []
    ordered.append((best.name, best.url))
    ordered.extend(
        (name, endpoint)
        for name, endpoint in DOWNLOAD_ENDPOINTS
        if endpoint != best.url
    )
    return ordered


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
) -> list[Dict[str, Any]]:
    plan = list(_iter_selected_resources(MODELS_TO_DOWNLOAD, selected_features))
    if include_optional_local:
        plan.extend(_iter_selected_resources(OPTIONAL_LOCAL_RESOURCES, selected_features))
    return plan


def resolve_best_sources() -> Dict[str, str]:
    endpoints = _resolve_hf_endpoints()
    return {name: endpoint for name, endpoint in endpoints}


def _emit_resource_progress(
    progress_cb: Optional[Callable[[Dict[str, Any], float, str], None]],
    resource: Dict[str, Any],
    percent: float,
    message: str,
) -> None:
    if progress_cb:
        progress_cb(resource, percent, message)


def _copy_local_resource(
    resource: Dict[str, Any],
    project_root: Path,
    progress_cb: Optional[Callable[[Dict[str, Any], float, str], None]] = None,
) -> Optional[Path]:
    filename = resource["filename"]
    dest_dir = project_root / resource["dest_dir"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / filename

    if destination.exists():
        _emit_resource_progress(progress_cb, resource, 100.0, f"{filename} already present")
        return destination

    local_candidates = [
        project_root / resource["dest_dir"] / filename,
        project_root / "resources" / resource["dest_dir"] / filename,
    ]
    for candidate in local_candidates:
        if candidate.exists():
            if candidate.resolve() != destination.resolve():
                destination.write_bytes(candidate.read_bytes())
            _emit_resource_progress(progress_cb, resource, 100.0, f"{filename} copied from local fallback")
            return destination
    return None


def _download_with_fallback(
    repo_id: str,
    filename: str,
    full_dest_dir: str,
    *,
    progress_cb: Optional[Callable[[str, float, str], None]] = None,
) -> Optional[str]:
    global hf_hub_download
    if hf_hub_download is None:
        try:
            from huggingface_hub import hf_hub_download as _hf_hub_download

            hf_hub_download = _hf_hub_download
        except Exception as exc:
            raise RuntimeError(f"huggingface_hub is not installed yet: {exc}") from exc
    errors = []
    endpoints = _resolve_hf_endpoints()

    for index, (source_name, endpoint) in enumerate(endpoints):
        logging.info("Attempting %s via %s (%s)", filename, source_name, endpoint)
        if progress_cb:
            progress_cb(source_name, 5.0 + (index * 10.0), f"{filename}: connecting {source_name}")
        try:
            download_kwargs: dict[str, Any] = {
                "repo_id": repo_id,
                "filename": filename,
                "local_dir": full_dest_dir,
                "local_dir_use_symlinks": False,
                "endpoint": endpoint,
            }
            # Keep old CLI-compatible behavior while allowing newer hub versions to resume.
            try:
                download_kwargs["resume_download"] = True
            except Exception:
                pass
            downloaded_path = cast(Any, hf_hub_download)(**download_kwargs)
            if progress_cb:
                progress_cb(source_name, 100.0, f"{filename}: ready via {source_name}")
            logging.info("%s is ready via %s.", filename, source_name)
            return downloaded_path
        except Exception as exc:
            error_text = _format_download_error(exc)
            errors.append(f"{source_name}: {error_text}")
            logging.warning("%s failed via %s: %s", filename, source_name, error_text)
            if progress_cb:
                progress_cb(source_name, 0.0, f"{filename}: {source_name} failed, trying fallback")
            if index < len(endpoints) - 1:
                next_source_name = endpoints[index + 1][0]
                logging.info("Falling back to %s for %s...", next_source_name, filename)

    logging.error(
        "All download sources failed for %s from %s. Details: %s",
        filename,
        repo_id,
        " | ".join(errors),
    )
    return None


def download_resource(
    resource: Dict[str, Any],
    *,
    project_root: Optional[Path] = None,
    progress_cb: Optional[Callable[[Dict[str, Any], float, str], None]] = None,
) -> Path:
    project_root = project_root or get_project_root()

    if resource.get("copy_only"):
        copied = _copy_local_resource(resource, project_root, progress_cb=progress_cb)
        if copied is None:
            raise FileNotFoundError(f"Local fallback resource not found: {resource['filename']}")
        return copied

    repo_id = resource["repo_id"]
    filename = resource["filename"]
    full_dest_dir = project_root / resource["dest_dir"]
    full_dest_dir.mkdir(parents=True, exist_ok=True)

    _emit_resource_progress(progress_cb, resource, 0.0, f"Preparing {filename}")

    downloaded_path = _download_with_fallback(
        repo_id=repo_id,
        filename=filename,
        full_dest_dir=str(full_dest_dir),
        progress_cb=(
            lambda source_name, percent, message: progress_cb(resource, percent, message)
            if progress_cb else None
        ),
    )
    if not downloaded_path:
        raise RuntimeError(f"Failed to download {filename} from {repo_id}")

    path_obj = Path(downloaded_path)
    if not verify_resource(resource, path_obj):
        path_obj.unlink(missing_ok=True)
        raise RuntimeError(f"Integrity verification failed for {filename}")

    _emit_resource_progress(progress_cb, resource, 100.0, f"Verified {filename}")
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

    # NOTE:
    # The old CLI behavior is intentionally preserved here as a compatibility fallback.
    # The new onboarding/initialization flow now uses resolve_download_plan() directly.
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
