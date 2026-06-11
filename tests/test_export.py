from pathlib import Path

import pandas as pd

from nex5_analyzer.analysis.service import AnalysisService
from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.exporters import export_result_data, export_result_figure
from nex5_analyzer.models import AnalysisResult
from nex5_analyzer.testing import make_synthetic_session


def test_exporters_write_png_svg_and_csv(tmp_path: Path) -> None:
    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")
    result = AnalysisService().compute(session, node, profile, {})

    png_path = tmp_path / "result.png"
    svg_path = tmp_path / "result.svg"
    csv_path = tmp_path / "result.csv"

    export_result_figure(result, png_path)
    export_result_figure(result, svg_path)
    export_result_data(result, csv_path)

    assert png_path.exists()
    assert svg_path.exists()
    assert csv_path.exists()


def test_export_heatmap_csv_preserves_row_and_column_labels(tmp_path: Path) -> None:
    csv_path = tmp_path / "matrix.csv"
    result = AnalysisResult(
        node_id="matrix",
        title="Matrix",
        kind="heatmap",
        export_table=pd.DataFrame(
            [[1.0, 0.5], [0.5, 1.0]],
            index=pd.Index(["M1", "S1"], name="region"),
            columns=["M1", "S1"],
        ),
    )

    export_result_data(result, csv_path)

    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "region,M1,S1"
