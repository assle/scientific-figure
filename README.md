<p align="center">
  <img src="assets/banner.svg" alt="Scientific Figure Builder" width="720">
</p>

<p align="center">
  <a href="./README.md">English</a> &nbsp;|&nbsp; <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/GUI-Qt_Quick-3B6FF5" alt="Qt Quick GUI">
  <img src="https://img.shields.io/badge/Providers-Configurable-blue" alt="Configurable providers">
  <img src="https://img.shields.io/badge/Plots-Reproducible-success" alt="Reproducible plots">
  <a href="https://github.com/assle/scientific-figure/releases/latest"><img src="https://img.shields.io/github/v/release/assle/scientific-figure?label=version" alt="Latest release"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License"></a>
</p>

<p align="center">
  Turn a clarified scientific request into reproducible assets, an assembled figure,
  validation evidence, and publication-ready exports.
</p>

<p align="center">
  <img src="assets/example_compound.png" alt="Publication-ready compound scientific figure" width="820">
</p>

## Product and delivery

Scientific Figure Builder is the open-source product, not a synonym for any one
of its components. It combines a Workflow Skill, a local lifecycle MCP server,
the deterministic Core runtime, a CLI, and a native Configuration app.

The latest fixed release ships a **Native Codex plugin** and an independently
versioned Core runtime. The Native plugin
owns Codex discovery, enablement, upgrade, and removal of its Workflow Skill and
MCP declaration; the separate Core runtime keeps deterministic execution and the
optional Configuration app outside the host plugin cache.

| Component | Responsibility |
|---|---|
| Workflow Skill | Teaches the Calling Agent when and how to run the workflow |
| Lifecycle MCP server | Exposes exactly `initialize_figure_project` and `advance_figure_workflow` |
| Core runtime | Owns lifecycle state, execution, plotting, assembly, validation, and export locally |
| Configuration app | Manages Providers, Model routes, and system credentials |
| Codex integration | Makes the Skill and MCP server discoverable in Codex |

## Architecture and lifecycle

There is one public lifecycle path and one authority for phase transitions:

```text
Calling Agent
  → Lifecycle MCP server (2 public tools)
    → Orchestrator (the only lifecycle authority)
      ├─ Phase worker → schema-governed Phase artifact
      ├─ Figure Planning Module
      │  └─ Figure Graph → Solved layout → SVG blueprint
      │     → Generation Conditions + structure questions
      ├─ Run Store + Run Invalidator → atomic persistence and precise reuse
      └─ Figure Execution Module
         ├─ Python plots and SVG/text
         ├─ Provider-routed Generation units
         └─ deterministic connectors/groups → assembly
            → layered validation → localized repair → export
```

The MCP server is a thin stdio Adapter. It does not publish plotting, Provider,
validation, or export helpers as hidden product tools. `advance_figure_workflow`
validates its input and output schemas, constructs one Runtime Context, and asks
the Orchestrator to advance until the next user decision or completion.

| Deep module | Owns |
|---|---|
| Orchestrator | Intake, Planning, Execution, Review and repair, Export, approvals, retries, resume, and the Export gate |
| Figure Planning Module | Figure Graph, Solved layout, editable blueprint, structure questions, Style Bible, and Generation Conditions before approval |
| Figure Execution Module | Approved Generation routes, Style-anchor conditions, candidate selection, deterministic assembly, validation inputs, and publication |
| Run Store | Run-directory structure, atomic JSON commit, schema validation, canonical hashes, references, and safe loads |
| Run Invalidator | Exact downstream invalidation for Figure brief/plan changes, repairs, assembly changes, and export-only reruns |
| Provider Configuration | Provider types, legacy migration, type-specific fields, Model role catalog, inheritance, and Route compatibility |
| Runtime Context Factory | Effective configuration, credentials, transport, Provider client, budget, cache, Run state, and Phase worker |

Run reuse is content-based rather than file-existence-based. Schema-invalid,
hash-mismatched, or externally replaced artifacts are not reused. Layout-only
plan revisions preserve valid paid raster assets; Python/SVG repairs rerender
their source-derived outputs; image edits preserve unrelated deterministic and
paid assets.

## What it delivers

