# NEX5 Analyzer Stabilization And Batch Plan

## Context
- Product priority: first make the tool stable and usable for the internal team.
- Sample files remain committed in the repository.
- The next version should deliver batch analysis.
- Current baseline:
  - single-file GUI workflow is already running end to end
  - core V1 analyses are implemented
  - automated test baseline exists and currently passes
  - real sample coverage exists for both spike-only and spike+LFP paths

## Current State Summary
### Already Working
- Single-file `.nex5` loading and metadata inspection.
- Channel-to-region mapping with JSON profile persistence.
- Analysis tree, preview, parameter editing, and figure/data export.
- Graceful degradation when LFP is absent.
- Basic automated tests for config, loader, analysis, export, and GUI smoke.

### Main Risks
- GUI compute tasks can race when users switch nodes quickly.
- Parameter validation is weak; invalid combinations are pushed to downstream libraries.
- Tests are too light for internal rollout confidence, especially for real-LFP and GUI flows.
- Documentation and repository hygiene are not yet ready for team onboarding.
- `AnalysisService` is growing into a monolith, which will slow batch-analysis delivery.

## Goal By Stage
### Stage 1
- Make current single-file workflow stable enough for internal daily use.

### Stage 2
- Establish regression protection and delivery discipline.

### Stage 3
- Refactor for maintainability so batch analysis can be added without destabilizing V1.

### Stage 4
- Deliver V2 batch analysis on top of the stabilized core.

## Execution Plan
### Phase 1: Internal Stability First
Priority: P0

#### Work Items
- Add request-versioning or cancellation logic for background analysis jobs in the workspace dialog.
- Prevent stale worker results from overwriting the latest selection.
- Add parameter guards before compute:
  - `noverlap < nperseg`
  - `low_hz < high_hz`
  - frequency limits must not exceed Nyquist-driven safe bounds
  - histogram/bin/window values must stay positive
- Improve user-facing error messages in Chinese for invalid parameter states and compute failures.
- Make export flow honor profile defaults where possible instead of relying only on hardcoded save suggestions.
- Verify startup path behavior with both in-repo samples and document which sample is auto-opened first.

#### Exit Criteria
- Rapid node switching does not produce mismatched previews.
- Common invalid parameter combinations are blocked before analysis starts.
- Internal users can complete load -> map -> analyze -> export without unexplained failures.

### Phase 2: Regression And Team Readiness
Priority: P0

#### Work Items
- Expand tests around the real LFP sample `NeuralDat072-01.nex5`.
- Add regression tests for:
  - mapping edits followed by session reload
  - apply/reset parameter behavior
  - export output shape and labeling
  - placeholder behavior with spike-only sample
  - representative spike-LFP and LFP-LFP outputs on real or synthetic fixtures
- Add a minimal CI workflow that runs `pytest`.
- Add `.gitignore` for Python cache and transient artifacts while keeping committed sample data explicitly intentional.
- Expand README with:
  - environment setup
  - launch instructions
  - sample-file roles
  - current supported analyses
  - known limitations

#### Exit Criteria
- New contributors can run the project from README alone.
- Every core workflow is covered by either real-data or synthetic regression tests.
- CI catches obvious breakage before internal sharing expands.

### Phase 3: Batch-Oriented Refactor
Priority: P1

#### Work Items
- Split `AnalysisService` into domain modules:
  - `lfp`
  - `spike`
  - `lfp_lfp`
  - `spike_lfp`
- Introduce an analysis registry so each analysis declares:
  - key
  - label
  - parameter spec
  - compute handler
  - export semantics
  - availability rules
- Separate UI orchestration from analysis execution concerns.
- Add a reusable batch-safe execution layer that can run analyses without GUI state.
- Define batch job output schema:
  - output directory structure
  - per-file summary
  - figure naming
  - CSV naming
  - failure log format

#### Exit Criteria
- Single-file GUI and future batch execution both call the same analysis backend.
- Adding one new analysis no longer requires touching multiple unrelated files.

### Phase 4: V2 Batch Analysis Delivery
Priority: P1

#### Scope
- Enable visible batch-analysis section in the main window.
- Select input directory and output directory.
- Reuse one JSON profile across files.
- Run selected analyses across multiple `.nex5` files.
- Export figures and CSV outputs per file and per analysis.
- Produce a batch summary report with success/failure status.

#### Recommended V2 Boundaries
- Support sequential execution first.
- Keep event-aligned and behavior-aligned workflows deferred.
- Do not introduce multi-file aggregation analytics in the first batch version unless explicitly needed.
- Fail one file without aborting the whole batch.

#### Exit Criteria
- Users can point the app at a folder of `.nex5` files and receive deterministic exports plus a run summary.
- Batch mode reuses the same validated profile and analysis codepath as single-file mode.

## Backlog Order
1. Fix compute-race and stale-preview issues.
2. Add parameter validation and clearer GUI errors.
3. Strengthen real-data regression coverage.
4. Add CI and repository hygiene.
5. Refactor analysis registration and execution boundaries.
6. Implement batch execution backend.
7. Implement batch GUI and summary reporting.

## Non-Goals For The Next Version
- Event-aligned analysis.
- Behavior-aligned analysis.
- Time-window workflow presets.
- PAC, Granger, or formal cell-type classification.
- Journal-specific figure theming beyond the current publication baseline.

## Notes On Keeping Large Samples In Repo
- This is acceptable for the current internal-use phase.
- Team discipline should treat these files as stable fixtures, not casual scratch inputs.
- Derived artifacts such as preview PNGs, exports, and caches should stay ignored.

## Recommended Immediate Next Task
- Implement Phase 1 completely before adding any new user-visible feature except small usability fixes required by that phase.
