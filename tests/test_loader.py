from types import SimpleNamespace

from nex5_analyzer.io.nex5_loader import (
    Nex5SessionLoader,
    build_sequential_channel_map,
    extract_channel_id,
    infer_preferred_lfp_sampling_rate,
    is_preferred_lfp_sampling_rate,
)


def test_extract_channel_id_prefers_header_and_falls_back_to_name() -> None:
    assert extract_channel_id("CH3_Unit1", header_wire=7) == 7
    assert extract_channel_id("CH12_Unit2_wf", header_wire=0) == 12
    assert extract_channel_id("LFP_31", header_wire=None) == 31
    assert extract_channel_id("unit_without_channel", header_wire=None) is None


def test_loader_prefers_lowest_continuous_sampling_rate_for_lfp_detection() -> None:
    variables = [
        SimpleNamespace(header=SimpleNamespace(SamplingRate=30000.0)),
        SimpleNamespace(header=SimpleNamespace(SamplingRate=1000.0)),
        SimpleNamespace(header=SimpleNamespace(SamplingRate=1000.0)),
    ]

    preferred_rate = infer_preferred_lfp_sampling_rate(variables)

    assert preferred_rate == 1000.0
    assert is_preferred_lfp_sampling_rate(1000.0, preferred_rate) is True
    assert is_preferred_lfp_sampling_rate(30000.0, preferred_rate) is False


def test_loader_reindexes_non_contiguous_raw_channels_to_sequential_ids() -> None:
    assert build_sequential_channel_map([48, 52, 60]) == {48: 1, 52: 2, 60: 3}
    assert build_sequential_channel_map([32, 48, 49, 50]) == {32: 1, 48: 2, 49: 3, 50: 4}


def test_loader_inspects_sample_headers(sample_nex5_path) -> None:
    session = Nex5SessionLoader().inspect(sample_nex5_path)

    assert session.file_path == sample_nex5_path
    assert session.spike_units
    assert session.waveform_available is True
    assert session.lfp_channels == []
    assert session.metadata["timestamp_frequency_hz"] == 30000.0
    assert session.spike_units[0].channel_id is not None


def test_region_mapping_resolves_units_from_channel(sample_nex5_path) -> None:
    session = Nex5SessionLoader().inspect(sample_nex5_path)
    updated = session.with_region_map({2: "M1", 3: "S1"})

    labels = {unit.name: unit.region for unit in updated.spike_units if unit.channel_id in {2, 3}}

    assert any(region == "M1" for region in labels.values())
    assert any(region == "S1" for region in labels.values())


def test_region_mapping_assigns_subject_and_region(sample_nex5_path) -> None:
    session = Nex5SessionLoader().inspect(sample_nex5_path)
    updated = session.with_region_map(
        {
            2: {"subject": "Mouse A", "region": "M1"},
            3: {"subject": "Mouse B", "region": "S1"},
        }
    )

    assignments = {
        unit.name: (unit.subject, unit.region)
        for unit in updated.spike_units
        if unit.channel_id in {2, 3}
    }

    assert ("Mouse A", "M1") in assignments.values()
    assert ("Mouse B", "S1") in assignments.values()


def test_loader_inspects_real_lfp_sample_headers(lfp_sample_nex5_path) -> None:
    session = Nex5SessionLoader().inspect(lfp_sample_nex5_path)

    assert session.file_path == lfp_sample_nex5_path
    assert len(session.lfp_channels) == 16
    assert len(session.spike_units) >= 1
    assert session.channel_ids == list(range(1, 17))
    assert {channel.sample_rate_hz for channel in session.lfp_channels} == {1000.0}
    assert all(channel.variable_name.startswith("LFP") for channel in session.lfp_channels)
    assert session.lfp_channels[0].channel_id is not None
    assert session.spike_units[0].channel_id is not None
    first_channel_units = [unit for unit in session.spike_units if unit.channel_id == 1]
    assert first_channel_units
