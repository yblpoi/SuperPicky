#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual regression checker for residual patch cleanup.

用于手工验证“残留 code_updates + 初始化关闭自动更新”场景的回归检查脚本。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.initialization_manager import (
    InitializationManager,
    RuntimeInstallLocation,
    RuntimeSelection,
)
from constants import APP_VERSION
from tools import patch_manager


def _create_residual_patch_environment(config_dir: Path) -> tuple[Path, Path]:
    patch_dir = config_dir / "code_updates"
    meta_path = config_dir / "patch_meta.json"
    (patch_dir / "core").mkdir(parents=True, exist_ok=True)
    (patch_dir / "core" / "legacy_override.py").write_text(
        "PATCH_MARKER = 'stale-overlay'\n",
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps(
            {
                "patch_version": "v-stale",
                "base_version": APP_VERSION,
                "release_channel": "official",
                "target_channels": ["official"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return patch_dir, meta_path


def run_manual_regression_check() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        config_dir = temp_root / "config"
        runtime_dir = temp_root / "runtime"
        config_dir.mkdir(parents=True, exist_ok=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        patch_dir, meta_path = _create_residual_patch_environment(config_dir)

        print(f"[setup] residual patch dir: {patch_dir}")
        print(f"[setup] residual patch meta: {meta_path}")
        print(f"[guard] source patch block reason: {patch_manager.get_patch_runtime_block_reason()}")

        manager = InitializationManager()
        update_events: list[tuple[str, str, str]] = []

        def _record_item(resource_id: str, status: str, detail: str) -> None:
            if resource_id == "updates":
                update_events.append((resource_id, status, detail))
                print(f"[updates] {status}: {detail}")

        with patch.object(patch_manager, "get_app_config_dir", return_value=config_dir), patch.object(
            patch_manager, "shared_get_patch_dir", return_value=patch_dir
        ), patch.object(
            manager,
            "choose_runtime_install_location",
            return_value=RuntimeInstallLocation("default", runtime_dir, None, True),
        ), patch.object(
            manager,
            "detect_runtime_selection",
            return_value=RuntimeSelection("cpu", False, "manual-check"),
        ), patch.object(
            manager,
            "_normalize_features",
            side_effect=lambda features: list(features or ["core_detection"]),
        ), patch.object(manager, "_save_config"), patch.object(
            manager,
            "_resolve_best_sources",
            return_value={
                "pypi_primary": "https://example.invalid/simple",
                "pypi_fallback": "",
                "torch_primary": "",
                "torch_fallback": "",
            },
        ), patch.object(manager, "repair_runtime_if_needed"), patch.object(
            manager, "repair_resources_if_needed"
        ), patch.object(manager, "is_ready_for_main_ui", return_value=True), patch.object(
            manager, "_raise_if_cancelled"
        ), patch.object(manager, "_emit_stage"), patch.object(
            manager, "_emit_item_status", side_effect=_record_item
        ):
            manager._run(
                {
                    "features": ["core_detection"],
                    "auto_update_enabled": False,
                    "runtime_variant": "cpu",
                    "runtime_install_location": "default",
                },
                mode="repair",
            )

        if patch_dir.exists() or meta_path.exists():
            print("[result] FAILED: residual patch artifacts still exist")
            return 1

        if not any(status == "done" and "补丁环境已清除" in detail for _, status, detail in update_events):
            print("[result] FAILED: patch cleanup event was not emitted")
            return 1

        if not any(status == "skipped" and "Automatic updates disabled by user" in detail for _, status, detail in update_events):
            print("[result] FAILED: auto-update disabled event was not emitted")
            return 1

        print("[result] PASS: residual patch environment was cleared during disabled-update initialization")
        return 0


if __name__ == "__main__":
    raise SystemExit(run_manual_regression_check())