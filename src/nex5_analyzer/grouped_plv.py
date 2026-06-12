from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t

from .analysis.runtime import AnalysisRuntime
from .analysis.spike_lfp import phase_locking_metrics
from .config import SessionProfile
from .exporters import export_result_figure
from .io.nex5_loader import Nex5SessionLoader
from .models import AnalysisNode, AnalysisResult, LFPChannel, SessionData, SpikeUnit


@dataclass(frozen=True, slots=True)
class GroupedPLVManifestEntry:
    file_path: Path
    group: str
    subject: str | None = None
    region: str | None = None


@dataclass(frozen=True, slots=True)
class GroupedPLVFailure:
    file_path: Path
    group: str
    subject: str | None
    message: str


@dataclass(frozen=True, slots=True)
class GroupedPLVParams:
    low_hz: float = 4.0
    high_hz: float = 12.0
    phase_bins: int = 18
    filter_order: int = 4
    min_spikes_per_unit: int = 5
    align_preferred_phase: bool = True
    same_region_only: bool = True
    ci_level: float = 0.95

    def validated(self) -> "GroupedPLVParams":
        if self.low_hz <= 0.0:
            raise ValueError("Parameter `low_hz` must be greater than 0.")
        if self.high_hz <= 0.0:
            raise ValueError("Parameter `high_hz` must be greater than 0.")
        if self.low_hz >= self.high_hz:
            raise ValueError("Parameter `low_hz` must be smaller than `high_hz`.")
        if self.phase_bins < 6:
            raise ValueError("Parameter `phase_bins` must be at least 6.")
        if self.filter_order <= 0:
            raise ValueError("Parameter `filter_order` must be greater than 0.")
        if self.min_spikes_per_unit <= 0:
            raise ValueError("Parameter `min_spikes_per_unit` must be greater than 0.")
        if not 0.0 < self.ci_level < 1.0:
            raise ValueError("Parameter `ci_level` must be between 0 and 1.")
        return self

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "GroupedPLVParams":
        defaults = cls()
        if not payload:
            return cls()
        return cls(
            low_hz=float(payload.get("low_hz", defaults.low_hz)),
            high_hz=float(payload.get("high_hz", defaults.high_hz)),
            phase_bins=int(payload.get("phase_bins", defaults.phase_bins)),
            filter_order=int(payload.get("filter_order", defaults.filter_order)),
            min_spikes_per_unit=int(payload.get("min_spikes_per_unit", defaults.min_spikes_per_unit)),
            align_preferred_phase=bool(payload.get("align_preferred_phase", defaults.align_preferred_phase)),
            same_region_only=bool(payload.get("same_region_only", defaults.same_region_only)),
            ci_level=float(payload.get("ci_level", defaults.ci_level)),
        )

    def phase_locking_params(self) -> dict[str, Any]:
        return {
            "low_hz": float(self.low_hz),
            "high_hz": float(self.high_hz),
            "phase_bins": int(self.phase_bins),
            "filter_order": int(self.filter_order),
        }


@dataclass(slots=True)
class GroupedPLVRunResult:
    preview_result: AnalysisResult
    unit_level: pd.DataFrame = field(default_factory=pd.DataFrame)
    subject_level: pd.DataFrame = field(default_factory=pd.DataFrame)
    group_level: pd.DataFrame = field(default_factory=pd.DataFrame)
    failures: list[GroupedPLVFailure] = field(default_factory=list)
    manifest_entries: list[GroupedPLVManifestEntry] = field(default_factory=list)
    params: GroupedPLVParams = field(default_factory=GroupedPLVParams)


