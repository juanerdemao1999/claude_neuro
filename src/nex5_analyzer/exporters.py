from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from .models import AnalysisResult
from .plotting import create_publication_figure


def export_result_figure(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    figure = create_publication_figure(result)
    try:
        figure.savefig(path, dpi=300, bbox_inches="tight")
    finally:
        figure.clear()
    return path


def export_result_data(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    if result.export_table.empty:
        result.export_table.assign(message=[result.message or "No data"]).to_csv(path, index=False)
    else:
        preserve_index = result.kind == "heatmap" and result.export_table.index.name is not None
        result.export_table.to_csv(path, index=preserve_index)
    return path
