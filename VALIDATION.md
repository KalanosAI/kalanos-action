# Validation record

What has been verified, and what has not. Update this file when you re-verify.

## Verified
- 23 unit tests plus 1 default-version consistency test pass on CPython 3.10.20 and 3.12.3
  (Linux x86_64). They cover input validation, pass/fail/error propagation, unknown exit
  statuses, timeouts, missing or malformed reports, output isolation, version/extras/tier
  validation, the optional job summary, and install failure.
- The wrapper was run against the **real grader**, installed from PyPI, for `kalanos` 0.8.0
  and 0.9.3 (report schema 7.1.0 and 8.0.0) on a small synthetic CSV recording and a
  deliberately defective one:
  - clean recording: status `pass`, exit 0, counts total 1 / pass 1;
  - defective recording (duplicate timestamps, NaNs): status `fail`, exit 1, counts unknown 1;
  - empty folder: status `error`, exit 2.
- The isolated-venv install path (`install: true`) installed the exact pinned release and
  graded successfully.
- Every CLI flag the wrapper passes exists in `kalanos grade --help` for 0.8.0:
  `--report`, `--fail-on`, `--no-color`, `--profile`, `--map-file`, `--tier`,
  `--hash-source`, `--no-sidecar`. The wrapper never passes `--publish` or `--api-key`.
- Workflow and action YAML parse; the patch applies to an empty repository.

## Not verified
- Execution of the composite Action on GitHub-hosted runners, including whether Action
  outputs remain readable after a failed step. The `Real grader smoke` workflow asserts this;
  run it before relying on the `report-path` upload recipe.
- Windows and macOS runners, and a private self-hosted runner image.
- Egress and telemetry of the full dependency graph; large reports; training effects.
- Optional extras (`hdf5`, `mcap`, `numeric`, `video`, `hf`, `all`) on real datasets.
