import itertools
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NEX5 = ROOT / "spike_sorting_curated.nex5"
LFP_SAMPLE_NEX5 = ROOT / "NeuralDat072-01.nex5"
TEST_TMP_ROOT = Path(tempfile.gettempdir()) / "nex5-pytest-local" / str(os.getpid())
TMP_COUNTER = itertools.count()


@pytest.fixture(scope="session")
def sample_nex5_path() -> Path:
    return SAMPLE_NEX5


@pytest.fixture(scope="session")
def lfp_sample_nex5_path() -> Path:
    return LFP_SAMPLE_NEX5


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def tmp_path() -> Path:
    path = TEST_TMP_ROOT / f"case_{next(TMP_COUNTER)}"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path
