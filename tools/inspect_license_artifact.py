from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from nex5_analyzer.licensing import format_license_artifact_inspection, inspect_license_artifact_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an activation key or signed license JSON and explain how it is decoded."
    )
    parser.add_argument(
        "--path",
        type=Path,
        help="Path to a .key/.json/.txt artifact. If omitted, --text or stdin is used.",
    )
    parser.add_argument(
        "--text",
        help="Paste an activation key or license JSON directly on the command line.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the inspection result as JSON.",
    )
    return parser.parse_args()


def _read_source_text(args: argparse.Namespace) -> str:
    if args.path is not None:
        return args.path.read_text(encoding="utf-8")
    if args.text:
        return args.text
    text = sys.stdin.read()
    if text.strip():
        return text
    raise SystemExit("Provide --path, --text, or pipe an activation key/license JSON on stdin.")


def main() -> int:
    args = parse_args()
    inspection = inspect_license_artifact_text(_read_source_text(args))

    if args.json:
        print(json.dumps(inspection.as_dict(), indent=2, ensure_ascii=False))
        return 0

    print(format_license_artifact_inspection(inspection))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