class GroupedPLVRunner:
    def __init__(self, loader: Any | None = None) -> None:
        self.loader = loader or Nex5SessionLoader()

    def load_manifest(
        self,
        manifest_path: str | Path,
        *,
        base_dir: str | Path | None = None,
    ) -> list[GroupedPLVManifestEntry]:
        manifest_path = Path(manifest_path)
        frame = pd.read_csv(manifest_path)
        required_columns = {"file_path", "group"}
        missing_columns = sorted(required_columns.difference(frame.columns))
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"Manifest CSV is missing required column(s): {missing}.")

        resolved_base_dir = Path(base_dir) if base_dir is not None else manifest_path.parent
        entries: list[GroupedPLVManifestEntry] = []
        for index, row in enumerate(frame.to_dict(orient="records"), start=1):
            raw_file_path = str(row.get("file_path", "")).strip()
            raw_group = str(row.get("group", "")).strip()
            if not raw_file_path:
                raise ValueError(f"Manifest row {index} is missing `file_path`.")
            if not raw_group:
                raise ValueError(f"Manifest row {index} is missing `group`.")
            file_path = Path(raw_file_path)
            if not file_path.is_absolute():
                file_path = (resolved_base_dir / file_path).resolve()
            entries.append(
                GroupedPLVManifestEntry(
                    file_path=file_path,
                    group=raw_group,
                    subject=_optional_text(row.get("subject")),
                    region=_optional_text(row.get("region")),
                )
            )
        return entries

    def run(
        self,
        manifest_path: str | Path,
        profile: SessionProfile,
        params: GroupedPLVParams | dict[str, Any] | None = None,
        *,
        base_dir: str | Path | None = None,
    ) -> GroupedPLVRunResult:
        entries = self.load_manifest(manifest_path, base_dir=base_dir)
        return self.run_entries(entries, profile, params=params)

    def run_entries(
        self,
        entries: list[GroupedPLVManifestEntry],
        profile: SessionProfile,
        params: GroupedPLVParams | dict[str, Any] | None = None,
    ) -> GroupedPLVRunResult:
        resolved_params = (
            params.validated()
            if isinstance(params, GroupedPLVParams)
            else GroupedPLVParams.from_mapping(params).validated()
        )
        unit_rows: list[dict[str, object]] = []
        unit_curve_rows: list[dict[str, object]] = []
        failures: list[GroupedPLVFailure] = []
        phase_params = resolved_params.phase_locking_params()

        for entry in entries:
            try:
                session = self.loader.inspect(entry.file_path, region_map=profile.channel_region_map)
            except Exception as exc:
                failures.append(
                    GroupedPLVFailure(
                        file_path=entry.file_path,
                        group=entry.group,
                        subject=entry.subject,
                        message=str(exc),
                    )
                )
                continue

            subject_label = self._resolve_subject_label(entry, session)
            runtime = AnalysisRuntime(session)
            pair_count = 0
            for unit, channel, region_label in self._iter_unit_lfp_pairs(session, entry, resolved_params):
                node = AnalysisNode(
                    node_id=f"grouped_plv:{subject_label}:{unit.slug}__{channel.slug}",
                    label=f"{unit.display_name} vs {channel.display_name}",
                    kind="leaf",
                    source_refs={"spike": unit.variable_name, "lfp": channel.variable_name},
                )
                metrics = _phase_metrics_for_pair(runtime, node, phase_params)
                if metrics.get("error_message"):
                    continue
                if int(metrics["spike_count"]) < resolved_params.min_spikes_per_unit:
                    continue
                pair_count += 1
                pair_id = f"{entry.file_path.name}:{unit.variable_name}:{channel.variable_name}"
                histogram_phase_values = _center_phase_values(
                    np.asarray(metrics["phase_values"], dtype=float),
                    float(metrics["mean_angle"]),
                ) if resolved_params.align_preferred_phase else np.asarray(metrics["phase_values"], dtype=float)
                probabilities, centers_deg = _normalized_histogram(histogram_phase_values, resolved_params.phase_bins)
                unit_rows.append(
                    {
                        "file_path": str(entry.file_path),
                        "group": entry.group,
                        "subject": subject_label,
                        "region": region_label,
                        "unit": unit.display_name,
                        "lfp_channel": channel.display_name,
                        "spike_variable": unit.variable_name,
                        "lfp_variable": channel.variable_name,
                        "spike_count": int(metrics["spike_count"]),
                        "plv": float(metrics["plv"]),
                        "ppc": float(metrics["ppc"]),
                        "preferred_phase_rad": float(metrics["mean_angle"]),
                        "preferred_phase_deg": float(np.degrees(metrics["mean_angle"])),
                        "rayleigh_z": float(metrics["rayleigh_z"]),
                        "rayleigh_p": float(metrics["rayleigh_p"]),
                        "kappa": float(metrics["kappa"]),
                        "aligned_to_preferred_phase": bool(resolved_params.align_preferred_phase),
                    }
                )
                for phase_deg, probability in zip(centers_deg, probabilities, strict=False):
                    unit_curve_rows.append(
                        {
                            "group": entry.group,
                            "subject": subject_label,
                            "region": region_label,
                            "phase_deg": float(phase_deg),
                            "probability": float(probability),
                            "pair_id": pair_id,
                        }
                    )

            if pair_count == 0:
                failures.append(
                    GroupedPLVFailure(
                        file_path=entry.file_path,
                        group=entry.group,
                        subject=subject_label,
                        message="No valid unit-LFP pairs met the minimum spike-count threshold.",
                    )
                )

        if not unit_rows or not unit_curve_rows:
            raise ValueError("No valid unit-LFP pairs found for grouped PLV analysis.")

        unit_level = pd.DataFrame(unit_rows).sort_values(["group", "subject", "region", "unit", "lfp_channel"]).reset_index(drop=True)
        unit_curves = pd.DataFrame(unit_curve_rows).sort_values(["group", "subject", "region", "phase_deg"]).reset_index(drop=True)
        subject_level = _build_subject_level(unit_curves)
        group_level = _build_group_level(subject_level, resolved_params.ci_level)
        preview_result = _build_preview_result(group_level, resolved_params, len(failures))
        return GroupedPLVRunResult(
            preview_result=preview_result,
            unit_level=unit_level,
            subject_level=subject_level,
            group_level=group_level,
            failures=failures,
            manifest_entries=list(entries),
            params=resolved_params,
        )

    def export_run(self, result: GroupedPLVRunResult, output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "figure": export_result_figure(result.preview_result, output_dir / "grouped_plv.png"),
            "unit_level": output_dir / "unit_level.csv",
            "subject_level": output_dir / "subject_level.csv",
            "group_level": output_dir / "group_level.csv",
        }
        result.unit_level.to_csv(paths["unit_level"], index=False)
        result.subject_level.to_csv(paths["subject_level"], index=False)
        result.group_level.to_csv(paths["group_level"], index=False)
        if result.failures:
            failure_path = output_dir / "failures.csv"
            pd.DataFrame(
                [
                    {
                        "file_path": str(failure.file_path),
                        "group": failure.group,
                        "subject": failure.subject or "",
                        "message": failure.message,
                    }
                    for failure in result.failures
                ]
            ).to_csv(failure_path, index=False)
            paths["failures"] = failure_path
        return paths

    def _resolve_subject_label(self, entry: GroupedPLVManifestEntry, session: SessionData) -> str:
        if entry.subject:
            return entry.subject
        if len(session.subject_names) == 1:
            return session.subject_names[0]
        return session.file_path.stem

    def _iter_unit_lfp_pairs(
        self,
        session: SessionData,
        entry: GroupedPLVManifestEntry,
        params: GroupedPLVParams,
    ) -> list[tuple[SpikeUnit, LFPChannel, str]]:
        selected_region = _optional_text(entry.region)
        has_any_region_mapping = any(
            str(item.region or "").strip()
            for item in [*session.spike_units, *session.lfp_channels]
        )
        pairs: list[tuple[SpikeUnit, LFPChannel, str]] = []
        for unit in session.spike_units:
            for channel in session.lfp_channels:
                if selected_region:
                    if has_any_region_mapping:
                        if str(unit.region or "").strip() != selected_region:
                            continue
                        if str(channel.region or "").strip() != selected_region:
                            continue
                    pairs.append((unit, channel, selected_region))
                    continue

                if params.same_region_only:
                    if unit.region_scope is not None and channel.region_scope is not None:
                        if unit.region_scope != channel.region_scope:
                            continue
                        pairs.append((unit, channel, channel.region_label))
                        continue
                    if unit.region_scope is not None or channel.region_scope is not None:
                        continue
                pairs.append((unit, channel, channel.region_label if channel.region_label else "All Regions"))
        return pairs


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _phase_metrics_for_pair(runtime: AnalysisRuntime, node: AnalysisNode, params: dict[str, Any]) -> dict[str, object]:
    cache_key = (
        "grouped_plv",
        node.source_refs["spike"],
        node.source_refs["lfp"],
        float(params["low_hz"]),
        float(params["high_hz"]),
        int(params["filter_order"]),
    )

    def factory() -> dict[str, object]:
        from .analysis.spike_lfp import _shared_phase_locking_state

        return _shared_phase_locking_state(runtime, node, params)

    state = runtime.cache_get_or_create(cache_key, factory)
    if state.get("error_message"):
        return {"error_message": state["error_message"]}
    return phase_locking_metrics(np.asarray(state["phase_values"], dtype=float))


