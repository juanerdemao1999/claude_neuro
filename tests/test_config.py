from pathlib import Path

from nex5_analyzer.config import SessionProfile


def test_session_profile_round_trip(tmp_path: Path) -> None:
    profile = SessionProfile.default()
    profile.channel_region_map = {2: "M1", 4: "S1"}
    profile.analysis_defaults["psd"]["max_freq_hz"] = 180.0
    profile.node_overrides["lfp:psd:ch02"] = {"max_freq_hz": 120.0}

    config_path = tmp_path / "profile.json"
    profile.save_json(config_path)

    restored = SessionProfile.load_json(config_path)

    assert restored.channel_region_map[2] == "M1"
    assert restored.analysis_defaults["psd"]["max_freq_hz"] == 180.0
    assert restored.node_overrides["lfp:psd:ch02"]["max_freq_hz"] == 120.0


def test_session_profile_round_trip_preserves_subject_region_mapping(tmp_path: Path) -> None:
    profile = SessionProfile.default()
    profile.channel_region_map = {
        2: {"subject": "Mouse A", "region": "M1"},
        4: {"subject": "Mouse B", "region": "S1"},
    }

    config_path = tmp_path / "profile_subjects.json"
    profile.save_json(config_path)

    restored = SessionProfile.load_json(config_path)

    assert restored.channel_region_map == profile.channel_region_map


def test_session_profile_resolved_params_use_analysis_defaults_for_all_nodes() -> None:
    profile = SessionProfile.default()
    profile.analysis_defaults["psd"]["max_freq_hz"] = 180.0
    profile.node_overrides["lfp:psd:ch02"] = {"max_freq_hz": 120.0}

    params_a = profile.resolved_params("psd", "lfp:psd:ch01")
    params_b = profile.resolved_params("psd", "lfp:psd:ch02")

    assert params_a["max_freq_hz"] == 180.0
    assert params_b["max_freq_hz"] == 180.0


def test_session_profile_uses_lfp_tuned_defaults_for_psd_and_spectrogram() -> None:
    profile = SessionProfile.default()

    assert profile.analysis_defaults["psd"]["min_freq_hz"] == 0.0
    assert profile.analysis_defaults["psd"]["max_freq_hz"] == 120.0
    assert profile.analysis_defaults["psd"]["nperseg"] == 1024
    assert profile.analysis_defaults["psd"]["noverlap"] == 768
    assert profile.analysis_defaults["psd"]["y_min_db"] == -70.0
    assert profile.analysis_defaults["psd"]["y_max_db"] == 0.0
    assert profile.analysis_defaults["psd"]["window_function"] == "hann"
    assert profile.analysis_defaults["psd"]["welch_average"] == "mean"
    assert profile.analysis_defaults["psd"]["detrend_mode"] == "constant"
    assert profile.analysis_defaults["psd"]["spectrum_scaling"] == "density"
    assert profile.analysis_defaults["psd"]["plot_line_width"] == 2.2
    assert profile.analysis_defaults["spectrogram"]["max_freq_hz"] == 120.0
    assert profile.analysis_defaults["spectrogram"]["nperseg"] == 1024
    assert profile.analysis_defaults["spectrogram"]["noverlap"] == 768
    assert profile.analysis_defaults["spectrogram"]["vmin_db"] == -80.0
    assert profile.analysis_defaults["spectrogram"]["vmax_db"] == -20.0
    assert profile.analysis_defaults["spectrogram"]["window_function"] == "hann"
    assert profile.analysis_defaults["spectrogram"]["detrend_mode"] == "constant"
    assert profile.analysis_defaults["spectrogram"]["spectrum_scaling"] == "density"
    assert profile.analysis_defaults["spectrogram"]["plot_colormap"] == "mako"
    assert profile.analysis_defaults["bandpass_preview"]["low_hz"] == 0.0
    assert profile.analysis_defaults["waveform_characterization"]["waveform_max_display"] == 0


def test_session_profile_from_dict_merges_partial_analysis_defaults_with_current_schema() -> None:
    profile = SessionProfile.from_dict(
        {
            "analysis_defaults": {
                "pac": {
                    "phase_min_hz": 4.0,
                }
            }
        }
    )

    assert profile.analysis_defaults["pac"]["phase_min_hz"] == 4.0
    assert profile.analysis_defaults["pac"]["phase_max_hz"] == 12.0
    assert profile.resolved_params("pac")["amp_max_hz"] == 120.0
