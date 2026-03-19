#!/usr/bin/env python3
"""Lightweight structural checks for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT_DIR / ".github" / "workflows"


class WorkflowCheckError(RuntimeError):
    """Raised when a workflow does not match the expected release structure."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorkflowCheckError(f"Missing workflow file: {path}") from exc


def ensure_contains(content: str, needle: str, *, path: Path) -> None:
    if needle not in content:
        raise WorkflowCheckError(f"{path}: missing required snippet: {needle}")


def ensure_in_order(content: str, snippets: list[str], *, path: Path) -> None:
    position = -1
    for snippet in snippets:
        next_position = content.find(snippet, position + 1)
        if next_position == -1:
            raise WorkflowCheckError(f"{path}: missing ordered snippet: {snippet}")
        position = next_position


def check_build_release() -> None:
    path = WORKFLOWS_DIR / "build-release.yml"
    content = read_text(path)

    required_snippets = [
        "name: Build and Release SuperPicky CPU",
        "workflow_dispatch:",
        "env:",
        "GITCODE_TOKEN: ${{ secrets.GITCODE_TOKEN }}",
        "GITCODE_REPO_URL: ${{ secrets.GITCODE_REPO_URL }}",
        "id: release_meta",
        "name: Create build virtual environment",
        "name: Install CPU build dependencies",
        ".\\.venv\\Scripts\\python.exe -m pip install requests",
        "name: Build CPU release payloads",
        "name: Create CPU installer with Inno Setup",
        "name: Prepare release assets",
        "output/SuperPicky_Win64_*_cpu.zip",
        "output/installer_cpu/Output/SuperPicky_Setup_Win64_*.exe",
        "name: Create GitHub Release",
        "release_assets/*",
        "name: Upload assets to GitCode Release",
        "if: env.GITCODE_TOKEN != '' && env.GITCODE_REPO_URL != ''",
        "GITCODE_RELEASE_NAME: ${{ steps.release_meta.outputs.name }}",
        "scripts\\upload_to_gitcode.py",
    ]
    for snippet in required_snippets:
        ensure_contains(content, snippet, path=path)

    ensure_in_order(
        content,
        [
            "name: Checkout repository",
            "name: Set up Python 3.12",
            "name: Resolve release metadata",
            "name: Create build virtual environment",
            "name: Install CPU build dependencies",
            "name: Build CPU release payloads",
            "name: Create CPU installer with Inno Setup",
            "name: Prepare release assets",
            "name: Create GitHub Release",
            "name: Upload assets to GitCode Release",
        ],
        path=path,
    )


def check_build_cuda_patch() -> None:
    path = WORKFLOWS_DIR / "build-cuda-patch.yml"
    content = read_text(path)

    required_snippets = [
        "name: Build and Release SuperPicky Windows",
        "push:",
        "tags:",
        "workflow_dispatch:",
        "env:",
        "GITCODE_TOKEN: ${{ secrets.GITCODE_TOKEN }}",
        "GITCODE_REPO_URL: ${{ secrets.GITCODE_REPO_URL }}",
        "id: release_meta",
        "name: Create build virtual environment",
        "name: Install build dependencies",
        ".\\.venv\\Scripts\\python.exe -m pip install requests",
        "name: Build CPU and CUDA patch release payloads",
        "build_release_win.py --build-type cuda-patch --copy-dir output --debug",
        "name: Create CPU installer with Inno Setup",
        "name: Create CUDA patch installer with Inno Setup",
        "name: Prepare release assets",
        "output/SuperPicky_Win64_*_cpu.zip",
        "output/installer_cpu/Output/SuperPicky_Setup_Win64_*.exe",
        "output/cuda_patch_installer/Output/SuperPicky_CUDA_Patch_Win64_*.exe",
        "output/SuperPicky_Win64_*_cuda_patch.zip",
        "name: Create GitHub Release",
        "release_assets/*",
        "name: Upload assets to GitCode Release",
        "if: env.GITCODE_TOKEN != '' && env.GITCODE_REPO_URL != ''",
        "GITCODE_RELEASE_NAME: ${{ steps.release_meta.outputs.name }}",
        "GITCODE_TAG: ${{ steps.release_meta.outputs.tag }}",
        "scripts\\upload_to_gitcode.py",
    ]
    for snippet in required_snippets:
        ensure_contains(content, snippet, path=path)

    ensure_in_order(
        content,
        [
            "name: Checkout repository",
            "name: Set up Python 3.12",
            "name: Resolve release metadata",
            "name: Create build virtual environment",
            "name: Install build dependencies",
            "name: Build CPU and CUDA patch release payloads",
            "name: Create CPU installer with Inno Setup",
            "name: Create CUDA patch installer with Inno Setup",
            "name: Prepare release assets",
            "name: Create GitHub Release",
            "name: Upload assets to GitCode Release",
        ],
        path=path,
    )


def main() -> int:
    try:
        check_build_release()
        check_build_cuda_patch()
    except WorkflowCheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Workflow checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
