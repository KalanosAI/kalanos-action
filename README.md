# Kalanos Dataset Audit for GitHub Actions

**Audit robot recordings in your existing CI pipeline, before the next training run.**

Run the open-source [Kalanos grader](https://github.com/KalanosAI/kalanos) on files already available to your runner. Produce a fresh JSON audit and fail the workflow when episodes are blocked, need review, or lack required evidence.

## Where it fits

```text
Record or retrieve data
        ↓
Your existing validation / conversion
        ↓
Kalanos CLI audit → JSON report + deterministic exit status
        ↓
Pass configured decision gate? → Your existing training job
```

For robotics teams with LeRobot exports, sensor recordings, private storage, or self-hosted training infrastructure. The workflow decides how to fetch or mount data. This action accepts local paths only.

### What the integration adds

- One reusable Action rather than each team maintaining CLI installation and error handling.
- A fresh grader run, not a lookup of an existing Hub report.
- Explicit configuration for scope, mappings, gate statuses and execution tier.
- Separate policy failure from operational errors.
- Local report and diagnostic logs, plus an **optional** aggregate GitHub job summary.
- Support for preinstalled, internally pinned environments and private self-hosted runners.

## Add it to a workflow

Add the Action to a workflow:

```yaml
name: Audit robotics data
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@v4
      # Insert your existing dataset preparation step here.
      - name: Audit prepared recordings
        id: audit
        uses: KalanosAI/kalanos-action@v1   # pin a full commit SHA in production
        with:
          path: ./recordings
          version: '0.9.3'
          fail-on: blocked,review,unknown
          job-summary: 'true'
      # Run training only after the audit succeeds.
      # - run: your-existing-training-command
```

The Action uses the real CLI contract:

```bash
kalanos grade /absolute/local/path \
  --report /absolute/output/audit.json \
  --fail-on blocked,review,unknown --no-color
```

It does not alter recordings, select or delete episodes, retrain a policy, or call an AI model.

### Private or preinstalled setup

Use the team's approved runner and existing installation. Python 3.10+ and the executable must be available. The wrapper itself uses Python 3.10+.

```yaml
jobs:
  audit:
    runs-on: [self-hosted, linux, robotics-data]
    timeout-minutes: 40
    steps:
      - uses: KalanosAI/kalanos-action@v1   # pin a full commit SHA in production
        id: audit
        with:
          path: /mnt/approved-datasets/current-batch
          install: 'false'
          executable: /opt/kalanos/bin/kalanos
          profile: /opt/kalanos/config/robot-scope.yaml
          map-file: /opt/kalanos/config/signal-map.yaml
          fail-on: blocked,review,unknown
          job-summary: 'false'
```

Your runner preparation handles storage credentials, mounts, downloads, and dependency installation. Do not pass a dataset URL to this Action. For fully reproducible installs, build and approve a locked runner image or use an internally supplied, hash-verified wheelhouse, then set `install: false`.

## Configuration

| Input | Default | Purpose |
|---|---|---|
| `path` | required | Existing local file or dataset directory |
| `version` | `0.9.3` | Exact release installed from configured pip index |
| `install` | `true` | Isolated venv installation; false leaves installation to you |
| `executable` | `kalanos` | CLI path/name in preinstalled mode |
| `extras` | empty | Comma-separated `hdf5,mcap,numeric,video,hf,all` |
| `profile` | empty | Built-in name or local bundle; empty uses CLI numeric-core default |
| `map-file` | empty | Local feature mapping file |
| `tier` | empty | CLI default; optionally `metadata`, `standard`, `full` |
| `fail-on` | `blocked,review,unknown` | Statuses that fail the grader gate |
| `hash-source` | `false` | Ask CLI to check local source bytes before/after grading |
| `no-sidecar` | `false` | Ignore dataset-side mapping file |
| `timeout-seconds` | `1800` | Grading limit, excluding installation |
| `job-summary` | `false` | Opt into sending aggregate counts to GitHub |

Base package reads text formats and LeRobot directories. HDF5/MCAP readers and numeric/video diagnostics may need extras. Missing required capabilities can produce unknown decisions. A lighter tier does **not** reduce required evidence. Full tier can be expensive.

`version` and `extras` do not change preinstalled mode. The report's producer field records the actual grader version.

## Outputs and failure handling

| Output | Meaning |
|---|---|
| `status` | `pass`, `fail`, or `error` |
| `exit-code` | 0 = configured gate passed; 1 = decision gate failed; 2 = configuration/operational/wrapper error |
| `report-path` | Local JSON audit path, only set if produced |
| `output-directory` | Local folder holding `audit.json`, `grader.log`, `result.json`; install mode also stores its venv and install log |

Output directories use unique names to avoid overwriting an earlier run. The action fails its step on exit 1 or 2. A completed CLI run without valid, nonempty decision counts is treated as a wrapper error, never a pass.

No artifact upload is performed. If your security policy allows storing reports in GitHub, add this explicitly after the audit:

```yaml
- name: Retain approved audit report
  if: ${{ always() && steps.audit.outputs.report-path != '' }}
  uses: actions/upload-artifact@v4
  with:
    name: kalanos-audit
    path: ${{ steps.audit.outputs.report-path }}
    retention-days: 7
```

Do not upload the entire output directory: it may contain private paths/evidence in logs and an installation environment. Do not use `continue-on-error` for a required training gate unless you explicitly enforce the result downstream.

## Decision semantics, not a magic score cutoff

The grader owns the gate. The Action does not reinterpret scores or introduce a second policy engine.

- `pass`: required evidence satisfies the chosen scope; report-only problems may still exist.
- `review`: inspect or validate the evidence.
- `blocked`: an authorized blocking consequence exists.
- `unknown`: evidence is missing or unavailable.
- Including `unknown` also gates an incomplete inventory.
- `fail-on: blocked` is an intentionally looser exploratory policy. Do not call it a strict training gate.

A passing audit does not prove task success, robot safety, dataset sufficiency or training performance. A low score does not by itself fail the gate: the gate follows decision statuses, so report-only findings can remain on a passing audit.

## Privacy and runner security

The wrapper calls the local grader, never MCP or `--publish`. It removes `KALANOS_API_KEY` from the grader process and keeps raw CLI output in local logs. GitHub receives the step's generic status; decision counts go to GitHub only if you enable the summary. Reports are not automatically uploaded.

This is **not** an egress sandbox or a guarantee that no information leaves the machine. Package installation uses the configured package index; GitHub manages workflow status/logs; dependencies, custom adapters, runner configuration, credentials and data references require review. The inspected official CLI only invokes Hub publication when explicitly requested, but the entire dependency/plugin graph has not been network-audited.

For sensitive datasets: use a trusted, ephemeral self-hosted runner, preinstalled locked dependencies, deny-by-default network policy, read-only mounts, and controlled retention. Never run untrusted pull-request code on a persistent private-data runner. Avoid `pull_request_target` with untrusted checkout content. Review configuration bundles and plugins as code/trusted inputs. A local-path check is not a filesystem sandbox.

The default install pins Kalanos but does **not** lock all transitive dependencies. Pin third-party GitHub Actions, including this one, to reviewed commit SHAs in production workflows. This Action pins its own `setup-python` dependency to a commit SHA.

## Known limitations

- Only JSON report export is implemented. Large reports are loaded to validate aggregate counts, so memory scales with report size.
- A timeout terminates the direct grader process. Use ephemeral runners with job-level timeouts and resource isolation for all descendants.
- Output files on a private runner remain until your cleanup policy removes them.
- Verified against Kalanos 0.8.0 and 0.9.3. The `version` input is exact, so you choose when to upgrade.

## Develop and verify

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
```

See [VALIDATION.md](VALIDATION.md) for what has and has not been verified.

## License and security

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Report suspected vulnerabilities privately as described in [SECURITY.md](SECURITY.md). For other questions or reports, email [reports@kalanos.ai](mailto:reports@kalanos.ai). Third-party product and project names identify compatibility only, and this project is not affiliated with, sponsored by or endorsed by their owners.

[Kalanos website](https://kalanos.ai) · [Data Hub](https://hub.kalanos.ai) · [Public grader](https://github.com/KalanosAI/kalanos)
