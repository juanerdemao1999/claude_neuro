# NEX5 Spike/LFP Analyzer V1 Requirements

## Product Goal
- Build a Windows-first desktop GUI for single-file `.nex5` analysis.
- Support spike, waveform, LFP, and combined spike-LFP workflows.
- Allow channel-to-region mapping so every spike unit inherits the region of its parent channel.

## Confirmed Decisions
- Spike sorting is already finished outside this application.
- GUI language is Chinese; default figure titles and axes remain in English.
- V1 supports one `.nex5` file at a time.
- Event-aligned, behavior-aligned, and time-segment analyses are deferred.
- Batch analysis is deferred, but the UI and configuration format must reserve a path for it.
- Parameter editing uses global defaults plus per-node overrides.
- Configuration is stored in one JSON profile file.

## Required Screens
### Main Window
- Load a single `.nex5` file.
- Show core metadata:
  - file name
  - duration
  - timestamp frequency
  - LFP channel count
  - spike unit count
  - waveform availability
  - recognized channels
- Show and edit channel-to-region mappings.
- Allow loading and saving a single JSON profile.
- Reserve a visible but non-functional batch-analysis section.

### Analysis Workspace Dialog
- Show an analysis-first tree.
- Preview one plot at a time.
- Allow parameter editing in the preview workflow.
- Support Apply/Recompute, Reset to Global Default, Export Figure, and Export Data.

## V1 Analysis Coverage
### LFP
- PSD (Welch)
- Spectrogram
- Band-pass preview
- Band power vs time

### Spike
- Waveform characterization
- Firing rate
- ISI histogram
- Autocorrelation
- Cross-correlation

### LFP-LFP
- Pairwise coherence
- Region summary matrix

### Spike-LFP
- Spike-triggered average
- Spike-field coherence
- Spike-LFP phase locking / phase histogram / PLV

## Data And Mapping Rules
- Channel ID is resolved in this order:
  1. header/wire metadata
  2. variable-name parsing
  3. manual correction in the GUI
- Region mapping is channel based.
- Every unit under a channel inherits the same region.
- If a source cannot be assigned to a channel, region-dependent analyses stay unavailable until corrected.

## Export Rules
- Figures export to PNG and SVG.
- Data exports to CSV.
- Curve results export in long-table style.
- Heatmap and matrix results export with row/column labels when possible.

## Current Sample Observation
- The workspace sample `spike_sorting_curated.nex5` currently contains spike units and waveforms.
- It does not contain LFP channels, so the application must degrade gracefully when LFP data is absent.
