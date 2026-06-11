# Batch Output Schema

## Goal
- Reuse the single-file analysis backend for batch execution.
- Make per-file outputs deterministic and easy to inspect.
- Allow one file to fail without invalidating the entire batch run.

## Proposed Layout

```text
<batch-output-root>/
  run_summary.csv
  failures.csv
  <input-file-stem>/
    figures/
      <analysis-node-id>.png
      <analysis-node-id>.svg
    data/
      <analysis-node-id>.csv
```

## Naming Rules
- `<input-file-stem>`: original `.nex5` file name without extension.
- `<analysis-node-id>`: sanitized node id generated from the analysis tree.
- The same session + profile + selected analyses should always produce the same relative output paths.

## Summary Files
### `run_summary.csv`
- one row per successful analysis task
- recommended columns:
  - `file_name`
  - `analysis_key`
  - `node_id`
  - `figure_png`
  - `figure_svg`
  - `data_csv`
  - `status`

### `failures.csv`
- one row per failed analysis task
- recommended columns:
  - `file_name`
  - `analysis_key`
  - `node_id`
  - `status`
  - `error_message`

## Execution Rules
- Batch mode should continue after a single-task failure.
- The summary files should be written even when some tasks fail.
- Exported files should be grouped by input file first, then by artifact type.

## Current Backend Mapping
- `BatchAnalysisTask.output_stem` is the canonical sanitized task stem.
- `BatchAnalysisRunner` is the batch-safe backend entry point.
- GUI batch mode should orchestrate file selection and progress, but should not own compute logic.
