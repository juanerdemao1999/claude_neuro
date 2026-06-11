from nex5_analyzer.analysis.service import AnalysisService
from nex5_analyzer.analysis.tree import AnalysisTreeBuilder
from nex5_analyzer.config import SessionProfile
from nex5_analyzer.io.nex5_loader import Nex5SessionLoader


def test_real_lfp_sample_supports_representative_lfp_and_spike_lfp_analyses(lfp_sample_nex5_path) -> None:
    session = Nex5SessionLoader().inspect(lfp_sample_nex5_path)
    profile = SessionProfile.default()
    root = AnalysisTreeBuilder().build(session, profile)
    service = AnalysisService()

    psd_result = service.compute(session, root.find_node("lfp:psd:ch01"), profile, {})
    pac_result = service.compute(session, root.find_node("lfp:pac:ch01"), profile, {})
    coherence_result = service.compute(session, root.find_node("lfp_lfp:coherence:ch01__ch02"), profile, {})
    sta_result = service.compute(session, root.find_node("spike_lfp:sta:unit_ch01_u00__ch01"), profile, {})

    assert not psd_result.export_table.empty
    assert {"frequency_hz", "power", "power_db"}.issubset(psd_result.export_table.columns)

    assert not pac_result.export_table.empty
    assert pac_result.export_table.index.name == "amplitude_frequency_hz"
    assert pac_result.export_table.columns.name == "phase_frequency_hz"

    assert not coherence_result.export_table.empty
    assert {"frequency_hz", "coherence"}.issubset(coherence_result.export_table.columns)

    assert not sta_result.export_table.empty
    assert {"lag_ms", "amplitude"}.issubset(sta_result.export_table.columns)