| | Capability | Result |
|---|---|---|
| 📊 | Deterministic plots | CSV-backed line, scatter, bar, heatmap, error-bar, and multipanel figures |
| 🧠 | Structure-first mechanism figures | Addressable nodes, named ports, typed directed edges, groups, constraints, and editable SVG blueprints |
| 🎨 | Provider-neutral AI assets | Non-quantitative Generation units with provenance and declared background handling |
| 🧩 | Precise assembly and repair | Asset-level placement, port-bound connectors, exact vector labels/equations, masked edits, and rollback |
| ✅ | Layered validation | Rendered graph recovery, exact source/OCR text and formulas, geometry, Publication profiles, and multimodal review |
| 📦 | Publication export | PNG, SVG, PDF, plus optional PowerPoint-friendly SVG/PPTX |

<p align="center">
  <table>
    <tr>
      <td align="center"><img src="assets/example_line_plot.png" width="280"><br><sub>Reproducible line plot</sub></td>
      <td align="center"><img src="assets/example_heatmap.png" width="280"><br><sub>Heatmap with deterministic data mapping</sub></td>
      <td align="center"><img src="assets/example_multipanel.png" width="330"><br><sub>Multipanel composition</sub></td>
    </tr>
  </table>
</p>

## Visual model routing

The native Qt Quick app manages Global Model routes, Providers, and credentials.
It does not open a browser, start a local web server, or contact a Provider while
opening or saving configuration.

<p align="center">
  <img src="assets/gui-model-routes.png" alt="Model role routing screen" width="920">
</p>

<table>
  <tr>
    <td width="50%"><img src="assets/gui-providers.png" alt="Provider endpoint and capability configuration"></td>
    <td width="50%"><img src="assets/gui-credentials.png" alt="Keyring credential and connection testing"></td>
  </tr>
  <tr>
    <td align="center"><sub>Endpoints, protocols, and capabilities</sub></td>
    <td align="center"><sub>Keyring credentials and explicit connection testing</sub></td>
  </tr>
</table>

- **Providers** handles endpoint CRUD, wire dialects, and optional capabilities.
  Supported types are OpenAI Compatible, Anthropic Compatible, and image-only
  DashScope Native.
- **Provider capabilities** explicitly declare reference images, multiple
  references, mask editing, structure control, native alpha, seeds, and
  candidate batches; unsupported controls fail instead of being ignored.
- **Credentials & Connection** stores API Keys in the operating-system Keyring and
  tests the current unsaved draft only when the user clicks the button.
- **Model routes** bind optional `phase_reasoning`, `vision_analyze`,
  `image_generate`, optional `image_edit`, and `vision_validate` to a Provider
  and fixed model identifier.
- **Structured output expansion** starts OpenAI-compatible structured responses
  with a modest allowance and doubles it only after an explicit
  `incomplete/max_output_tokens` result. Every repeat consumes the Model role's
  call budget and is recorded in Run State audit data.
- With no Provider configured, route selectors stay disabled and lead directly to
  the Provider creation flow.

Provider waiting settings are available in the Provider and Model role forms. Blank
fields inherit: role `request_policy` overrides Provider policy, then defaults.
Reasoning/vision defaults are `connect_timeout: 15`, `status_interval: 120`,
`inactivity_timeout: 600`, `total_timeout: 1800`, `max_attempts: 3`,
`backoff_base: 2`, and `backoff_cap: 30` (durations in seconds).

DeepSeek Responses requests stay on one SSE connection. Local status checks never resend;
600 seconds of complete silence or a 30-minute logical invocation deadline stops local
waiting. Heartbeats reset inactivity only and do not prove inference progress. Generation
and editing retain their 30-second inactivity default. Other compatible Providers use
Responses SSE only with `supports_responses_streaming: true`; the official DeepSeek host
defaults to support. There is no remote background polling or reconnect-by-response-ID.

HTTP 429/500/502/503/504 and known pre-submission connection failures allow three transient
attempts including the first, with exponential backoff and equal jitter. Valid Retry-After
takes precedence; a delay beyond the remaining deadline stops retries. Every dispatched
model request consumes the existing role budget, including output expansions. Read
inactivity, interrupted streams and cancellation never automatically resend. Explicit
recovery resends the failed operation while preserving consumed budget.

