"""Native client build configuration tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import json
from pathlib import Path

from tools.build_client_bundle import build_bundle


ROOT = Path(__file__).parents[1]


def test_native_package_defines_android_ios_and_windows_scripts() -> None:
    """The native wrapper exposes build entry points for requested platforms."""
    package = json.loads((ROOT / "clients" / "native" / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]
    assert {
        "android:sync", "ios:sync", "macos:build:silicon",
        "macos:build:intel", "macos:build:universal", "windows:build",
    } <= set(scripts)
    assert "@capacitor/core" in package["dependencies"]
    assert "@tauri-apps/cli" in package["devDependencies"]


def test_tauri_windows_targets_are_configured() -> None:
    """Desktop packaging is configured for Windows installers and macOS DMG."""
    config = json.loads((ROOT / "clients" / "native" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert set(config["tauri"]["bundle"]["targets"]) == {"msi", "nsis", "dmg"}
    assert config["package"]["productName"] == "HGPExamWorkFlowAndChat"
    assert "macOS" in config["tauri"]["bundle"]


def test_client_bundle_writes_static_layout_and_api_base(tmp_path: Path) -> None:
    """The generated native web bundle preserves /static paths and API config."""
    build_bundle(tmp_path, "https://study.example.edu")
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "admin.html").exists()
    assert (tmp_path / "static" / "app.js").exists()
    config = (tmp_path / "static" / "client-config.js").read_text(encoding="utf-8")
    assert "https://study.example.edu" in config
