# -*- coding: utf-8 -*-
"""
Packaged runtime bootstrap helper.

This entrypoint is designed for frozen Windows lightweight builds. It runs in a
separate hidden process mode of the packaged executable and installs runtime
dependencies into an app-local site-packages directory without relying on any
system Python interpreter.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runtime-bootstrap", action="store_true")
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--index-url", default=None)
    parser.add_argument("--extra-index-url", action="append", default=[])
    return parser.parse_args(argv)


def _ensure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _build_pip_args(args: argparse.Namespace, site_packages_dir: Path) -> list[str]:
    """
    Build the pip command line for the packaged runtime bootstrap.

    为打包运行时引导流程构建 pip 命令行参数。
    """
    pip_args = [
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--no-cache-dir",
        "--progress-bar",
        "raw",
        "--use-deprecated=legacy-certs",
        "--upgrade",
        "--target",
        str(site_packages_dir),
        "-r",
        str(Path(args.requirements).resolve()),
    ]
    if args.index_url:
        pip_args.extend(["-i", args.index_url])
    for extra_index_url in args.extra_index_url:
        pip_args.extend(["--extra-index-url", extra_index_url])
    return pip_args


def _write_manifest(runtime_dir: Path, site_packages_dir: Path, args: argparse.Namespace) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_dir": str(runtime_dir),
        "site_packages_dir": str(site_packages_dir),
        "requirements": str(Path(args.requirements).resolve()),
        "index_url": args.index_url,
        "extra_index_urls": list(args.extra_index_url),
        "python_version": sys.version,
        "bootstrap_executable": sys.executable,
    }
    manifest_path = runtime_dir / "runtime_install_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _bundled_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        return Path(meipass)
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return Path(sys.executable).resolve().parent / "_internal"
    return Path(__file__).resolve().parent.parent


def _configure_ca_bundle() -> Path | None:
    cert_path = _bundled_root() / "certifi" / "cacert.pem"
    if not cert_path.exists():
        return None
    os.environ.setdefault("PIP_CERT", str(cert_path))
    os.environ.setdefault("SSL_CERT_FILE", str(cert_path))
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(cert_path))
    return cert_path


def _patch_pip_for_frozen_bootstrap() -> None:
    """
    Patch pip vendored distlib so it can run from a PyInstaller-frozen process.
    """
    os.environ.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    os.environ.setdefault("PIP_USE_DEPRECATED", "legacy-certs")
    cert_path = _configure_ca_bundle()

    from pip._vendor.distlib import resources as distlib_resources

    distlib_pkg = importlib.import_module("pip._vendor.distlib")
    loader = getattr(distlib_pkg, "__loader__", None)
    if loader is not None:
        finder_registry = getattr(distlib_resources, "_finder_registry", {})
        if type(loader) not in finder_registry:
            distlib_resources.register_finder(loader, distlib_resources.ResourceFinder)

    import pip._internal.cli.index_command as pip_index_command
    import pip._vendor.certifi as pip_certifi
    import pip._vendor.distlib.scripts as distlib_scripts

    if not getattr(distlib_scripts.ScriptMaker.__init__, "_superpicky_patched", False):
        original_init = distlib_scripts.ScriptMaker.__init__

        def _patched_init(self, source_dir, target_dir, add_launchers=True, dry_run=False, fileop=None):
            return original_init(
                self,
                source_dir,
                target_dir,
                add_launchers=False,
                dry_run=dry_run,
                fileop=fileop,
            )

        _patched_init._superpicky_patched = True  # type: ignore[attr-defined]
        distlib_scripts.ScriptMaker.__init__ = _patched_init

    pip_index_command._create_truststore_ssl_context = lambda: None
    if cert_path is not None:
        pip_certifi.where = lambda: str(cert_path)


def run_runtime_bootstrap(argv: list[str]) -> int:
    _ensure_utf8_stdio()
    args = _parse_args(argv)
    runtime_dir = Path(args.runtime_dir).resolve()
    site_packages_dir = runtime_dir / "site-packages"
    site_packages_dir.mkdir(parents=True, exist_ok=True)

    _patch_pip_for_frozen_bootstrap()

    from pip._internal.cli.main import main as pip_main

    pip_args = _build_pip_args(args, site_packages_dir)
    print(f"[runtime-bootstrap] target={site_packages_dir}")
    exit_code = int(pip_main(pip_args))
    if exit_code != 0:
        return exit_code

    if str(site_packages_dir) not in sys.path:
        sys.path.insert(0, str(site_packages_dir))

    import torch  # noqa: F401

    _write_manifest(runtime_dir, site_packages_dir, args)
    print("[runtime-bootstrap] torch import verified")
    return 0