def _center_phase_values(phase_values: np.ndarray, mean_angle: float) -> np.ndarray:
    centered = np.asarray(phase_values, dtype=float) - float(mean_angle)
    return ((centered + np.pi) % (2.0 * np.pi)) - np.pi


def _normalized_histogram(phase_values: np.ndarray, phase_bins: int) -> tuple[np.ndarray, np.ndarray]:
    counts, edges = np.histogram(np.asarray(phase_values, dtype=float), bins=int(phase_bins), range=(-np.pi, np.pi))
    total = max(int(counts.sum()), 1)
    centers_deg = np.degrees((edges[:-1] + edges[1:]) / 2.0)
    return counts.astype(float) / float(total), centers_deg.astype(float)


def _build_subject_level(unit_curves: pd.DataFrame) -> pd.DataFrame:
    if unit_curves.empty:
        return pd.DataFrame(columns=["group", "subject", "region", "phase_deg", "mean_probability", "unit_count"])
    subject_level = (
        unit_curves.groupby(["group", "subject", "region", "phase_deg"], as_index=False)
        .agg(
            mean_probability=("probability", "mean"),
            unit_count=("pair_id", "nunique"),
        )
        .sort_values(["group", "subject", "region", "phase_deg"])
        .reset_index(drop=True)
    )
    return subject_level


