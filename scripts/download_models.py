import os
import sys
import logging
from typing import Any, Optional, cast


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
    print("Error: huggingface_hub is not installed. Please run `pip install huggingface_hub tqdm` first.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)

HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"
DOWNLOAD_ENDPOINTS = [
    ("hf-mirror", HF_MIRROR_ENDPOINT),
    ("official", HF_OFFICIAL_ENDPOINT),
]

# Define the models and their destination directories relative to the project root
MODELS_TO_DOWNLOAD = [
    {
        "category": "Classification",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "model20240824.pth",
        "dest_dir": "models",
    },
    {
        "category": "Flight Detection",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "superFlier_efficientnet.pth",
        "dest_dir": "models",
    },
    {
        "category": "Keypoint Detection",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "cub200_keypoint_resnet50_slim.pth",
        "dest_dir": "models",
    },
    {
        "category": "Database",
        "repo_id": "jamesphotography/SuperPicky-models",
        "filename": "avonet.db",
        "dest_dir": "birdid/data",
    },
    {
        "category": "Quality Assessment",
        "repo_id": "chaofengc/IQA-PyTorch-Weights",
        "filename": "cfanet_iaa_ava_res50-3cd62bb3.pth",
        "dest_dir": "models",
    }
]


def _format_download_error(exc: Exception) -> str:
    """Return a concise error string for download attempts."""
    message = str(exc).strip()
    if not message:
        message = repr(exc)
    return f"{type(exc).__name__}: {message}"


def _download_with_fallback(repo_id: str, filename: str, full_dest_dir: str) -> Optional[str]:
    """
    Try the China mirror first, then fall back to the official Hugging Face endpoint.
    Returns the downloaded file path on success, or None if all endpoints fail.
    """
    errors = []

    for index, (source_name, endpoint) in enumerate(DOWNLOAD_ENDPOINTS):
        logging.info(f"Attempting {filename} via {source_name} ({endpoint})")
        try:
            download_kwargs: dict[str, Any] = {
                "repo_id": repo_id,
                "filename": filename,
                "local_dir": full_dest_dir,
                "local_dir_use_symlinks": False,
                "endpoint": endpoint,
            }
            downloaded_path = cast(Any, hf_hub_download)(**download_kwargs)
            logging.info(f"{filename} is ready via {source_name}.")
            return downloaded_path
        except Exception as exc:
            error_text = _format_download_error(exc)
            errors.append(f"{source_name}: {error_text}")
            logging.warning(f"{filename} failed via {source_name}: {error_text}")
            if index < len(DOWNLOAD_ENDPOINTS) - 1:
                next_source_name = DOWNLOAD_ENDPOINTS[index + 1][0]
                logging.info(f"Falling back to {next_source_name} for {filename}...")

    logging.error(
        "All download sources failed for %s from %s. Details: %s",
        filename,
        repo_id,
        " | ".join(errors),
    )
    return None

def main():
    """
    Downloads required models and database files from Hugging Face Hub.
    Ensures files are placed in the correct directories for the application to function.
    """
    logging.info("Starting model download process...")
    
    # Ensure we're running from the project root (where this script is located in an expected directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    
    # Change to project root to simplify path handling if run from elsewhere
    os.chdir(project_root)
    logging.info(f"Working directory set to: {project_root}")

    success_count = 0
    total_models = len(MODELS_TO_DOWNLOAD)

    for item in MODELS_TO_DOWNLOAD:
        repo_id = item["repo_id"]
        filename = item["filename"]
        dest_dir = item["dest_dir"]
        category = item["category"]
        
        full_dest_dir = os.path.join(project_root, dest_dir)

        logging.info(f"[{category}] Retrieving {filename}...")
        
        # Ensure destination directory exists
        os.makedirs(full_dest_dir, exist_ok=True)
        
        try:
            # Download file using huggingface_hub. It handles caching automatically.
            # We use local_dir to bypass symlink behaviors and put it right where we want it.
            # If the file already exists and is the correct size/hash, it won't redownload.
            downloaded_path = _download_with_fallback(
                repo_id=repo_id,
                filename=filename,
                full_dest_dir=full_dest_dir,
            )
            if downloaded_path:
                logging.info(f"✓ Successfully downloaded/verified: {os.path.basename(downloaded_path)}")
                success_count += 1
            else:
                logging.error(f"✗ Failed to download {filename} from {repo_id}")
        except Exception as e:
            logging.error(f"✗ Failed to download {filename} from {repo_id}: {_format_download_error(e)}")

    if success_count == total_models:
        logging.info(f"All {total_models} files are ready.")
        logging.info("Application is ready to run.")
        sys.exit(0)
    else:
        logging.error(f"Only {success_count}/{total_models} files were successfully downloaded.")
        logging.error("Please check your internet connection and verify the files exist in the specified Hugging Face repositories.")
        sys.exit(1)

if __name__ == "__main__":
    main()