Sanitized latest status lives in Run state's `provider_status`; MCP progress notifications
are sent when the host supplies a progress token. `advance_figure_workflow` waits briefly
for a local operation and otherwise returns `status: in_progress` plus a durable operation
reference. Call it again with `resume` to observe or consume that same operation; polling
includes the returned `operation_id` and never resubmits the Provider request. An explicit
`cancel_operation` action requests cancellation by operation ID and records the result
without claiming remote cancellation. `wait_timeout` can tune the initial local wait from
0 to 240 seconds. If the local owner disappears, the operation becomes
`remote_outcome_unknown` and requires inspection rather than automatic resubmission.
Local cancellation does not confirm remote cancellation, and partial output never becomes
a Phase artifact.

Phase reasoning starts at **8,192 output tokens per phase**. Intake, Planning and Review
and repair have independent starting allowances. Within the same run, resuming the same
phase/Provider/model reuses the highest allowance actually sent; changing any of those
identities starts independently. Generation/editing do not inherit text output allowances.
The Configuration app exposes phase output settings; the equivalent Model route example is:

```yaml
models:
  phase_reasoning:
    provider: deepseek
    model: deepseek-v4-flash-vision-exp
    output_tokens:
      initial_tokens: 8192
      phase_initial_tokens:
        intake: 8192
        planning: 8192
        review_and_repair: 8192
      # max_tokens: 65536  # Optional limit for each request, including reasoning.
```

