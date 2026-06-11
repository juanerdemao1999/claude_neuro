import pytest

from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.testing import make_synthetic_session, make_waveform_population_session


def test_validate_rejects_overlap_not_smaller_than_window() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")

    with pytest.raises(ValueError, match="`noverlap`"):
        validate_analysis_request(
            session,
            node,
            {
                "max_freq_hz": 200.0,
                "nperseg": 256,
                "noverlap": 256,
                "y_min_db": -120.0,
                "y_max_db": 10.0,
            },
        )


def test_validate_rejects_high_cutoff_above_nyquist() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:bandpass_preview:ch01")

    with pytest.raises(ValueError, match="Nyquist"):
        validate_analysis_request(
            session,
            node,
            {
                "low_hz": 4.0,
                "high_hz": 500.0,
                "order": 4,
                "preview_duration_s": 5.0,
            },
        )


def test_validate_rejects_non_positive_time_window() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:isi:unit_ch01_u01")

    with pytest.raises(ValueError, match="greater than 0"):
        validate_analysis_request(
            session,
            node,
            {
                "bin_size_ms": 0.0,
                "max_interval_ms": 200.0,
            },
        )


def test_validate_rejects_invalid_pac_frequency_ranges() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:pac:ch01")

    with pytest.raises(ValueError, match="phase_min_hz"):
        validate_analysis_request(
            session,
            node,
            {
                "phase_min_hz": 8.0,
                "phase_max_hz": 4.0,
                "phase_step_hz": 2.0,
                "phase_bandwidth_hz": 2.0,
                "amp_min_hz": 30.0,
                "amp_max_hz": 120.0,
                "amp_step_hz": 10.0,
                "amp_bandwidth_hz": 20.0,
                "phase_bins": 18,
                "filter_order": 4,
            },
        )


def test_validate_rejects_invalid_custom_plot_range() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")

    with pytest.raises(ValueError, match="plot_x_min"):
        validate_analysis_request(
            session,
            node,
            {
                "max_freq_hz": 120.0,
                "nperseg": 256,
                "noverlap": 128,
                "y_min_db": -120.0,
                "y_max_db": 10.0,
                "window_function": "hann",
                "welch_average": "mean",
                "plot_use_custom_x_range": True,
                "plot_x_min": 20.0,
                "plot_x_max": 10.0,
            },
        )


def test_validate_accepts_zero_low_cutoff_for_lfp_filters() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:bandpass_preview:ch01")

    validated = validate_analysis_request(
        session,
        node,
        {
            "low_hz": 0.0,
            "high_hz": 12.0,
            "order": 4,
            "preview_duration_s": 5.0,
        },
    )

    assert validated["low_hz"] == 0.0


def test_validate_rejects_psd_min_frequency_not_below_maximum() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:psd:ch01")

    with pytest.raises(ValueError, match="min_freq_hz"):
        validate_analysis_request(
            session,
            node,
            {
                "min_freq_hz": 50.0,
                "max_freq_hz": 50.0,
                "nperseg": 256,
                "noverlap": 128,
                "y_min_db": -120.0,
                "y_max_db": 10.0,
            },
        )


def test_validate_rejects_invalid_polar_tick_step() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_synthetic_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("lfp:pac_polar:ch01")

    with pytest.raises(ValueError, match="plot_polar_tick_step_deg"):
        validate_analysis_request(
            session,
            node,
            {
                "phase_min_hz": 2.0,
                "phase_max_hz": 12.0,
                "phase_step_hz": 2.0,
                "phase_bandwidth_hz": 2.0,
                "amp_min_hz": 30.0,
                "amp_max_hz": 120.0,
                "amp_step_hz": 10.0,
                "amp_bandwidth_hz": 20.0,
                "phase_bins": 18,
                "filter_order": 4,
                "plot_polar_tick_step_deg": 50,
            },
        )


def test_validate_rejects_duplicate_waveform_summary_axes() -> None:
    from nex5_analyzer.analysis.validation import validate_analysis_request

    session = make_waveform_population_session()
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    node = root.find_node("spike:waveform_characterization:summary")

    with pytest.raises(ValueError, match="summary_x_feature"):
        validate_analysis_request(
            session,
            node,
            {
                "summary_max_units": 250,
                "summary_x_feature": "half_width_ms",
                "summary_y_feature": "half_width_ms",
                "summary_z_feature": "firing_rate_hz",
            },
        )
