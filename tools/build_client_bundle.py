# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Build the static client bundle used by Android, iOS, and Windows shells."""

import argparse
import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEFAULT_OUTPUT = ROOT / "clients" / "native" / "www"


def build_bundle(output: Path, api_base: str) -> None:
    """Copy frontend assets and write the native app API configuration."""
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    static = output / "static"
    static.mkdir()
    for source in FRONTEND.iterdir():
        if source.is_file():
            target_dir = output if source.suffix == ".html" else static
            shutil.copy2(source, target_dir / source.name)
    (static / "client-config.js").write_text(
        "/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */\n"
        f"window.HCP_CLIENT_CONFIG = {json.dumps({'apiBase': api_base}, indent=2)};\n"
        "(() => {\n"
        "  const originalFetch = window.fetch.bind(window);\n"
        "  window.fetch = (input, init) => {\n"
        "    const base = window.HCP_CLIENT_CONFIG.apiBase || \"\";\n"
        "    if (base && typeof input === \"string\" && input.startsWith(\"/api/\")) return originalFetch(`${base}${input}`, init);\n"
        "    return originalFetch(input, init);\n"
        "  };\n"
        "})();\n",
        encoding="utf-8",
    )


def main() -> None:
    """Parse command-line arguments and create the native client web bundle."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=os.environ.get("HCP_API_BASE", ""), help="HTTPS API origin, for example https://study.example.edu")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_bundle(args.output, args.api_base.rstrip("/"))


if __name__ == "__main__":
    main()