def _build_group_level(subject_level: pd.DataFrame, ci_level: float) -> pd.DataFrame:
    if subject_level.empty:
        return pd.DataFrame(columns=["group", "region", "phase_deg", "mean", "ci_low", "ci_high", "n_subjects", "n_units", "series"])

    subject_summary = (
        subject_level.groupby(["group", "region", "subject"], as_index=False)
        .agg(unit_count=("unit_count", "max"))
    )
    count_summary = (
        subject_summary.groupby(["group", "region"], as_index=False)
        .agg(
            n_subjects=("subject", "nunique"),
            n_units=("unit_count", "sum"),
        )
    )

    rows: list[dict[str, object]] = []
    half_alpha = (1.0 + float(ci_level)) / 2.0
    for (group, region, phase_deg), subset in subject_level.groupby(["group", "region", "phase_deg"], sort=True):
        values = subset["mean_probability"].to_numpy(dtype=float)
        n_subjects = int(subset["subject"].nunique())
        mean_value = float(np.mean(values))
        if n_subjects >= 2:
            sem = float(np.std(values, ddof=1) / np.sqrt(n_subjects))
            margin = float(t.ppf(half_alpha, df=n_subjects - 1) * sem)
            ci_low = mean_value - margin
            ci_high = mean_value + margin
        else:
            ci_low = np.nan
            ci_high = np.nan
        rows.append(
            {
                "group": group,
                "region": region,
                "phase_deg": float(phase_deg),
                "mean": mean_value,
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        )

    group_level = pd.DataFrame(rows).merge(count_summary, on=["group", "region"], how="left")
    multiple_regions = group_level["region"].astype(str).nunique() > 1
    group_level["series"] = [
        _series_label(str(group), str(region), multiple_regions)
        for group, region in zip(group_level["group"], group_level["region"], strict=False)
    ]
    return group_level.sort_values(["series", "phase_deg"]).reset_index(drop=True)


def _series_label(group: str, region: str, multiple_regions: bool) -> str:
    region_text = str(region or "").strip()
    if multiple_regions and region_text:
        return f"{group} | {region_text}"
    return group


def _build_preview_result(group_level: pd.DataFrame, params: GroupedPLVParams, failure_count: int) -> AnalysisResult:
    if group_level.empty:
        return AnalysisResult(
            node_id="grouped_plv:summary",
            title="Grouped PLV",
            kind="message",
            message="当前没有可用于绘制分组 PLV 极坐标图的数据。",
        )

    group_count = int(group_level["group"].nunique()) if not group_level.empty else 0
    region_count = int(group_level["region"].astype(str).nunique()) if not group_level.empty else 0
    subtitle_parts = [
        f"{group_count} 个分组",
        "已按首选相位对齐" if params.align_preferred_phase else "原始相位",
    ]
    if failure_count:
        subtitle_parts.append(f"跳过 {failure_count} 个文件")
    subtitle = " | ".join(subtitle_parts)

    if region_count <= 1:
        region_label = str(group_level["region"].iloc[0])
        return _build_region_preview_result(group_level, region_label, subtitle)

    panels = [
        _build_region_preview_result(region_frame.copy(), str(region_label), subtitle)
        for region_label, region_frame in group_level.groupby("region", sort=True)
    ]
    return AnalysisResult(
        node_id="grouped_plv:summary",
        title="Grouped PLV Polar",
        kind="composite",
        export_table=group_level.copy(),
        panels=panels,
        meta={
            "layout": _composite_layout(len(panels)),
            "subtitle": subtitle,
        },
    )


def _build_region_preview_result(group_level: pd.DataFrame, region_label: str, subtitle: str) -> AnalysisResult:
    plot_frame = pd.DataFrame(
        {
            "theta_rad": np.mod(np.deg2rad(group_level["phase_deg"].to_numpy(dtype=float)), 2.0 * np.pi),
            "radius": group_level["mean"].to_numpy(dtype=float),
            "ci_low": group_level["ci_low"].to_numpy(dtype=float),
            "ci_high": group_level["ci_high"].to_numpy(dtype=float),
            "series": group_level["group"].astype(str).to_numpy(),
            "phase_deg": group_level["phase_deg"].to_numpy(dtype=float),
            "n_subjects": group_level["n_subjects"].to_numpy(dtype=int),
            "n_units": group_level["n_units"].to_numpy(dtype=int),
            "region": group_level["region"].astype(str).to_numpy(),
        }
    ).sort_values(["series", "theta_rad"]).reset_index(drop=True)
    if region_label and region_label != "All Regions":
        title = f"Grouped PLV Polar - {region_label}"
    else:
        title = "Grouped PLV Polar"
    return AnalysisResult(
        node_id=f"grouped_plv:summary:{region_label}",
        title=title,
        kind="polar",
        export_table=plot_frame,
        meta={
            "subtitle": subtitle,
            "show_legend": True,
            "line_width": 2.2,
            "band_alpha": 0.10,
            "polar_fill_alpha": 0.12,
            "polar_zero_location": "E",
            "polar_direction": "counterclockwise",
            "polar_tick_step_deg": 90,
            "polar_tick_label_mode": "pi",
            "polar_chart_style": "line_fill",
            "show_polar_grid": True,
            "show_metrics_box": False,
        },
    )


def _composite_layout(panel_count: int) -> dict[str, int]:
    if panel_count <= 1:
        return {"rows": 1, "cols": 1}
    if panel_count == 2:
        return {"rows": 1, "cols": 2}
    cols = 2
    rows = int(np.ceil(panel_count / cols))
    return {"rows": rows, "cols": cols}
