# Windows installation and bridge validation

Use Windows 11 with a licensed Adobe After Effects 2025 installation and Python 3.11+. FFmpeg and ffprobe are local helper binaries. No Adobe plugin, paid API or background service is installed.

Run the README setup commands from the checkout. To reproduce the exact verified Python dependency set after creating the venv:

```powershell
uv pip sync --python .venv\Scripts\python.exe requirements-dev.lock
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
```

If detection fails, set `ASTRA_AE_EXECUTABLE`, `ASTRA_FFMPEG`, `ASTRA_FFPROBE` to absolute executable paths. Set `ASTRA_WORKSPACE` to a writable artifact directory. These are trusted local operator settings; do not accept executable overrides from untrusted prompts. A status call probes binaries but does not start AE or check its scripting preferences/license dialogs.

## Historical Sprint 0 controlled test

This read-only procedure was used to diagnose scripting. Manual execution and a later direct Python argument-list launch succeeded; the `Start-Process` attempts below did not produce acknowledgements on this host. The Sprint 1 runner now uses direct `subprocess.Popen` argument lists. Retain this procedure for troubleshooting, not as a proven launch recipe.

1. Save any existing work yourself, then open AE 2025 to an empty project. Record whether an AE instance is running, the scripting preference and project item count. In **Edit > Preferences > Scripting & Expressions**, inspect **Allow Scripts to Write Files and Access Network**. This permission is needed for acknowledgement output; enable it yourself if you accept it. Astra does not change preferences.
2. Prepare the unique script. This command does not launch AE:

   ```powershell
   .\.venv\Scripts\astra-studio.exe prepare-probe
   ```

3. Review the generated `probe.jsx`. It reads AE's version and item count and writes only its unique result file. Substitute the returned full script path in this command:

   ```powershell
   Start-Process -FilePath 'C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe' -ArgumentList @('-r', '"C:\full\path\to\probe.jsx"') -WindowStyle Hidden
   ```

4. Allow up to 60 seconds for AE initialization, inspecting dialogs manually if needed. Check the acknowledgement:

   ```powershell
   .\.venv\Scripts\astra-studio.exe verify-probe --job-id <returned-job-id>
   ```

5. Collect the manifest, `result.json`, current AE version, elapsed time, any dialogs/errors and whether the existing instance handled the command. Confirm project item count and dirty state remain unchanged. Record evidence in `docs/test-report.md` before deciding on Sprint 1. Repeat with a fresh probe ID in an already-running AE, then, after closing AE yourself, from a cold start. Do not close an unsaved project for this test.

No acknowledgement within 60 seconds means **unconfirmed/timeout**, even if the launcher exits successfully. Do not automatically kill AE or resend the script. Check permissions and dialogs. If `-r` fails, try **File > Scripts > Run Script File** with the same trusted probe to distinguish file-write permission from command-line delivery. Manual execution alone does not validate `-r`. The script has no project operations, but AE startup may display license/recovery dialogs.

The local `verify-probe` command reports results; it does not monitor, kill processes, or mark the bridge validated automatically. Human review must establish repeated, reliable delivery and absence of unintended state changes.

## Sprint 1 execution and timeout recovery

Use the `create-demo` command and opt-in tests in README.md. No additional dependencies are needed. The real MCP tool path has its own opt-in test. All artifacts live beneath `ASTRA_WORKSPACE`; retain its manifests with the AEPs so ownership and operation history remain available.

If `ae-pending.json` exists, the bridge blocks all new submissions. Read the referenced job journal/result and inspect AE. An empty result or a launcher exit is not success. Do not kill AE or repeat the timed-out script. A cancellation marker prevents that job from starting mutations if it has not begun, but cannot stop one already executing. After manually confirming the job is no longer running/queued, preserving any resulting work and recording the recovery decision, the operator may archive the pending record before another test. No automatic recovery or MCP quarantine-clear tool is exposed. Keep the same configured workspace throughout this process.

Cold-start routing, multiple interactive AE instances and interrupted-save recovery are not validated. Current evidence covers an already-running AE 25.5 instance. Do not use multiple workspaces to bypass a pending job. All untracked or dirty open projects are refused; save and close them yourself, or explicitly authorize a separately reviewed snapshot workflow.

## Sprint 2 verification

