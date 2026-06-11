# 2026-03-25 Initial Implementation

## What Changed
- Created a new Python project scaffold with `pyproject.toml`, package source tree, and test suite.
- Added core data models for sessions, channels, spike units, analysis nodes, and analysis results.
- Implemented JSON profile loading/saving with:
  - `channel_region_map`
  - `analysis_defaults`
  - `node_overrides`
  - `enabled_analyses`
  - `export_defaults`
  - `input_defaults.manual_channel_ids`
- Implemented `.nex5` header inspection and lazy data loading with `nex5file`.
- Added name-based and metadata-based channel parsing.
- Added synthetic-data helpers for repeatable analysis testing.
- Implemented analysis tree generation for:
  - LFP
  - Spike
  - LFP-LFP
  - Spike-LFP
- Implemented V1 analysis functions:
  - FFT
  - PSD
  - spectrogram
  - band-pass preview
  - band power
  - waveform characterization
  - firing rate
  - ISI
  - auto/cross-correlation
  - coherence
  - region summary
  - spike-triggered average
  - spike-field coherence
  - phase locking
- Added matplotlib-based figure export and CSV data export.
- Added a PySide6 main window and analysis workspace dialog with pyqtgraph preview and background workers.
- Added a single Windows launcher entry:
  - `run_gui.bat` as the user-facing entry point
  - `launch_gui.py` as the Python bootstrapper
  - launcher auto-loads `NeuralDat072-01.nex5` first when present
- Replaced the hand-built preview/export plotting path with an open-source publication-oriented stack:
  - `seaborn` high-level plotting API
  - `SciencePlots` publication styles
  - `matplotlib` canvas for GUI preview and figure export

## Why
- This establishes the first end-to-end GUI loop for single-file `.nex5` analysis.
- The implementation keeps batch-analysis and richer neuroscience modules open for later phases without blocking V1.
- Lazy loading is used so large `.nex5` files do not need to fully materialize into memory before the user starts working.

## Validation
- Added automated tests for:
  - profile round-trip
  - channel parsing
  - sample header inspection
  - region inheritance
  - PSD behavior on synthetic data
  - ISI output
  - placeholder tree behavior when LFP is missing
  - figure/data export
  - GUI smoke tests
- Verified the real sample file loads with 36 spike units and waveform support.
- Verified firing-rate computation on a real unit from the sample file.
- Verified publication-style PSD export on the real LFP sample file.

## Known Gaps
- The current sample file has no LFP channels, so LFP workflows are verified through synthetic data rather than a real in-repo LFP example.
- Batch execution UI is reserved but not implemented yet.
- Event/behavior/time-window analyses are not part of V1.
- PAC, Granger, and formal neuron-type classification remain deferred.
- The current publication theme is generic scientific styling, not yet a lab-specific or journal-specific figure template.
