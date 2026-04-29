# -*- coding: utf-8 -*-
"""
First-run initialization manager for lightweight builds.

The old first-run onboarding path is intentionally preserved elsewhere for
full-package compatibility. This manager only takes over when runtime or
required resources are missing.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from PySide6.QtCore import QObject, Signal

from advanced_config import get_advanced_config
from config import get_app_config_dir
from core.source_probe import pick_best_source, probe_sources
from scripts.download_models import download_resource, resolve_download_plan


PIPY_SOURCES = [
    {"name": "cernet", "url": "https://mirrors.cernet.edu.cn/pypi/web/simple"},
    {"name": "official", "url": "https://pypi.org/simple"},
]

CUDA_TORCH_SOURCES = [
    {"name": "nju-cu118", "url": "https://mirror.nju.edu.cn/pytorch/whl/cu118/"},
    {"name": "official-cu118", "url": "https://download.pytorch.org/whl/cu118"},
]

CPU_TORCH_SOURCES = [
    {"name": "official-cpu", "url": "https://mirrors.cernet.edu.cn/pypi/web/simple"},
    {"name": "official", "url": "https://pypi.org/simple"},
]

MAC_TORCH_SOURCES = [
    {"name": "cernet", "url": "https://mirrors.cernet.edu.cn/pypi/web/simple"},
    {"name": "official", "url": "https://pypi.org/simple"},
]

RUNTIME_REQUIREMENTS = {
    "cpu": "requirements_runtime_cpu.txt",
    "cuda": "requirements_runtime_cuda.txt",
    "mac": "requirements_runtime_mac.txt",
}

STAGE_NOT_STARTED = "not_started"
STAGE_PROBING = "probing_sources"
STAGE_CHECKING_UPDATES = "checking_updates"
STAGE_PREPARING_RUNTIME = "preparing_runtime"
STAGE_DOWNLOADING = "downloading_resources"
STAGE_VERIFYING = "verifying"
STAGE_READY = "ready"
STAGE_FAILED = "failed"


@dataclass
class RuntimeSelection:
    variant: str
    detected_cuda_capable: bool
    reason: str


class InitializationManager(QObject):
    stage_changed = Signal(str, str)
    progress_changed = Signal(int, str, int, int)
    item_status_changed = Signal(str, str, str)
    finished = Signal(bool, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_advanced_config()
        self._thread: Optional[threading.Thread] = None
        self._last_options: Optional[dict] = None
        self._last_mode: str = "init"
        self._project_root = Path(__file__).resolve().parent.parent
        self._runtime_dir = get_app_config_dir() / "runtime_env"
        self._source_map: Dict[str, str] = {}

    @staticmethod
    def _normalize_features(selected_features: Optional[Iterable[str]]) -> list[str]:
        features = list(selected_features or [])
        if "core_detection" not in features:
            features.insert(0, "core_detection")
        return features

    def _save_config(self, **updates) -> None:
        setters = {
            "initialization_completed": self.config.set_initialization_completed,
            "initialization_in_progress": self.config.set_initialization_in_progress,
            "selected_runtime_variant": self.config.set_selected_runtime_variant,
            "detected_cuda_capable": self.config.set_detected_cuda_capable,
            "enabled_feature_set": self.config.set_enabled_feature_set,
            "downloaded_resources": self.config.set_downloaded_resources,
            "resolved_source_map": self.config.set_resolved_source_map,
            "last_init_error": self.config.set_last_init_error,
            "is_first_run": self.config.set_is_first_run,
        }
        for key, value in updates.items():
            setter = setters.get(key)
            if setter is not None:
                setter(value)
        self.config.save()

    def _emit_item_status(self, resource_id: str, status: str, detail: str) -> None:
        self.item_status_changed.emit(resource_id, status, detail)

    def start(self, options: dict, mode: str = "init") -> None:
        normalized_options = dict(options)
        normalized_options["features"] = self._normalize_features(normalized_options.get("features"))
        self._last_options = normalized_options
        self._last_mode = mode
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, args=(dict(normalized_options), mode), daemon=True)
        self._thread.start()

    def start_initialization(self, options: dict) -> None:
        self.start(options, mode="init")

    def start_repair(self, options: dict) -> None:
        self.start(options, mode="repair")

    def retry_failed(self) -> None:
        if self._last_options is not None:
            self.start(self._last_options, mode=self._last_mode)

    def resume_pending(self) -> None:
        if self._last_options is not None:
            self.start(self._last_options, mode=self._last_mode)

    def is_ready_for_main_ui(self, selected_features: Optional[Iterable[str]] = None) -> bool:
        return self._has_runtime_available() and self._resources_available(selected_features)

    def needs_initialization(self, selected_features: Optional[Iterable[str]] = None) -> bool:
        # Compatibility note:
        # We do not force initialization only because the config flag is false.
        # Full packages and dev environments may already contain all required assets.
        return not self.is_ready_for_main_ui(selected_features)

    def check_runtime_health(self) -> bool:
        return self._has_runtime_available() and self._runtime_import_ok()

    def check_resource_health(self, selected_features: Optional[Iterable[str]]) -> Dict[str, bool]:
        plan = resolve_download_plan(self._normalize_features(selected_features))
        return {item["resource_id"]: self._resource_item_available(item) for item in plan}

    def repair_runtime_if_needed(self, runtime_variant: str) -> bool:
        if self.check_runtime_health():
            self._emit_item_status("runtime", "done", "Runtime already healthy")
            return False
        self._emit_stage(STAGE_PREPARING_RUNTIME, f"Preparing {runtime_variant} runtime...")
        self._prepare_runtime(runtime_variant)
        return True

    def repair_resources_if_needed(self, selected_features: Optional[Iterable[str]]) -> bool:
        plan = resolve_download_plan(self._normalize_features(selected_features))
        pending = [item for item in plan if not self._resource_item_available(item)]
        total_items = max(1, len(pending))
        if not pending:
            self._emit_item_status("resources", "done", "Resources already healthy")
            return False
        self._emit_stage(STAGE_DOWNLOADING, "Downloading required resources...")
        for index, resource in enumerate(pending, start=1):
            label = resource["filename"]
            self._emit_item_status(resource["resource_id"], "running", f"Preparing {label}")
            download_resource(
                resource,
                project_root=self._project_root,
                progress_cb=self._resource_progress_cb(index, total_items),
            )
            self._emit_item_status(resource["resource_id"], "done", f"{label} ready")
        return True

    def detect_runtime_selection(self, preferred_variant: str = "auto") -> RuntimeSelection:
        if sys.platform == "darwin":
            if preferred_variant in ("cpu", "mac"):
                return RuntimeSelection("mac", False, "macOS runtime")
            return RuntimeSelection("mac", False, "macOS runtime")

        detected_cuda = self._detect_cuda_capable()
        if preferred_variant == "cuda" and detected_cuda:
            return RuntimeSelection("cuda", True, "user requested CUDA")
        if preferred_variant == "cuda" and not detected_cuda:
            return RuntimeSelection("cpu", False, "CUDA unavailable, falling back to CPU")
        if preferred_variant == "cpu":
            return RuntimeSelection("cpu", detected_cuda, "user requested CPU")
        if detected_cuda:
            return RuntimeSelection("cuda", True, "detected NVIDIA/CUDA support")
        return RuntimeSelection("cpu", False, "default CPU runtime")

    def _run(self, options: dict, mode: str) -> None:
        try:
            selected_features = self._normalize_features(options.get("features"))
            self._save_config(
                initialization_in_progress=(mode == "init"),
                last_init_error=None,
            )

            runtime_choice = self.detect_runtime_selection(options.get("runtime_variant", "auto"))
            if mode == "init":
                self._save_config(
                    selected_runtime_variant=runtime_choice.variant,
                    detected_cuda_capable=runtime_choice.detected_cuda_capable,
                    enabled_feature_set=selected_features,
                )

            self._emit_stage(STAGE_PROBING, "Probing download sources...")
            self._source_map = self._resolve_best_sources(runtime_choice.variant)
            self._emit_item_status("source_probe", "done", f"PyPI -> {self._source_map['pypi_primary']}")
            self._emit_item_status("source_probe", "done", f"Torch -> {self._source_map['torch_primary']}")
            self._save_config(resolved_source_map=self._source_map)

            if options.get("auto_update_enabled", True):
                self._emit_stage(STAGE_CHECKING_UPDATES, "Checking updates...")
                self._check_updates_if_enabled()
            else:
                self._emit_item_status("updates", "skipped", "Automatic updates disabled by user")

            self.repair_runtime_if_needed(runtime_choice.variant)
            self.repair_resources_if_needed(selected_features)

            self._emit_stage(STAGE_VERIFYING, "Verifying resources...")
            if not self.is_ready_for_main_ui(selected_features):
                raise RuntimeError("Initialization completed with missing runtime or resources")

            success_updates: dict[str, object] = {"initialization_in_progress": False}
            if mode == "init":
                success_updates.update(
                    initialization_completed=True,
                    is_first_run=False,
                    downloaded_resources={
                        item["resource_id"]: True for item in resolve_download_plan(selected_features)
                    },
                )
            self._save_config(**success_updates)
            final_message = "Initialization completed" if mode == "init" else "Environment repair completed"
            self._emit_stage(STAGE_READY, final_message)
            self.finished.emit(
                True,
                {"runtime_variant": runtime_choice.variant, "source_map": self._source_map, "mode": mode},
            )
        except Exception as exc:
            self._save_config(initialization_in_progress=False, last_init_error=str(exc))
            self._emit_stage(STAGE_FAILED, str(exc))
            self.finished.emit(False, {"error": str(exc), "mode": mode})

    def _resource_progress_cb(self, item_index: int, total_items: int):
        def _callback(resource: dict, percent: float, message: str) -> None:
            overall = int((((item_index - 1) + (percent / 100.0)) / total_items) * 100)
            self.progress_changed.emit(overall, message, item_index - 1, total_items)
            self._emit_item_status(resource["resource_id"], "progress", message)
        return _callback

    def _emit_stage(self, stage: str, message: str) -> None:
        self.stage_changed.emit(stage, message)

    def _check_updates_if_enabled(self) -> None:
        try:
            from tools.update_checker import UpdateChecker

            checker = UpdateChecker()
            checker.check_for_updates()
            self._emit_item_status("updates", "done", "Update probe finished")
        except Exception as exc:
            # Initialization continues even if update probing fails.
            self._emit_item_status("updates", "warning", f"Update probe skipped: {exc}")

    def _resolve_best_sources(self, runtime_variant: str) -> Dict[str, str]:
        pypi_results = probe_sources("pypi", PIPY_SOURCES)
        best_pypi = pick_best_source(pypi_results)

        torch_sources = MAC_TORCH_SOURCES
        if runtime_variant == "cuda":
            torch_sources = CUDA_TORCH_SOURCES
        elif runtime_variant == "cpu":
            torch_sources = CPU_TORCH_SOURCES

        torch_results = probe_sources(f"torch-{runtime_variant}", torch_sources)
        best_torch = pick_best_source(torch_results)

        pypi_primary = best_pypi.url if best_pypi else PIPY_SOURCES[0]["url"]
        pypi_fallback = next(
            (source["url"] for source in PIPY_SOURCES if source["url"] != pypi_primary),
            pypi_primary,
        )
        torch_primary = best_torch.url if best_torch else torch_sources[0]["url"]
        torch_fallback = next(
            (source["url"] for source in torch_sources if source["url"] != torch_primary),
            torch_primary,
        )

        selected = {
            "pypi_primary": pypi_primary,
            "pypi_fallback": pypi_fallback,
            "torch_primary": torch_primary,
            "torch_fallback": torch_fallback,
        }
        return selected

    def _prepare_runtime(self, runtime_variant: str) -> None:
        python_cmd = self._resolve_python_command()
        if not self._runtime_dir.exists():
            self._run_subprocess([*python_cmd, "-m", "venv", str(self._runtime_dir)], "Create runtime venv")

        pip_executable = self._runtime_dir / ("Scripts" if os.name == "nt" else "bin") / ("pip.exe" if os.name == "nt" else "pip")
        requirements_file = self._project_root / RUNTIME_REQUIREMENTS[runtime_variant]
        install_cmd = [
            str(pip_executable),
            "install",
            "-r",
            str(requirements_file),
            "-i",
            self._source_map["pypi_primary"],
            "--extra-index-url",
            self._source_map["pypi_fallback"],
        ]
        if runtime_variant in ("cpu", "cuda"):
            install_cmd.extend(["--extra-index-url", self._source_map["torch_primary"]])
            if self._source_map["torch_fallback"] != self._source_map["torch_primary"]:
                install_cmd.extend(["--extra-index-url", self._source_map["torch_fallback"]])
        self._run_subprocess(install_cmd, f"Install {runtime_variant} runtime")
        self._inject_runtime_site_packages()
        self._verify_runtime_import(runtime_variant)

    def _run_subprocess(self, command: list[str], label: str) -> None:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            text = line.strip()
            if text:
                self.item_status_changed.emit("runtime", "progress", f"{label}: {text}")
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"{label} failed with exit code {return_code}")

    def _resolve_python_command(self) -> list[str]:
        if os.environ.get("VIRTUAL_ENV") and shutil.which("python"):
            return [shutil.which("python") or "python"]

        candidates = [
            [sys.executable] if sys.executable else None,
            [shutil.which("python3")] if shutil.which("python3") else None,
            [shutil.which("python")] if shutil.which("python") else None,
            ["py", "-3"] if shutil.which("py") else None,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                subprocess.run(
                    [*candidate, "-c", "import sys; print(sys.executable)"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True,
                )
                return candidate
            except Exception:
                continue
        raise RuntimeError("Unable to find a Python interpreter for runtime bootstrap")

    def _inject_runtime_site_packages(self) -> None:
        importlib.invalidate_caches()
        version_tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
        candidates = [
            self._runtime_dir / "Lib" / "site-packages",
            self._runtime_dir / "lib" / version_tag / "site-packages",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                if path not in sys.path:
                    sys.path.insert(0, path)

    def _verify_runtime_import(self, runtime_variant: str) -> None:
        try:
            importlib.invalidate_caches()
            torch_module = importlib.import_module("torch")
            torch_version = getattr(torch_module, "__version__", "unknown")
            self._emit_item_status("runtime", "done", f"Torch import OK: {torch_version} ({runtime_variant})")
        except Exception as exc:
            raise RuntimeError(f"Runtime installed but Torch import failed: {exc}") from exc

    def _runtime_import_ok(self) -> bool:
        try:
            self._inject_runtime_site_packages()
            importlib.invalidate_caches()
            importlib.import_module("torch")
            return True
        except Exception:
            return False

    def _has_runtime_available(self) -> bool:
        if importlib.util.find_spec("torch") is not None:
            return True
        self._inject_runtime_site_packages()
        return importlib.util.find_spec("torch") is not None

    def _resources_available(self, selected_features: Optional[Iterable[str]]) -> bool:
        features = self._normalize_features(selected_features)
        plan = resolve_download_plan(features)
        return all(self._resource_item_available(item) for item in plan if item.get("required") or selected_features)

    def _resource_item_available(self, item: dict) -> bool:
        path = self._project_root / item["dest_dir"] / item["filename"]
        return path.exists()

    def _detect_cuda_capable(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=4,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception:
            return False