Run the default suite without `ASTRA_RUN_AE_TESTS` for schema/planner/runner checks. With explicit operator authorization and saved work, set `ASTRA_RUN_AE_TESTS=1` and run `python -m pytest` from the venv to include all three real AE cases. The motion test creates a fresh 10-second project, applies a static transform and four skills through MCP, and leaves the last version open. Previous versions and source snapshots remain under the workspace. Clear the environment flag afterward.

If a version fails verification after AE saved it, do not promote it or modify its parent manifest automatically. Inspect its `version.json`, operation acknowledgement and AE state; preserve the artifact and confirm a deliberate recovery. The current pointer remains on the last verified file, so ordinary editing calls may correctly refuse an active failed-version path. This is a safety boundary, not permission to discard the active project.

Do not run other JSX scripts while Astra is executing. If AE displays a warning about simultaneous scripts, finish/dismiss the message yourself, then inspect the pending job before further calls. The current bridge publishes acknowledgement through AE's task queue and retains a 750 ms post-acknowledgement interval; real combined testing passed with that change. It does not forcibly dismiss dialogs or claim universal readiness.

## Sprint 3 sources and tests

Put trusted sources under `ASTRA_WORKSPACE` or explicitly set `ASTRA_IMPORT_ROOTS` in the launching shell/MCP host. On Windows separate multiple absolute folders with `;`. This is operator-controlled read permission; tool calls cannot expand it. `.env.example` remains documentation only and is not loaded automatically. The server never writes into import roots.

Use `open-copy --source <path>` and `save --project-id <id>`, or their MCP equivalents. Read `existing-projects.md` before opening a linked-media/plugin-heavy production project. The source AEP is preserved; linked media is not automatically collected and application-level AE reads are not sandboxed by the Python path validator.

With `ASTRA_RUN_AE_TESTS=1`, `python -m pytest` now includes four live cases. The existing-project case builds an ordinary source fixture, opens a copy, checks selective editing and saves deliberately simulated manual changes in that test copy. No client project is required for this acceptance check. Default tests leave all live cases disabled.

## Sprint 4 bridge and rendering

Run `astra-studio bridge-start` once before editing. The first -r bootstrap may need manual execution via the AE Scripts menu; `status` returns its reviewed local path under `bridge_runtime.bootstrap_script`. This host required that manual initialization. After a live idle heartbeat, tools reuse the inbox instead of launching scripts again. A stale known session requires review/manual bootstrap restart after AE is closed/reopened. Do not clear pending operations just to restart the bridge.

The installed `aerender.exe` must be adjacent to the configured AfterFX.exe. Local FFmpeg must provide libx264 and ffprobe. PNG Sequence is preferred when installed; this machine's actual preset is TIFF Sequence with Alpha and is selected after template discovery. `ASTRA_PNG_TEMPLATE` is an optional operator PNG-template name override. No preset is installed or invented automatically. Templates using other formats fail explicit validation.

The full opt-in suite now includes five real AE cases, including render-to-MP4. Run it only with saved work, the idle listener ready and enough disk space for a lossless image sequence. Keep the MCP host alive and do not run other scripts during execution. See `preview-rendering.md` for bounded requests, cancellation semantics, retained artifacts and native-render pending recovery.
# Sprint 5 verification and operation

No additional packages or paid services are needed. Run the existing local stdio server; it now publishes 22 typed tools. Use the persistent host through `scene_execute`/`scene_status` so the preview worker remains alive. See [scene direction](scene-direction.md) for the brief→plan→AEP→preview→revision workflow.

Default tests do not change AE. The authorized full native regression uses:

```powershell
$env:ASTRA_RUN_AE_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:\ASTRA_RUN_AE_TESTS
```

This includes seven live AE cases, including a 12 second directed scene, Portuguese revision, two full previews, four layer types, imported media and stagger. It creates new files and leaves a managed project open. Preserve other work and initialize the idle bridge before running. Full playback and artistic approval remain human checks.

# Sprint 6 operation

No new dependencies are required. The stdio server exposes 32 tools. Scene CLI commands mirror MCP names with hyphens and accept `--request` JSON. See [scene editing](scene-editing.md).