Provider-level `output_tokens` supplies defaults; matching Model route fields override them.
Known official DeepSeek V4 endpoints use a conservative 384,000-token bound based on the
[advertised 384K maximum](https://api-docs.deepseek.com/quick_start/pricing/); other models
should have their supported maximum configured explicitly. Unknown model capacities are
not guessed, and a Provider rejection is surfaced without blindly retrying it. An explicit
smaller maximum also caps remembered allowances. Expansion still shares the invocation
deadline and call budget. `output_token_limits` stores dispatched allowances in Run State;
`output_usage` records reported numeric usage in attempt diagnostics. Missing counters are
unknown, not zero. Older runs without explicit history start from configured defaults.

## Quick start

### 1. Install the Core runtime and Codex plugin

```bash
git clone https://github.com/assle/scientific-figure.git
cd scientific-figure
./install.sh --codex --release latest --with-gui
```

The verified Product bundle installs the Core runtime, CLI, Native plugin, and
optional Configuration app as one Local activation. Omit `--with-gui` for a
headless Core runtime.

Installing a new Runtime does not hot-replace MCP or GUI processes that are already
running. Maintainers and users who need every local process on the released version
should follow the [current release and local update runbook](docs/operations/release-and-local-activation.md),
which explains process ownership, version sources, host restarts, and the final audit.

Later updates and local status use:

```bash
scientific-figure update --latest
scientific-figure status
```

### 2. Configure Providers

```bash
scientific-figure gui
```

If the Core runtime was installed without `--with-gui`, add or upgrade the
Configuration app at any time without reinstalling the Agent integrations:

```bash
scientific-figure install-gui
```

Requesting `gui` before installing the component returns this exact recovery
command and no Python traceback. Core MCP, plotting, validation, and export do
not import Qt and remain available on headless systems.

Create a Provider first, then assign Model roles. API Keys never enter YAML:
Global configuration stores only a stable `credential_id`, while headless and CI
environments can continue using `key_env` environment variables.

### 3. Ask your agent

```text
Use scientific-figure-builder to create a publication-ready multipanel figure
from data.csv. Export PNG, SVG, and PDF, and keep the SVG PowerPoint-friendly.
```

The lifecycle Orchestrator first records export target, figure width, language,
style, and optional Publication profile in a Figure brief. Planning then derives
the Figure Graph, Solved layout, editable SVG blueprint, structure questions,
and Generation Conditions before image generation. Calling Agent commands resume
from the Orchestrator's next action instead of manually sequencing low-level
tools. Each response contains the current Lifecycle phase, status, next action,
and canonical Artifact references.

## The core rule

```text
Measured data and quantitative plots              →  Python / SVG
Scientific relationships                           →  semantic Figure Graph
Non-quantitative figure/panel/module units           →  chosen image/vector/hybrid method
Final composition and export                       →  deterministic local pipeline
```

An image model can draw a complete non-quantitative flowchart, including its owned
labels and arrows. Data plots remain deterministic, as does outer assembly. Deterministic
findings remain authoritative; a vision model may enrich them but cannot turn a
failed geometry check into a pass.

The Phase worker returns narrow Planning Advice for composition and style. The Figure
Planning Module, not the model, deterministically owns Generation-unit identity, membership,
routes, asset ownership, hashes, and source provenance. A schema-valid suggestion therefore
cannot silently rewrite the selected production method or scope.

Style input is normalized at the Lifecycle seam. The canonical forms are
`{"kind":"default"}`, `{"kind":"description","description":"..."}`,
`{"kind":"file","path":"...json"}`, and
`{"kind":"inline","style_bible":{...}}`; legacy strings and inline Style Bible objects
remain accepted. Phase reasoning compiles descriptions to a validated Style Bible; missing
or invalid compilation pauses Planning instead of silently loading the default. The Generation summary includes the resolved view,
projection, background, palette, and important forbidden elements.

Explicit generation choices are submitted through the existing Lifecycle request:

```json
"generation_intent": [
  {"unit_id": "workflow", "method": "image_model", "scope": "figure", "background": "preserve"}
]
```

Methods are `auto`, `image_model`, `vector`, and `hybrid`. Scope is `figure`, `panel`
(with `panel_id`), or `module` (with `panel_id` and `members`, the existing element/
Figure Graph node IDs). Disjoint selections can produce a complete image flowchart
in one panel alongside a deterministic data plot in another. Hybrid `ownership`
maps members to `image_model` or `vector`. Image-owned top-level labels require
`panel_id` and `bbox`, or grouping into an image panel/module; unselected content retains automatic
routing. Optional `parameters` and `candidate_count` apply to the complete image unit.

A new plan returns `generation_summary` before image generation. Display it, then
continue with the returned action: `resume` requires no new human approval under
`auto_execute`; `approve_plan` retains normal approval. The summary is not a final
figure. Old approved plans without the new contract remain usable without a re-plan.

A later explicit instruction can revise the selection with the existing tool's
`revise_generation_intent` action (`generation_intent` plus `reason`). This revision
preserves budgets, phase token history and reusable unrelated assets. Invalid or
conflicting choices pause with actionable information rather than changing routes.

Whole image units preserve their background by default, can contain their required
text/arrows, and retain semantic topology separately from assembly geometry. Planning
publishes an Asset Blueprint for production ownership and, for collapsed image units, a
Composition Blueprint with semantic regions, reading direction, density flow, anchors, and
relationships. The Composition Blueprint is the primary pre-generation review artifact; it
is not final artwork or a promise of editable raster internals. Three
unit-specific review results (content, connections, quality) are required; missing
image review evidence blocks normal export. `apply_repair` can regenerate that same
unit (`image_model`) or use supported `image_edit`, but cannot silently replace it
with SVG or subdivide it. Raster units do not provide per-object editability;
`require_editable_objects: true` makes that conflict explicit. Existing waiting,
retry and phase output-token policies remain unchanged.

A minimal single-panel request needs only an ID and its content when figure width or canvas
dimensions are available:

```json
{
  "figure_id": "overview",
  "figure_width_cm": 14,
  "panels": [{
    "panel_id": "main",
    "elements": [{"element_id": "title", "type": "text", "content": "Overview"}]
  }]
}
```

After canvas resolution, the single panel receives the full normalized bounding box and a
derived physical size. Multiple panels still need explicit bounding boxes; the runtime does
not invent an ambiguous layout.

## Mechanism-figure workflow

```text
Scientific intent
  → Figure Graph (nodes, ports, typed edges, groups, constraints)
  → Solved layout + Asset Blueprint + optional Composition Blueprint
  → Provider-neutral Generation Conditions
  → declared Generation units + their owned text/connectors
  → assembled-figure structure/OCR/publication validation
  → layout, connector, vector, or masked-raster patch with rollback
```

Asset bounding boxes are panel-relative when explicitly supplied. Layout-only
changes preserve paid raster assets. Related assets use approved per-group Style
anchors; references are role-tagged as content, style, structure, parent, or
mask and are hash-verified before upload. `nature_research` is available as a
Publication profile for Nature dimensions, typography, editable vectors, and
palette-accessibility checks, while `general` remains the default.

## Minimal Provider configuration

The GUI writes this metadata for you; API Keys are deliberately absent:

```yaml
providers:
  vision_provider:
    type: openai
    base_url: https://api.example.com/v1
    key_env: VISION_API_KEY
  image_provider:
    type: dashscope
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    key_env: DASHSCOPE_API_KEY
    supports_image_edit: true
    supports_reference_image: true
    supports_multi_reference: true
    supports_mask_edit: false
    supports_structure_control: false
    supports_native_alpha: false
    supports_seed: true
    supports_candidate_batch: false

models:
  vision_analyze:  {provider: vision_provider, model: vision-model}
  image_generate:  {provider: image_provider,  model: image-model}
  vision_validate: {provider: vision_provider, model: vision-model}
```

Omit `image_edit` to inherit `image_generate`. A Keyring-backed credential takes
precedence over its environment fallback. Declare only capabilities the Provider
actually supports; they are compatibility contracts, not hints.
DashScope Native normalizes the shown `compatible-mode/v1` URL to the matching
regional `/api/v1` native root and immediately downloads results from the
synchronous multimodal-generation API. It cannot serve `phase_reasoning`,
`vision_analyze`, or `vision_validate`.

## Export targets

| Target | Best for | SVG text |
|---|---|---|
| `general` | Publishing, browsers, vector tools | Converted to portable paths |
| `ppt` | PowerPoint editing and ungrouping | Preserved as editable text |

## Command reference

If `scientific-figure` is not on the current shell `PATH`, use the absolute
launcher printed by the installer. Its Unix default is
`~/.local/bin/scientific-figure`.

### Install and activate locally

| Command | Meaning | Network and mutation |
|---|---|---|
| `./install.sh --help` | Show the current complete installation interface | Offline, read-only |
| `./install.sh --codex --release latest --with-gui` | Install or activate the latest formal Release with Core runtime, CLI, Native plugin, and Configuration app | Online; changes product and Codex plugin state |
| `./install.sh --codex --release vX.Y.Z --with-gui` | Install one pinned Product version | Online; changes product and Codex plugin state |
| `./install.sh --codex --bundle /path/to/bundle.tar.gz --with-gui` | Install an offline Product bundle; `SHA256SUMS` must be beside it | Offline; changes product and Codex plugin state |
| `./install.sh --runtime-only --release latest` | Install only the Core runtime and CLI | Online; adds no Agent integration |
| `./install.sh --runtime-only` | Compatibility Core-only installation from the current source tree | Development source, not a formal Release installation |

`--with-gui` includes the Configuration app; `--without-gui` explicitly creates
a headless new Runtime. `--codex` means complete Codex activation, not Core-only.
The older `--codex-only` alias remains for one minor migration cycle and prints
a compatibility notice.

### Update an installed version

| Command | Meaning |
|---|---|
| `scientific-figure update --latest` | Resolve GitHub latest once, pin it as the Target version, and preserve the installed host/GUI shape |
| `scientific-figure update --release vX.Y.Z` | Update online to one exact Release |
| `scientific-figure update --bundle /path/to/bundle.tar.gz` | Update from a local bundle without deleting the user-supplied bundle |
| `scientific-figure update --latest --codex` | Explicitly update the complete Codex integration |
| `scientific-figure update --latest --runtime-only` | Explicitly update only Core runtime and CLI |
| `scientific-figure update --latest --with-gui` | Update and ensure the Configuration app is included |
| `scientific-figure update --latest --without-gui` | Update to a headless Runtime |
| Add `--json` to an update command | Emit the machine-readable Activation result |

Update preserves Providers, Model routes, Credential references, Keyring API
Keys, projects, data, and run artifacts. It replaces the Core runtime, Native
plugin, Workflow Skill, CLI, Configuration app, and product dependencies. It
does not terminate Codex or close a GUI that may contain an unsaved
Configuration draft.

### Status, configuration, and project setup

| Command | Meaning | Mutates state |
|---|---|---:|
| `scientific-figure status` | Summarize Native plugin, Active runtime, CLI, Running runtime instances, and cleanup state offline | No |
| `scientific-figure status --verbose` | Also show each MCP/Configuration app process and retained path | No |
| `scientific-figure status --json` | Emit complete machine-readable status | No |
| `scientific-figure status --remote` | Compare local status with the latest GitHub Release | No; uses network |
| `scientific-figure --version` | Show the Product version of the current CLI | No |
| `scientific-figure gui` | Open the Configuration app on demand | Starts GUI, not MCP |
| `scientific-figure install-gui` | Add GUI dependencies to the Active runtime | Yes |
| `scientific-figure init [project_dir]` | Create non-secret `.scientific-figure/` project configuration | Yes |

Status conclusions and exit codes:

| Exit | Conclusion | Meaning and next action |
|---:|---|---|
| `0` | `converged` | Local versions agree; `clean=true` means no obsolete product files remain |
| `2` | `restart_required` | Disk is updated but old MCP/GUI instances remain; save work and fully restart the host |
| `3` | `inconsistent` / `update_available` | Component versions differ or `--remote` found a newer Release; run update |
| `4` | `broken` | Active runtime is missing or unreadable; repeat complete installation |
| `1` | update/install failure | Download, checksum, manifest, installation, or compensation failed before an Activation result |

MCP and the Configuration app are on-demand; idle is healthy. To load a newly
installed MCP, fully quit and reopen Codex, then invoke Scientific
Figure Builder in a new task.

### Maintainer build and release

| Command | Meaning |
|---|---|
| `python3 scripts/verify_release_candidate.py --tests --build` | Run the same full tests, Pyright, Core wheel, and Product bundle build used by CI |
| `python3 scripts/release.py minor` | Prepare the next minor candidate in an isolated worktree and retain local ref `codex/release-X.Y.Z`; do not push |
| `python3 scripts/release.py patch --publish --notes-file /path/to/approved.md` | Prepare a patch, push main, wait for CI, then tag; the tag workflow publishes formal artifacts |
| `python3 scripts/release.py X.Y.Z --publish` | Continue an already-versioned candidate with approved notes; resume from remote facts after interruption |
| Add `--activate-local` to publish | Activate the exact published version locally; exit `2` means host reload remains and does not undo the Release |
| `python3 scripts/record_release_acceptance.py --confirm-codex-restarted` | Record observed Codex restart, new-task MCP, Configuration app, and clean status |
| `python3 scripts/release.py X.Y.Z --check-acceptance` | Validate only local acceptance evidence |
| `python3 scripts/release.py X.Y.Z --check-notes` | Validate only `status: approved` Release notes |
| `python3 scripts/release.py X.Y.Z --check-release` | Validate a non-draft GitHub Release has bundle, wheel, and `SHA256SUMS` |

Release notes begin as `status: draft`; review and change them to
`status: approved` before `--publish`. Published tags are immutable; use a new
patch version for conflicts. See [Release and local update](docs/operations/release-and-local-activation.md)
for the complete maintainer flow.

### Filesystem layout

Code, the private virtual environment, and dependencies live in a versioned
application-payload prefix rather than `XDG_DATA_HOME`:

| Category | Unix default | Windows default |
|---|---|---|
| Global Core runtime | `~/.local/lib/scientific-figure-builder/global/runtimes/<version>` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\global\runtimes\<version>` |
| Project Core runtime | `~/.local/lib/scientific-figure-builder/projects/<project-id>/runtimes/<version>` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\projects\<project-id>\runtimes\<version>` |
| Global configuration | `$XDG_CONFIG_HOME/scientific-figure-builder/config.yaml` | `%APPDATA%\scientific-figure-builder\config.yaml` |
| Application state root | `$XDG_STATE_HOME/scientific-figure-builder` | `%LOCALAPPDATA%\State\scientific-figure-builder` |
| Application cache root | `$XDG_CACHE_HOME/scientific-figure-builder` | `%LOCALAPPDATA%\Cache\scientific-figure-builder` |
| Launcher | `~/.local/bin/scientific-figure` | `%LOCALAPPDATA%\Programs\ScientificFigureBuilder\bin\scientific-figure.cmd` |

Absolute XDG overrides are honored. `SCIENTIFIC_FIGURE_INSTALL_HOME` overrides
the application-payload prefix and `SCIENTIFIC_FIGURE_BIN_DIR` overrides the
launcher directory. Project paths are hashed only to create an isolated runtime
identity; user projects remain where the user put them.

Each Agent integration points to an exact Product version. Installing a newer
version builds and verifies a new runtime before switching the active-runtime
record, so a failed upgrade leaves the previous runtime and integration usable.
When the old `$XDG_DATA_HOME/scientific-figure-builder` runtime is detected, a
successful Global installation records it as the migration source and retains
it for rollback. A full Global uninstall removes both the versioned runtime
scope and that legacy runtime; a Project uninstall removes only its own scope.

### Transaction and retention

Install and upgrade run as one filesystem transaction per Runtime scope. The
installer performs source, config, launcher, permission, and disk-space preflight;
builds the Core runtime with non-editable package metadata in same-filesystem
staging; validates the CLI and MCP server; then atomically commits runtime,
launcher, optional legacy Codex integration, and active-runtime metadata. A failure or process
interruption restores replaced paths in reverse order. A scope lock rejects
concurrent installs, while the next safe run removes orphan staging from a dead
installer.

The Delivery Interface is `InstallRequest → InstallResult`. The request carries
target, Runtime scope, Product version, and GUI selection; the result reports
committed, retained, pruned, and logged paths. The CLI only translates flags
into this Interface. Deprecated manual Codex delivery remains inside the same
transaction, while the Native Codex plugin is host-managed.

During activation, the previous verified Runtime remains available for
compensation and every Runtime used by a live MCP or GUI is protected. After
process convergence, on-demand startup removes superseded Runtime and Plugin
cache versions. Temporary transaction backups are deleted after commit or
rollback. Sanitized transaction logs are stored below the scope's XDG state
directory and capped at 10 entries; they record paths and outcomes, never config
contents or credentials. Uninstall recognizes active locks and will not remove a
runtime while its install transaction is running.

<details>
<summary><strong>Uninstall safely</strong></summary>

```bash
codex plugin remove scientific-figure-builder@scientific-figure
./uninstall.sh                    # default: Core runtime and CLI only
./uninstall.sh --codex-legacy     # deprecated manual Codex integration only
./uninstall.sh --all              # Core, legacy Codex integration, config, credentials
./uninstall.sh --runtime-only --project DIR
./uninstall.sh --dry-run
codex plugin marketplace remove scientific-figure # optional: stop listing this repo
```

Native plugin removal deletes its cached Skill and MCP declaration without
creating or leaving a top-level Codex MCP entry. It deliberately preserves the
independent Core runtime, Global configuration, and Keyring credentials. The
source uninstaller removes every version in the selected runtime scope, including
the optional GUI, plus only legacy installer-owned launcher and MCP entries. A
Global uninstall also removes the retained legacy runtime. If Keyring cleanup
fails, user configuration is retained.
</details>

## Versioning

Scientific Figure Builder follows [Semantic Versioning](https://semver.org/).
`scientific-figure-builder/pyproject.toml` is the canonical Product version;
the CLI and Lifecycle MCP server read that installed package version. Check it
with:

```bash
scientific-figure --version
```

The project is currently pre-1.0, so `0.y.z` releases may still refine public
interfaces. See the [latest fixed release](https://github.com/assle/scientific-figure/releases/latest).
A release exists only when the repository has an immutable
`vX.Y.Z` Git tag and a matching GitHub Release. Schema, prompt, and recipe
versions are compatibility contracts of their own and do not follow the Product
version automatically.

## Development

### Repository layout

This is a single-context repository: product vocabulary lives in `CONTEXT.md`
and repository-wide architecture decisions live in `docs/adr/`.

```text
.
├── CONTEXT.md                         # Canonical product vocabulary
├── docs/
│   ├── agents/                        # Engineering-skill configuration
│   ├── adr/                           # Repository-wide architecture decisions
│   └── verification/                  # Current platform evidence
├── scientific-figure-builder/         # Canonical Core, Skill resources, and tests
├── plugins/scientific-figure-builder/ # Generated Native plugin snapshot
├── scripts/                            # Repository maintenance
├── assets/                             # README images
├── install.sh                           # Public source-install entry point
└── uninstall.sh                         # Public source-uninstall entry point
```

Edit canonical Skill resources under `scientific-figure-builder/`, then run
`python3 scripts/sync_plugin_bundle.py` from the repository root. Do not edit the
generated Skill copy under `plugins/` directly; the test suite verifies that the
snapshot matches its canonical source.

### Local development

```bash
cd scientific-figure-builder
uv sync --extra gui
uv run --extra gui pytest -q
uv run --extra gui python -m figure_tools gui
uvx pyright --pythonpath .venv/bin/python figure_tools install
```

Useful references:

- [Domain vocabulary](./CONTEXT.md)
- [Security policy](./SECURITY.md)
- [GUI platform verification](./docs/verification/gui-platforms.md)
- [Real Provider regression verification](./docs/verification/provider-regression.md)
- [OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)

## License

[MIT](./LICENSE)
