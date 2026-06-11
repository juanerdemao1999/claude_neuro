from __future__ import annotations

import sys
from pathlib import Path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    root = _runtime_root()
    src_dir = root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    from nex5_analyzer.app import main as launch_app

    preferred_files = [
        root / "NeuralDat072-01.nex5",
        root / "spike_sorting_curated.nex5",
    ]
    return launch_app(preferred_files=preferred_files, runtime_root=root)


if __name__ == "__main__":
    raise SystemExit(main())
