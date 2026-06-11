# NEX5 Spike/LFP Analyzer

Desktop GUI for single-file `.nex5` spike and LFP analysis with configurable brain-region mapping, interactive previews, and exportable figures/data.

## UI Notes

- The UI now uses a lightweight desktop workspace layout with unified Chinese labels, clearer status feedback, and a shared light theme.
- The main window focuses on three steps only: load sample, finish brain-region mapping, then run single-file or batch analysis.
- The analysis workspace keeps a simple three-column layout: analysis tree, preview, and parameter panel.

## Environment Setup

1. Install Python 3.12 on Windows.
2. Install project dependencies:

```powershell
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -e .[dev]
```

## Launch

- Windows quick start: `run_gui.bat`
- Python entry: `py -3.12 launch_gui.py`

## Offline Licensing

The app supports `offline activation key + machine binding`.

Customer-facing flow:

- The program reads `license_public_key.pem` from the application directory.
- First launch without a valid license opens an activation dialog.
- The dialog shows a 64-character machine code.
- The customer sends that machine code to you.
- You generate an activation key file for that exact machine code.
- The customer pastes the key or imports the `.key` file.
- If the program is copied to another computer, the machine code changes and the old key fails.

Recommended owner flow:

1. Open the key generator:

```powershell
py -3.12 tools\license_generator_app.py
```

2. On first run, it creates `.secrets\license_private_key.pem` and `license_public_key.pem`.

3. Rebuild once after the public key exists:

```powershell
build_exe.bat
```

4. Ask the customer to send the machine code shown by the activation dialog.

5. Paste the machine code into the key generator and click `生成密钥文件`.

6. Send the generated `.key` file to the customer.

Command-line alternative:

```powershell
py -3.12 tools\generate_offline_license.py `
  --private-key .secrets\license_private_key.pem `
  --customer "Customer Name" `
  --fingerprint "<machine code>" `
  --license-id "LIC-2026-001" `
  --expires-at "2027-04-12T00:00:00+00:00" `
  --feature desktop `
  --feature batch `
  --output .\out\activation.key
```

Notes:

- Keep `license_private_key.pem` offline and never ship it with the program.
- `license_public_key.pem` is safe to ship and is included in the PyInstaller bundle when placed in the project root before build.
- Licenses are stored locally under the user's home directory in `.nex5_analyzer\license.json`.

Reuse pattern:

- Treat the license as a fixed protocol, not as a one-off script.
- Keep the outer transport stable: `prefix + base64url + JSON`.
- Put differences into embedded protocol metadata such as `profile_id`, `product`, `schema_version`, and `signature_algorithm`.
- Reuse one inspector instead of keeping many ad-hoc decode scripts:

```powershell
py -3.12 tools\inspect_license_artifact.py --path .\out\activation.key
```

- The inspector will tell you which profile the artifact uses and the exact decode / verify steps.

## Batch Analysis

- Batch mode now runs from the main window.
- Select:
  - an input directory containing `.nex5` files
  - an output directory for exported results
- Choose the specific analysis items to run from the batch picker before starting.
- Batch execution is blocked until the currently loaded sample has a complete brain-region mapping.
- Batch execution takes a snapshot of the current in-memory profile when the run starts.
  - If you want a fixed reusable profile across sessions, load or save the JSON profile first.
- Every file in the batch must match the currently loaded sample's logical channel layout.
  - Files with mismatched logical channels or incomplete region mapping are reported as failures instead of running silently with reused mappings.
- Current batch behavior:
  - sequential execution
  - live progress text plus a progress bar in the main window
  - one file or task can fail without aborting the whole run
  - outputs are written per input file
  - summary files are written to the batch output root

## Samples

- Continuous-channel auto-detection:
  - when a `.nex5` file contains multiple continuous sampling rates, the loader treats only the lowest-rate continuous channels as LFP inputs
  - higher-rate continuous channels are ignored by the LFP analysis tree
- Channel mapping:
  - region mapping uses sequential logical channel indices rather than raw recorder numbering
  - non-contiguous raw channels such as `48, 52, 60` are normalized to logical channels `1, 2, 3`
  - spike units and LFP channels that share the same raw channel are mapped to the same logical channel and therefore the same brain region
  - customers enter mappings in a dedicated dialog using inclusive ranges such as `1-4 -> M1`
  - every logical channel must be covered before analysis can continue; partial mappings are rejected
- `NeuralDat072-01.nex5`
  - preferred launcher sample
  - contains both spike units and LFP channels
  - useful for validating LFP, LFP-LFP, and spike-LFP workflows
- `spike_sorting_curated.nex5`
  - spike-only sample
  - useful for validating graceful degradation when LFP is absent

## Sample Auto-Load Behavior

- The launcher prefers `NeuralDat072-01.nex5` when it exists.
- If that file is absent, it falls back to `spike_sorting_curated.nex5`.

## Supported Analyses

- LFP
  - PSD
  - spectrogram
  - band-pass preview
  - band power vs time
- Spike
  - waveform characterization
  - firing rate
  - ISI histogram
  - autocorrelation
  - cross-correlation
- LFP-LFP
  - pairwise coherence
  - region summary matrix
- Spike-LFP
  - spike-triggered average
  - spike-field coherence
  - phase locking / phase histogram / PLV

## Parameter Editing

- Analysis parameters are edited per analysis type, not per individual node.
- Example: changing `PSD` parameters on `ch01` also updates `PSD` for `ch02`, `ch03`, and the rest of the PSD nodes.
- Reset also resets the whole analysis type back to its default values.

## Testing

- Run the automated test suite with:

```powershell
pytest -q
```

- The repository now includes a minimal GitHub Actions workflow that runs `pytest` on `windows-latest`.

## Known Limitations

- Interactive analysis workspace is still single-file oriented.
- Batch execution is available, but only as a first sequential version.
- Event-aligned, behavior-aligned, and time-window analyses are deferred.
- Real sample coverage now exists for both spike-only and spike+LFP paths, but broader internal validation is still recommended before wider rollout.