The authorized native suite now also includes `tests/integration/test_scene_ae_live.py`: a 20-second master with three nested scenes, stable IDs, null parenting, mattes/blend modes, frame/FPS policies, dependency refusals and preserved prior files. Preview limits remain unchanged; the test renders a three-second excerpt. Do not run mutex unit tests in parallel with native AE tests; use the single full pytest command sequentially.

# Sprint 7 operation

No additional installation is required. The stdio server now exposes 42 tools; CLI names use hyphens and `--request` JSON. Start with `fonts-list` to obtain actual font names/IDs. See [design tools](design-tools.md).

The opt-in `tests/integration/test_design_ae_live.py` creates a disposable editable brand card, checks missing-font/overflow handling, native vector import/paths/Trim Paths/morph/text animators, layout profiles and alignment/distribution, then renders landscape and portrait excerpts. The full native suite has nine cases. Run it sequentially with the existing command and keep AE's idle bridge ready; do not run separate mutex tests concurrently.

# Sprint 8 operation

The server exposes 48 typed tools with no added dependencies. Use `animation-inspect --request ...` to obtain the hashes required by editing commands. The CLI names mirror the tools with hyphens. See [animation editor](animation-editor.md).

After restarting AE/computer, use `studio_status` to inspect heartbeat and pending markers. A stale known session must not trigger automatic repeated -r launches. With no pending work, run the reported bootstrap manually through AE's File > Scripts > Run Script File, then confirm fresh heartbeat and a real acknowledged read before native tests.

The opt-in `test_animation_ae_live.py` checks key CRUD, Hold/Bezier/Linear, curved tangents, velocity changes, group retime, explicit blur settings, overlapping anticipate_settle entries, preserved exit/sentinel and two fully decoded five-second previews. The full suite now has ten native cases. Run tests sequentially; do not run mutex tests concurrently with AE operations.


# Sprint 9 operation

The server exposes 53 tools with no added dependency. CLI names mirror the five revision tools with hyphens and typed `--request` JSON. See [revisions/manual collaboration](revisions.md). Keep the same workspace and idle bridge session; no new bootstrap/transport is required for these generated operations.

If the MCP host was already running before the code update, reload that server after its queued work finishes so it discovers the new tools. This is separate from restarting AE or its idle bridge.

`test_revisions_ae_live.py` is an explicitly enabled native case. It creates a disposable project, simulates unsaved operator color/anchor edits through a test-only template fixture, captures them explicitly, changes title/entry keys, verifies conflict refusal and restores prior versions as new AEPs. It also exercises text style, static transform and timing patches and a fully decoded five-second preview. There are eleven native cases in total. Run native and machine-mutex tests sequentially.

# Stint 9.1 operation

The server exposes 55 tools. Rich responses now default to compact; migrate callers that depend on data.compositions to filtered project_query/operation_query, or explicitly pass top-level response_mode=full. CLI equivalents are project-query, operation-query and --response-mode full. See [examples and byte limits](compact-responses.md).

An already running MCP server must be reloaded after its current work finishes to discover the updated tools/contracts. This host-only update does not require another AE bootstrap. Published response evidence requires same-filesystem hard-link support; it was tested on this host. Existing native timeout/pending markers must never be cleared to reload presentation code.

Default tests cover stdio MCP with simulated full-state/service results, CLI output, concurrency and historical evidence presentation. Existing opt-in AE tests explicitly request full host output through the test harness; their original native assertions remain intact. No native tests are automatically enabled by presentation tests.

# Stint 9.2 native result transport

New hosts default to ASTRA_AE_RESULT_TRANSPORT=artifact-v1; the optional explicit legacy value is inline-v1. .env.example is not automatically loaded. Full native data now lives in jobs/<UUID>/native-result.json, while result.json is a small descriptor. Older historical inline jobs are preserved. The idle bootstrap is unchanged; reload a Python/MCP host only after its current work finishes. Do not clear any native/render pending marker as part of a reload.

Run the standard functional suite normally. The targeted opt-in test_native_artifacts_ae_live.py uses real AE and stdio MCP but only read-only font/result fixtures; it preserves the currently open project/source and render queue. It is safe to run independently of the old render-acceptance cases only when the existing bridge is fresh and has no uncertain native job. An unresolved preview marker still prohibits a new render. Run native and machine-mutex tests sequentially. See [full transport verification/limits](native-result-transport.md).
