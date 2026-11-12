# Verification report — Sprints 0–4, 2026-11-05

## 2026-11-07 — Standalone SFX commission (not a product sprint)

Trusted operator source: `C:/Users/ryanb/OneDrive/Imagens/MMV/avs apple like video/Project.aep`. The original was not saved. Copies, original synthesized SFX, source hashes and evidence are under `workspace/deliveries/project-sfx/`.

Direct AE job `0016beba8e9b4706ae6cd3345e786157` returned a matching deferred success acknowledgement after saving and reopening `Project-com-SFX.aep`; SHA-256 `008bb0a2036952d0076ed94412f383c338d006418589f3893050f561804d8dfe`. Native `Comp 1` (ID 1), duration 20.02002002002 s, 29.9700012207031 fps, has a new audio-only layer ID 462 with 30 cue markers and enabled stereo audio. All seven original compositions were compared by persistent layer IDs, structure, readable properties/key values and expression text; their inspected state and the original render queue were unchanged. Copied media were relinked in the new working project; no missing footage was reported. Opaque CUSTOM_VALUE paint data remain outside semantic value inspection and were not written.

The first attempt was an acknowledged synchronous inspection failure while reading `ADBE Paint Shape` custom values, before audio insertion. Its evidence and active working state were preserved in `attempt-01/`. The corrected attempt did not relax value equality for supported properties. The source and initial snapshot hashes were rechecked.

`Preview-com-SFX.mp4` uses the supplied existing render, not a fresh native render: 600 frames, 1920×1080, 30000/1001 fps, 20.02 s, AAC stereo / 48 kHz. Copied video packet SHA-256 `51b611877343e5a6e3af4fd88d262f64e4128384639678643861065b1b16a706` matches the supplied render. Full decode passed; the final MP4 SHA-256 is `d5f581a039a262d484dba75b8ae39e30965aeb8868dd7a6f7beaa3e8acebdb75`. Cue planning used inspected source-frame samples; full playback, audio listening and artistic approval are not claimed. The prior native-render pending marker was not cleared and no new native render was launched. This changed production artifacts only, so the product functional pytest suite was not rerun.

## 2026-11-07 — Team Aureon production evidence (separate from sprint acceptance)

Project `3f2d6bb04bd74204b2485d8c14ed2020`, composition `462a2e3540774860a96d35719fda0df2`: native 1920×1080 / 30 fps / 24 s text, solids, vector paths, trim animation, blur and transform/opacity batches were acknowledged, saved and reopened. Final verified version: `5cbaebefefe84671b9bc273e14938b1c`. See `workspace/deliveries/team-aureon/native-evidence.json` and `editable-project.json`.

A synchronous path precision validation failure was preserved and recovered from a hash-checked clean source; see `recovery.json` and the immutable creative amendment. The parent manifest did not advance on failure. No source code or tolerance change was made.

Native renderer job `bb9cf0bad5c4488e99deec75356973a9` reached its 300-second timeout before producing any frames; its log only contained the aerender version. Queue preparation was acknowledged, but native rendering is **unverified**. `workspace/preview-pending.json` and the disposable render copy remain. No further native render was submitted and AE was not terminated.

The commissioned MP4 is independently composed from the creative specification, with original synthesized audio. Its technical output and actual sampled-frame review are recorded separately in `workspace/deliveries/team-aureon/delivery-verification.json`. That output does not prove native rendered appearance or pixel equivalence with the AEP. Full playback, audio listening and human artistic approval are not claimed. No functional implementation change was made, so the functional pytest suite was not rerun for these production-only artifacts and evidence notes.

## Historical Sprint 0 scope

The early sections below preserve the original evidence. Current increment acceptance is recorded in the Stint 9.2 section at the end of this report; host-presentation, prior native and separate production evidence retain their own scopes. Earlier statements about missing capabilities describe their original sprint, not the current implementation. Dates are client-local (America/Sao_Paulo); UTC job timestamps can fall on the following calendar day.

Sprint 0: Python package and entry points, configuration, typed MCP `studio_status`, AE executable/PE-version discovery, FFmpeg/ffprobe diagnostics, actual workspace write probe, stderr logging, workspace containment, controlled read-only JSX probe preparation and acknowledgement validation. Installation instructions, architecture, decisions and tool contracts are included.

No AE editing, saving, media import, rendering or motion engine implementation has been claimed. No existing project was opened or modified. No server was registered in the Codex app automatically.

## Environment actually observed

| Component | Observed result |
| --- | --- |
| OS | Windows-11-10.0.26200-SP0 |
| System Python | 3.13.7 |
| Isolated `.venv` Python | 3.14.0 (existing interpreter selected by uv) |
| MCP SDK | 1.30.0 |
| Pydantic | 2.14.3 |
| AE executable | `C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe` |
| AE PE version | 25.5.0.4 |
| FFmpeg | 8.0.1, `C:\ffmpeg\bin\ffmpeg.exe` |
| ffprobe | 8.0.1, `C:\ffmpeg\bin\ffprobe.exe` |
| Workspace write/delete permission | Passed |
| Bridge execution | Not validated; AE was not launched |

Live `astra-studio status` returned `status: ok`, `bridge_status: not_validated`, operation ID `b6f73538024f463eb17679bdcabeb387`, UTC timestamp `2026-11-05T14:38:45.839495+00:00`. This establishes diagnostic prerequisites only.

## Automated checks

Command: `.\.venv\Scripts\python.exe -m pytest -q --tb=short`

**32 passed, 1 skipped in 4.47 seconds.** The skip is the symlink escape test: Windows did not grant symlink creation privileges. Ordinary traversal and absolute-path escape tests passed; symlink escape remains unverified on this host.

- Configuration/environment loading and workspace path containment.
- Missing AE override and incompatible/unknown version reporting.
- Missing media binaries, failed/empty/unexpected version responses, subprocess timeout and permission failures.
- Workspace write failure, unsupported platform and preservation of `not_validated` bridge status.
- Unique probe preparation without process launch; malformed IDs, oversized responses, incorrect acknowledgement IDs, invalid status/version/item metadata and missing acknowledgements.
- Real MCP stdio subprocess: initialize handshake, tools/list, output schema and tools/call returning structured content. Only `studio_status` is exposed. No AE process is launched by this test.

The initial sandboxed pytest run failed during temporary-directory fixture setup for all tests, before test bodies ran. The same suite then passed outside the sandbox. uv also required escalation for denied interpreter-cache access. These were environment permission failures. Dependency versions are captured in `requirements-dev.lock`.

## Prepared bridge evidence and pending work

Probe job `4d6842da22a2498299360ba70be54dbd` is prepared under `workspace/bridge-probes/`. Its manifest and trusted JSX exist; no acknowledgement exists because execution has not been attempted. The script reads AE version/item count and writes its result, without project mutations. The procedure and failure/timeout handling are documented in `installation-windows.md`.

Before Sprint 1, validate this controlled test with the operator and collect successful matching acknowledgement from warm and cold AE starts, elapsed times, dialogs, scripting permission state and unchanged project state. CLI delivery, file-writing permission, license readiness, reliable instance routing and AE completion behavior remain unverified. No `.aep`, keyframe or render acceptance criteria have been met yet. GPU availability and visual quality were not tested in Sprint 0.

The candidate command uses Adobe's documented `AfterFX.exe -r` interface; documentation alone is not runtime evidence. No automatic polling/cancellation runner is enabled before delivery semantics are verified.

## Controlled bridge attempt — 2026-11-05

The operator confirmed that AE permits scripts to write files and access the network. Launched the prepared trusted probe via `Start-Process`, `AfterFX.exe -r`, with a quoted absolute JSX path and hidden launcher window. Launcher PID: 24040. The observed AE process was PID 9564, executable in the expected 2025 installation; its title was `Adobe After Effects 2025 - Untitled Project.aep` and `Responding` was true. No pre-launch process snapshot was obtained because the sandbox launcher failed, so warm/cold routing cannot be established from these observations.

Repeated acknowledgement reads through and beyond 60 seconds returned `unconfirmed`: no `result.json` was present. Launcher exit is not evidence of JSX completion. The operator reported no visible dialog. No automatic resend, process termination, preference changes or project operations were performed. This attempt does not validate the bridge.

Next diagnostic: manually run the same `workspace/bridge-probes/4d6842da22a2498299360ba70be54dbd/probe.jsx` using AE's **File > Scripts > Run Script File**, then inspect its acknowledgement or collect the exact script error. This separates JSX/file-write behavior from command-line delivery. Only after that result should a fresh, explicitly controlled warm-instance command-line test be considered. Sprint 1 remains pending.

## Manual acknowledgement and warm-instance test — 2026-11-05

After the operator reported manually executing the probe, `verify-probe` validated its matching result: `status: succeeded`, `ae_version: 25.5x4`, `project_item_count: 0`, `error: ""`. Result file size was 122 bytes, filesystem modification time 11:51:57 local. This confirms the trusted JSX and acknowledgement file writing work when invoked through AE's script menu; it does not establish command-line delivery or unchanged dirty state.

Prepared a fresh read-only probe, job `edf719157d9b4cad9ad514efbb03478e`. Before sending, AE PID 9564 was responding with an untitled project. Submitted once through `AfterFX.exe -r` with the quoted absolute script path; launcher PID 32920. Checks through and beyond the 60-second diagnostic window returned `unconfirmed`, with no result file. No automatic retry of that job, AE termination or project mutation was performed.

Conclusion: manual ExtendScript execution and file-write permission are verified; automatic `-r` delivery remains unverified after a controlled warm-instance attempt. Retain `bridge_status: not_validated`. Investigate command-line/instance delivery or an alternative controlled bridge before enabling Sprint 1 editing tools. No new functional code was changed in this follow-up; the prior automated suite result remains applicable.

## Successful direct `-r` attempt — 2026-11-05

At the operator's request, prepared a fresh read-only probe, job `7ece3fc8304b4a1fa61f2c3a3be1308f`. Launched `AfterFX.exe` using Python `subprocess.Popen` with a three-element argument list: executable path, `-r`, absolute JSX path, `shell=False` (default) and `CREATE_NO_WINDOW`. This bypassed PowerShell `Start-Process` argument-string construction. Launcher PID: 4148.

The subsequent verifier returned a matching acknowledgement: `status: succeeded`, `ae_version: 25.5x4`, `project_item_count: 0`, `error: ""`. This is positive evidence of automated command-line script execution and result-file communication on this host. It is not merely launcher success. The probe contains no project mutations; no editable project or render was created.

The root cause of earlier `Start-Process` failures is not established by this single success. Prefer direct argument-list subprocess invocation for the proposed runner and verify repeated delivery, locking, timeout handling and project-state safeguards before enabling editing. Cold-start reliability and project dirty-state preservation remain unverified. The current Sprint 0 MCP diagnostic still deliberately reports `not_validated` until a production bridge runner and capability checks are implemented; this probe result is recorded separately rather than silently promoting runtime capabilities.

## Sprint 1 — implemented and verified on 2026-11-05

The operator approved proceeding to Sprint 1. Added a production argument-list runner, Windows-session mutex, trusted ES3 templates, persistent operation journals, project manifests/hashes, timeout quarantine/cancellation markers, typed creation requests/results, and MCP tools `project_create`, `composition_inspect`, `job_status`. CLI now supports `create-demo`, `inspect`, `job-status`. Updated configuration/status schemas, README, architecture, contracts, installation, decisions, AGENTS and tests. No new dependencies were needed.

### Real AE evidence

- Save/close/reopen and repeated creation test: **1 passed in 4.58 s**, including two distinct AEP paths, matching composition/title metadata, stable Astra IDs, original-file hash preservation and an AE-side refusal to replace a project treated as untracked. The rejected operation produced no AEP and left the active saved file hash unchanged.
- Public MCP stdio → `project_create` → AE → `composition_inspect` → `job_status`: **1 passed in 5.48 s** after correcting `job_status` to an explicit Pydantic output model. Creation and inspection had already succeeded in the initial attempt; its failure exposed missing structured content for a bare `dict` output. That contract is now covered by both the default schema test and the live round-trip test.
- Latest delivered project ID: `c72fd8e20f564926a97e01ccc983fc4e`; operation `a884ef5882274ff0a84307c3784b59ff`; file `workspace/projects/c72fd8e20f564926a97e01ccc983fc4e/project.aep`.
- AE reopened that file and reported one composition named `Astra Sprint 1`, 1920×1080, 30 fps, 5 s; one editable text layer `ASTRA VIDEO STUDIO`, position `[960,540,0]`, anchor `[-1.8017578125,-32.18994140625,0]`, visible bounds `left=-550.3447265625, top=-65.5224609375, width=1097.0859375, height=66.6650390625`, in/out points 0/5 s. Anchor equals the visible-bounds center. No rasterized title or external media dependency.
- AEP SHA-256: `7dd17d3231509b8bb7aea832fb23e8ebf726d9ef6fc9dfc970d5edff45a794af`.
- Final diagnostic operation `08ed0ff8a52b42f68bcd99b0aa2a2670` reported `status: ok`, `bridge_status: acknowledged`. This records successful creation evidence, not a guarantee of future AE readiness.

### Unexpected manual edits were preserved

The first live test created/reopened `8a5badfb39c340d9bc70c2d5961b7d69/project.aep` but Python validation initially rejected three-component 2D transform vectors. Fixed the verifier to accept XY or XYZ with zero Z and added regression coverage.

Read-only follow-up inspection then found an additional empty composition `Astra Demo 2`, absent from the creation acknowledgement. The operator explicitly authorized preserving this state and continuing. The internal reviewed snapshot action saved both compositions to `workspace/snapshots/7bc63af4e38349cca877a130228284e7/preserved-project.aep`, operation `9b29ec091cfd4efca69ebdcf584b86a7`, with a hash and manifest. Only after that successful save was the snapshot closed and a blank project opened. The original failed job and its artifact remain preserved. No unapproved discard or overwrite occurred.

### Automated scope and remaining limits

Default suite covers schema limits/code-injection escaping, acknowledgement and timeout failures, durable quarantine, launch failure, missing AE, instance mutex contention, persisted-result verification, transforms, protocol schemas and invalid MCP calls. Real AE tests remain opt-in via `ASTRA_RUN_AE_TESTS=1`.

Final default suite: `.\.venv\Scripts\python.exe -m pytest -q --tb=short` → **54 passed, 3 skipped in 4.63 s**. The two live cases were verified separately as reported above; no additional AE run was needed for the final journal/timing-verifier adjustment, whose default regression tests passed and whose expected 0/5 s timing is present in the captured live metadata.

The default suite skips the two live AE cases and one Windows symlink-creation case. Real AE evidence above comes from explicitly enabled targeted runs. Save/reopen/inspect establishes project persistence and editability; no visual screenshot review, motion, render, MP4 or aesthetic acceptance is claimed. Cold starts, multiple interactive AE instances, interrupted saves, and cross-workspace timeout recovery remain unverified. A timeout requires manual inspection; delayed scripts check a cancellation marker before mutations, but an already-running operation cannot be safely killed. Use one workspace per AE session. Sprint 2 (transforms, keyframes and initial motion skills) is the next increment.

## Sprint 2 — implemented and verified on 2026-11-05

Added `motion_engine` schemas, easing functions, frame-aware timeline compiler, four presets and versioned edit service; extended the trusted JSX template/inspector, project version resolution, MCP and CLI tools. Updated README, AGENTS, architecture, decisions, contracts and installation; added skill documentation and motion unit/live integration tests. No new dependencies, paid services or API calls were introduced.

### Final acceptance run

Command (PowerShell): set `ASTRA_RUN_AE_TESTS=1`, then `.\.venv\Scripts\python.exe -m pytest -q --tb=short`.

**88 passed, 1 skipped in 59.28 s.** This single combined run includes both Sprint 1 live tests, the new Sprint 2 live MCP/AE test, protocol/schema/runner tests and motion unit tests. The sole skip is Windows symlink creation permission; traversal/absolute-path containment tests passed. The preceding default run after runner changes was **85 passed, 4 skipped in 7.21 s** (three live cases opt-in, plus symlink). No failing test remains in the final suite.

### Delivered editable motion

- Project ID `54047655ae3b4e778225b653bf17257f`; current version `7f446e5b74ea490286a7cb4051e2e793`; final motion operation `4aa1c27e28c842c1889c0498ca0c5997`.
- File: `workspace/projects/54047655ae3b4e778225b653bf17257f/versions/7f446e5b74ea490286a7cb4051e2e793/project.aep`.
- SHA-256: `26cbf724d7dbeb3e72894b07ada036f1e94a4f9536cf06b4579d73bf75618d9b`.
- AE 25.5 reopened/inspected the saved version. One 1920×1080/30 fps/10 s composition with editable `ASTRA VIDEO STUDIO` text; static position/anchor/scale/rotation/opacity were set through the public MCP transform tool before animation.
- Slide-in at 0.3–1.2 s: X=540→985.2 (6% overshoot)→960, Y=540. Four native position keys including quantized settle midpoint; reported Bezier enum `6613`, temporal influence 33⅓%. The odd-frame midpoint has matching incoming/outgoing speed ≈324 px/s.
- Scale pop at 0.3–1.2 s: 82→106→100% with settlement keys. Smooth zoom at 2–8 s: 100→104→108%. Seven native scale keys total, with independent XY ease and unchanged Z=100.
- Fade opacity: six keys at 0, 0.3, 0.6, 9, 9.5, 10 s with values 0, 50, 100, 100, 50, 0. Sampled opacity at 2.5/5/7.5 s was 100; last displayed-frame sample ≈0.0148. Exit endpoint is zero.
- Native expressions remain disabled. Composition/layer motion blur both true, shutter angle 180°. All previous base/version AEP hashes were unchanged at each step; source snapshots exist for every edit. IDs survived every save/reopen round-trip.
- Repeated overlapping motion and static replacement of keyed opacity were refused in the live test. Unit tests cover expression protection, timeline/fps/schema limits, easing math and rejection of unrelated-transform changes. Source hashes are checked by the service and prior-file hash preservation is exercised live; externally saved-source rejection was not independently fault-injected in this sprint.
- Final `studio_status` operation `19096debf37146f49f73e5d7685d4e0f` returned `ok`, `acknowledged`, no pending-job warning.

### Failures found and corrected before acceptance

The first slide operation `5c030349393543df968b211af493a73e` saved its version but verification initially labeled native Bezier as Hold because strict host-enum identity is unreliable in ExtendScript. Read-only diagnostic operation exposed native values and constants, then revalidation `77197d21a6ef4487a021c8ca6995a3f0` confirmed the planned keys/ease, unchanged source hash and clean active project with corrected decoding. The original failed journal is retained; revalidation is recorded separately in that version manifest.

A later combined suite returned **2 failed, 86 passed, 1 skipped**: create job `3198dbc4842b432ba128ff124124462f` had no acknowledgement after 60 s; the next live test was correctly blocked by quarantine. The operator reported a warning about two scripts attempting to run simultaneously, now cleared. Read-only checks found AE responding on the previous project, no timed-out prologue output/result or AEP, and no remaining launcher process. After review, archived the pending record under that job, retaining its cancellation marker, timeout and `recovery.json`. The job was not resent.

Changed report delivery to a fixed AE deferred-task callback (500 ms), followed by a 750 ms mutex-held settling interval. New combined tests with fresh IDs then produced the final **88 passed, 1 skipped** result above. This addresses the observed completion gap empirically; manual scripts, modals, cold starts and multiple AE instances remain outside the reliability claim.

### Remaining scope

No MP4/render or visual frame review was performed; the acceptance evidence is saved-project/native metadata, hashes and real MCP/AE round-trips. The title begins at zero opacity, so view a later frame when reviewing manually. Symlink creation remains the one unavailable platform check. Existing external-project editing, media imports, broader motion skills, masks/effects and previews remain later increments. Sprint 3 is versioned opening/inspection/editing of existing projects. Use one workspace per AE session and do not run other JSX scripts during Astra operations.

## Sprint 3 — implemented and verified on 2026-11-05

The operator approved Sprint 3. Added `ExistingProjectService`, source-path validation with operator-configured external read roots, sidecar identity mapping, MCP tools `project_open_copy` and `project_save`, CLI equivalents, and copy/save JSX actions. Extended the inspector and transform/motion guards for existing-project capabilities, comments, locks, unsupported/3D/separated properties and non-target isolation. Added source/identity/selective-edit unit tests and an opt-in existing-project AE test. Updated README, AGENTS, configuration example, architecture, decisions, installation, tool contracts and `existing-projects.md`. No dependency or paid-service changes.

### Final acceptance

Command: set `ASTRA_RUN_AE_TESTS=1`, then `.\.venv\Scripts\python.exe -m pytest -q --tb=short`.

**102 passed, 1 skipped in 70.62 s.** This combined run includes all four real AE integration cases: Sprint 1 creation/repetition/protection, MCP creation/inspection/journals, Sprint 2 four-preset motion, and Sprint 3 existing-project copy/selective edit/manual-save. The sole skip remains Windows symlink creation permission. Default suite before the combined run: **98 passed, 5 skipped in 7.59 s** (four opt-in live cases and symlink). No failures remain in final acceptance.

Targeted new live test after correcting capability detection: **1 passed in 24.83 s**. The first attempt opened/copied correctly and refused the locked layer, but erroneously refused the text target because `TextLayer instanceof AVLayer` returned false on this AE host. Fixed detection to inspect concrete type and available transforms instead of host inheritance. That first failure occurred before target mutation; the copied source and failure journal remain as evidence.

### Real existing-project evidence

No production client project was supplied. The opt-in test generated an ordinary source AEP with two compositions and four layers: title, locked sentinel with the same layer name, secondary text and a camera. Client comments contained no Astra IDs. This exercises actual existing-file opening with native IDs and unsupported camera inspection; it is not a claim of compatibility with arbitrary client plugins/assets.

- Source: `workspace/fixtures/be2a7de90beb4c9a98e4266b5a86661f/client-source.aep`.
- New managed project: `27be9093795b4ed990249040287461f8`; copy-open operation `19f7cdc1e2cb4580984dd899506cb98a`.
- Original-source backup: `workspace/projects/27be9093795b4ed990249040287461f8/original-source.aep`.
- Original/source/initial copy hash: `ff84877e4302760f38109021a242e5fb8a03ba6a2e8796d1817888f8f0767e36`. The test checked byte equality and later checked the original source and initial copy remained unchanged after editing/saving.
- Selective edit saved version `8d560786e0784a7287679dab2ff27283`: selected title opacity 55%, rotation 8°. Its saved hash `b7ec6af2649208c238b72cbf5b735c4d75da2ade59844b5992383854918c0931` remained unchanged after the subsequent save.
- Locked sentinel retained opacity 37% and all inspected metadata. The entire secondary composition (including camera) and all other inspected layers/settings remained equal. Source comments were unchanged; repeated names did not affect target resolution.
- Explicitly simulated manual rename/duplication inside the managed throwaway test copy, resulting in unsaved state. `project_save` captured this into version `76a606d5b1e148aa9590aafee1a61445`, operation `217b0a5260b44f9b8304cd5726fe4050`, then reopened/verified the state. No source or parent AEP was overwritten.
- Saved file: `workspace/projects/27be9093795b4ed990249040287461f8/versions/76a606d5b1e148aa9590aafee1a61445/project.aep`.
- Saved SHA-256: `0733391866237b92ef65ba66197d0f844e1c586a0a012c8dbe3e4512f0529ee8`.
- Existing title native ID 13 retained UUID `1bf8da80dc5d4372aeea05df57216cf7` after its index changed. Newly duplicated native ID 29 received UUID `661815e84c874c02b105a92791deffe2`. Both retained `Original client title comment` without rewriting. A separate unit regression covers an Astra-comment duplicate inserted before its original, seeded from verified metadata so it cannot steal that UUID.
- Final `studio_status` operation `d686678c489146918ea63b26c7d3feba` returned `ok`, `acknowledged`, with no pending-submission warning.

### Source permissions and evidence limits

Unit tests verify workspace-relative sources, rejection of unapproved external sources, acceptance of operator-configured roots, invalid files, absent sources without submission, mapping uniqueness/reordering/comments, externally changed-source hash rejection before AE dispatch and unrelated-layer verification. The source fixture/live test used the workspace; external folder configuration was tested at the Python validator layer, not by opening a separate real external production project.

Copies/backups and saved versions are verified by bytes/hashes and real AE reopen/inspection. Linked-media references, cameras and unavailable properties are inspectable; camera/light/3D/locked/separated targets are not editable through the 2D tools. AE may resolve media and expressions outside the workspace when opening a trusted project; Python's source path policy is not a native application sandbox. Missing media/plugin/font recovery and collect/relink are not implemented.

Isolation is based on all inspected non-target layers/compositions and target metadata, not exhaustive effect/plugin serialization or rendered-pixel comparisons. No visual review or MP4 preview was performed. Interrupted saves, cold-start/multiple-instance routing and universal modal-free automation remain unverified. Deferred acknowledgement/settling and timeout quarantine remain enabled. The earlier authorized snapshot of the user's manual edits remains intact.

Sprint 4 (selected native effects, basic masks and verified preview rendering) is next; it was not implemented as part of this sprint.

## Sprint 4 — implemented and verified on 2026-11-05 (client-local)

The operator approved Sprint 4. Added allowlisted Fill/Gaussian Blur, editable rectangle/ellipse masks, inspection/verification of appended treatments, a bounded preview worker queue, cancellation requests, native-render logs/persistent ownership, image-sequence validation, FFmpeg encoding, ffprobe checks/full decode and extracted PNG samples. Added MCP tools `effect_apply`, `mask_create`, `preview_render`, `job_cancel` plus CLI equivalents. Retained snapshots/version promotion and source preservation.

Repeated per-operation command-line delivery failed during live validation, so replaced it with a reviewed once-started idle bridge. Added heartbeat/session/startup/inbox tracking, single-UUID publishing, fixed trusted-template path dispatch and stale/active-job guards. CLI `bridge-start` and `studio_status.bridge_runtime` expose setup/readiness. Updated architecture, contracts, installation, decisions, README, AGENTS, configuration example and `preview-rendering.md`. No paid service, dependency installation or generative video API was used.

### Final combined acceptance

Command: set `ASTRA_RUN_AE_TESTS=1`, then `.\.venv\Scripts\python.exe -m pytest -q --tb=short`.

**139 passed, 1 skipped in 117.06 s.** This final run includes all five real AE cases: Sprint 1 repeat/safe creation, public MCP creation, existing-project selective edits/manual save, four-preset motion, and native effects/masks/rendered MP4. It also includes schema/planner/runner/idle-transport/preview queue/cancellation/failure tests. The sole skip is Windows symlink creation permission. No failure remains in final acceptance.

An earlier combined run, before adding the durable pre-launch renderer marker and its two focused tests, passed **137, skipped 1 in 110.72 s**. The final 139-test run verifies that additional guard as well; these are not two counts added together. Default-only tests had passed 131 with six skips before the final sequence/renderer tests were added; the skips then were five opt-in live cases and symlink. The final combined run is authoritative.

### Final artifacts and real rendering evidence

- Preview job `844f9a6ddc6d49e08aad422d3331d047`; AE preparation operation `acae0746273a4ebbbde719331dfe23be`.
- Editable project `afb6fd30e62c47f5aae3efd2fa2ab2d1`, version `26de5ac38a9547368757076611d9b462`.
- AEP: `workspace/projects/afb6fd30e62c47f5aae3efd2fa2ab2d1/versions/26de5ac38a9547368757076611d9b462/project.aep`.
- AEP/source SHA-256: `93fdefad7c45b59d1ee3c335d889d402eb8bf4bb645c39db1171424c11c23ee6`.
- MP4: `workspace/jobs/844f9a6ddc6d49e08aad422d3331d047/preview.mp4`.
- Video SHA-256: `86cf3cea8e364eeef5c834d72e0615762faebd292120590ec39806e235bdd6c2`.
- Native AE 25.5 preparation wrote one private render-queue item for 0–3 s, using the installed `TIFF Sequence with Alpha` template. `aerender.exe` rendered the disposable copy without `-reuse`; the prior saved interactive project was restored and remained inspectable at its original path. The AEP source hash and initial creation bytes remained unchanged in the live test.
- Exact nonempty contiguous sequence: **72 frames**. FFmpeg produced **3.000 s, 960×540, 24 fps, H.264, yuv420p**, no audio. ffprobe counted 72 decoded frames; a separate full FFmpeg `-xerror` decode succeeded. Renderer/encode/probe/decode/sample logs are retained in the job directory.
- Three sample PNGs (start/middle/near-end) and the private `render-copy.aep` are retained. Temporary job-owned TIFF sequence files were removed only after MP4 validation. The private render queue, not the source queue, was rendered.
- Native Fill color `[0.3,0.85,1]`, Gaussian Blur amount 0.8/repeat edges true, an Add rectangle with feather 2 and a separate Subtract ellipse were saved/reopened and inspected before animation/render. Prior effects/masks and other inspected state were preserved. Slide/fade native keys remain editable in the final AEP.
- A separate earlier native render job `f5bce0b3b9d949b6a88e82b04d0b4872` produced the same MP4 SHA-256 for a fresh but visually identical test fixture, providing evidence of repeatable output for this case, not a universal determinism guarantee.

### Sampled visual review actually performed

Viewed all three final PNG samples with the local image viewer. The first/near-end samples show the dark background consistent with fade endpoints. The middle sample shows the complete cyan `ASTRA VIDEO STUDIO` title centered with visible margins, legible text and no visible clipping in that sample. This is sampled-frame inspection, not playback of every frame or artistic sign-off. The full video was decoded functionally but not watched in real time.

### Failures found, preserved and corrected

1. First Fill operation succeeded, but a later read-only inspect `f1d3368a7ca64230918a824a99f75fcb` received no acknowledgement after 60 s. It remained cancelled/quarantined; no subsequent script was resent. A later bootstrap -r attempt also lacked a heartbeat. Read-only UI diagnostics found AE's main window disabled and an enabled native modal. No dialog was clicked or dismissed by Codex. The operator reported closing the message and executing the generated bootstrap manually; heartbeat instance `f355dbcba2a14844a503602713da0b71` became fresh. After review, archived only the cancelled legacy inspect pending record, retaining `cancelled`, original timeout and `recovery.json`. The new idle inbox then executed sequential jobs without per-operation launches.
2. Mask operation `9bd542ed9dbc4081846ba3d4201e599f` saved a valid Add path, but strict host-derived comparisons reported its native value 6813 as Subtract. Read-only checks exposed Add=6813/Subtract=6814. Explicit numeric-difference conditionals report the correct modes; both Add and Subtract are verified in final live acceptance. Retained the original failed journal/artifact and preserved it separately as an inspected copy instead of silently promoting that failed operation.
3. Preparation `ee07e561f09248a49503d17179456876` failed before rendering because PNG Sequence is not installed. The actual template list includes TIFF Sequence with Alpha. Added detected lossless TIFF fallback, consistent-format sequence checks and TIFF/mixed-format unit coverage. No template or codec support was invented/installed. Final rendering uses the discovered TIFF preset.

### Reliability checks and remaining limits

Tests cover malformed/nonfinite effect/mask/preview values, geometry, invalid spans/size, missing/discontinuous/mixed image sequences, wrong MP4 count/duration/FPS/resolution/codec, queued cancellation without process launch, source changes while queued, renderer errors/timeouts, persistent marker before native launch, blocked competing render, occupied inbox, stale heartbeat/session and no repeated CLI launch for a live listener. The native marker is written before aerender so a host interruption leaves a review boundary; interrupted jobs are not automatically resumed. Active native cancellation is a request, not immediate engine termination. Unknown native processes keep preview quarantine; interactive AE is never killed.

Final `studio_status` operation `16d235005ae547a581e3aef49058beb2` (UTC `2026-11-06T02:52:12.770242+00:00`, client-local Nov 5) reported `ok`, historical bridge `acknowledged`, runtime `idle_inbox`, ready true and no active job or pending warning. Manual listener startup was needed on this host. After AE restarts, stale known sessions require reviewed manual bootstrap reactivation; unattended cold-start recovery is not validated.

Current previews are silent, local and bounded to 15 seconds/4K source/900 frames with even MP4 dimensions. Linked media/plugin/font recovery, audio previews, mask animation, arbitrary effects, native engine process-tree cancellation, interrupted-job auto-resume and universal modal-free execution remain outside acceptance. Keep one workspace per AE session and the MCP host alive for queued work. Earlier user-approved backup of manual edits remains preserved. Sprint 5 (scene planning, direction/review and broader skills) was not implemented in this increment.
# Sprint 5 — final MVP acceptance

Implemented the Director, immutable hashed plans, bounded Portuguese revision, native layer/media creation, batch/stagger motion, text reveal, shake, parallax, reference extraction and explicit review records. The MCP schema contract now checks 22 tools with structured output. No paid service or dependency was added.

Final complete regression with `ASTRA_RUN_AE_TESTS=1`: **157 passed, 1 skipped in 246.94 seconds**. All seven native AE cases passed alongside the unit/MCP/transport/render failure tests. The sole skip is Windows symlink creation permission. Exact output is retained in `workspace/sprint5-regression.log`. No implementation changes followed this run; subsequent work only recorded review evidence and documentation.

Final diagnostic is retained in `workspace/sprint5-final-status.json` with logs separate: status `ok`, idle inbox ready, no active job. This verifies the current listener state; unattended startup after restarting AE remains outside acceptance.

## Final scene evidence

- First execution `3de5f6a604044f1ea84be7d653a6ed09`, plan `8c0a4d31322a41e0b004b5d58dfe8f34`.
- Natural revision: `Troque o título para "ASTRA EM AÇÃO" e reduza overshoot para 3%.`
- Revised execution `bc03c8c2381d4122a093ef612705ea33`, plan `716824fcefc3470bbb0958fa80bc6a42`, project `029b928d3df74c348cbdb52207dfe240`.
- Revised editable AEP: `workspace/projects/029b928d3df74c348cbdb52207dfe240/versions/f4148843ccdd4a54bcf033e109aa52e2/project.aep`.
- AEP SHA-256: `fee3b50ed5f4264568d5662c8f73516b841e3e67c71d62c999b4a6522fbbb9c1`.
- MP4: `workspace/jobs/cb86fe617a774e66a4ba71d6e957b124/preview.mp4`.
- MP4 SHA-256: `a9117f4e26a9c7bdb3cd6b636adbbf39f961892116318c9475e7bc623d521a6b`.
- **12.000 seconds, 1280×720, 24 fps, 288 frames, H.264/yuv420p, silent**. ffprobe count/metadata and a separate full FFmpeg decode passed. Native TIFF sequence rendering uses the actual installed AE template.
- Nine editable native layers and seven techniques: slide, scale pop, fade, text reveal, staggered accents, parallax and shake. Layer IDs and native keys/mask keys survive save/reopen. Text has explicit normal caps. The natural revision retains the project ID, creates new versions and preserves the first AEP hash.
- Separate native acceptance creates text, shape, solid and imported-image layers, checks copied image bytes and original preservation, then applies stagger in one verified version.

## Actual sampled review

Viewed the final preview's middle PNG and additional matching-video samples at 1.5, 6 and 10.8 seconds. Reference `361037183674433789bcc0bc9f381d9b` retains the samples and matching video SHA. The title is legible and centered with margins; the subtitle is still revealing at 1.5 seconds and fully visible at 6 seconds in its intended mixed case. The cyan closing and signature are legible. The large decorative circle extends beyond the frame intentionally.

Recorded these actual observations in `workspace/plans/716824fcefc3470bbb0958fa80bc6a42/review.json`, assessment `acceptable_samples`. Scope is sampled frames only; full_video_watched is false. Full-playback rhythm and artistic approval remain human checks. Reference extraction explicitly reports visual_analysis_performed=false, avoiding a claim of automatic semantic analysis.

## Scope and limitations

Unit coverage includes duration/FPS boundaries, unsupported or partially parsed revisions, integrity changes, deterministic shake, native reveal plans, stagger collisions and the preceding-position baseline for appended motions. Integration covers public MCP brief→scene→render→Portuguese revision→render, source preservation and layer/media creation.

The Director uses a local template and bounded phrases/typed changes. It rebuilds its own unchanged scene into new versions; it does not merge arbitrary manual changes. The MCP host must stay alive for queued rendering. Current output is silent; semantic reference analysis, audio synchronization, cameras and a product panel remain future work. Earlier transport timeouts, modal recovery and preserved user work remain documented in the historical reports below.

# Sprint 6 — multi-composition scene editing

Implemented ten typed scene tools, for 32 MCP tools total. New files are `scene_editing.py`, the fixed `scene_ops.jsx` template, unit scene tests, native scene acceptance and `docs/scene-editing.md`. Updated the inspector, trusted action allowlist, MCP/CLI entry points and prior motion verification to account for recursive animation counts. No dependencies were added.

## Acceptance scope

The native MCP scenario creates a 960×540/24 fps/20-second master with three nested scenes. It exercises composition creation/settings, duplicate/rename/reorder/remove, static frame shift/lifetimes, null transforms, world/local parenting, all four allowlisted blend modes, alpha/luma/inverted/remove mattes, precompose, composition insertion and both FPS policies. It checks dependent-removal, relation/composition cycles, selection-boundary and duration-trimming refusals. Final regression additionally verifies that an animated layer cannot be shifted or frame-retimed by these structural tools.

Save/reopen verification checks stable IDs, composition/source references, parent/matte relations and retained inspected metadata before promoting each version. All generated AEP versions are hashed and checked unchanged after subsequent edits and rendering. A three-second excerpt is rendered with the existing isolated TIFF→H.264 pipeline. The 20-second master does not imply that preview duration limits were raised.

An isolated native acceptance passed in **182.89 seconds** before the final animated-timing guard assertions were added. The final complete regression below is authoritative.

## Final complete regression and artifacts

With `ASTRA_RUN_AE_TESTS=1`, the full suite passed **191 tests, 1 skipped in 398.16 seconds**. All eight native AE cases passed; the sole skip is Windows symlink permission. Exact output: `workspace/sprint6-regression.log`. No implementation changes followed this run.

- Project: `1f7b350f40b4464b9fdf8bc3215622d3`; master `acf8a8007da5476181176fff2c2f7595`.
- Editable AEP: `workspace/projects/1f7b350f40b4464b9fdf8bc3215622d3/versions/273eed1844b94676810a1dfd8d094d4d/project.aep`.
- AEP SHA-256: `acdb7d5fc31f6ff18a342ba8f8869655262f73c637c04896ed1f08c18ef378a7`.
- Three scene composition IDs: `59c92e546dc4466a969888a3608084be`, `b597d215e49942bda208a3b34edf3626`, `019597876f5941cab77fe01f1689e6d7`.
- All **40** generated AEP files retained their hashes after later edits and render. The final scenario edits Scene 02, leaving the other inspected scenes unchanged, and checks the animated-timing refusal.
- Preview job `7639d8a06f274e2f96fabd0c4a12fd38`, MP4 `workspace/jobs/7639d8a06f274e2f96fabd0c4a12fd38/preview.mp4`.
- MP4 SHA-256: `a92a31195491114228686be2af875d37294ccaf649a603dc8af2eb29e8a6dee1`.
- Master interval 6–9 seconds, output **3.000 seconds, 960×540, 24 fps, 72 frames, H.264/yuv420p, silent**. Native sequence, ffprobe and full FFmpeg decode passed. This excerpt is not a render of all 20 seconds.
- Machine-readable evidence: `workspace/sprint6-acceptance.json`. Final diagnostic: `workspace/sprint6-final-status.json`, logs separate; status ok, idle inbox ready and no active job.

Actual visual review inspected the entry, middle and an independently extracted near-end frame at 2.9 seconds of the excerpt. The cyan title is offset left on entry and centered/readable with margins in the later images. The viewer presented the original near-end sample as dark, so it was not accepted by assumption: a separate extraction was viewed correctly, and decoded pixel comparison confirmed it identical to the original sample. No video defect was established at that instant. Evidence is in `workspace/sprint6-visual-review.json`; full_video_watched remains false. This is a structural acceptance fixture, not artistic approval of a finished professional piece.

## Issues found and corrected

1. AE persisted background `[0.015,0.025,0.05]` as `[4/255,6/255,13/255]`. Operation `8d0ca7f468a14a03b39d2f3ce2d6e29c` was retained as verification-failed. Added exact expected 8-bit quantization and a focused test rather than weakening all numeric comparison tolerances. Preserved an inspected recovery copy without promoting the original failed version.
2. Clearing parenting by omitting the setParentWithJump argument failed on this AE (`dcba356a43fb4f16a983a7553a532baf`). An explicit null works and is now exercised in native acceptance. Saved source versions were untouched.
3. Nested host ternaries labeled a precomp source as footage. A deliberately cyclic insertion reached AE, which refused it (`722bf6f874904b77bb05b2beb1784cc3`); the next requested operation correctly failed because the unpromoted file was active. Changed source type detection to explicit conditionals, made Python composition edges depend on source native IDs, and added an independent native cycle check before saving/mutation. Added a regression where the type label is deliberately incorrect. Preserved the failed file/journals and recovered through an inspected copy.
4. A default-only test run executed concurrently with the native scenario encountered the intentionally shared machine mutex. This was test contention, not evidence of an AE execution failure. Final regression runs all tests sequentially; concurrency between real AE jobs and mutex unit tests is now documented as unsupported.

## Limits retained

Scene editing blocks stored project expressions, ambiguous/locked/unsupported targets and unresolved dependencies. Frame-preserving FPS changes are limited to static still contents; general keyframe retiming remains future work. World-preserving parenting requires static 2D ancestry without auto orientation. Precompose verification is structural/metadata-based, not a universal pixel equivalence guarantee for arbitrary client plugins/blending. Preview/full-playback/artistic evidence remain distinct. No Sprint 7 typography/vector work is included.

# Sprint 7 — typography, vectors and identity layouts

Implemented ten tools, bringing the server to 42: installed-font inventory, text styles/ranges, native text animators, managed Bezier groups, solid fill/stroke, Trim Paths, compatible morphs, strict-subset SVG import, immutable identity tokens and responsive layouts. Added `design.py`, `svg.py`, `design_ops.jsx`, unit/native design tests and `docs/design-tools.md`; extended the inspector, layer factory, MCP/CLI and fixed-template allowlist. No dependency or paid API was added.

## Native acceptance and final artifacts

The real MCP case builds an editable five-second brand card at 24 fps, using an SVG mark converted into native paths, a styled point title, an accented multiline paragraph subtitle and a Bezier accent. It adds word/character entry animators, compatible path morph and Trim Paths. It checks missing-font refusal, overflow rejection/restoration and explicit overflow reporting, unsupported-gradient refusal, incompatible-morph refusal, square/landscape/portrait adaptation, all alignment modes and both distribution axes.

An isolated native run passed in **161.45 seconds** before the final square/horizontal-distribution and interpolation-inspection additions.

Final complete regression with `ASTRA_RUN_AE_TESTS=1`: **233 passed, 1 skipped in 595.30 seconds**, including all nine native AE cases. Exact log: `workspace/sprint7-regression.log`. The sole skip is Windows symlink permission.

Four additional pure SVG boundary/consistency cases were added after that run collected its tests. The final default suite on the final code passed **228, skipped 10 in 6.50 seconds**, recorded in `workspace/sprint7-default-final.log`; its skips are the nine opt-in native cases plus symlink permission. Together the runs cover **237 distinct passing cases** and one platform skip; overlapping counts must not be summed. No source implementation changes followed final default verification.

Final diagnostic `workspace/sprint7-final-status.json` reports status ok, idle bridge ready and no active job, with stderr separate in `.log`. Cold-start recovery and full artistic playback remain outside acceptance.

- Project ID: `88d9a07596f14a6f994ca0f48cb92419`, composition `b1bb940b9ff943c98755af6c1f320873`.
- Landscape AEP: `workspace/projects/88d9a07596f14a6f994ca0f48cb92419/versions/a949e8c6f3154345a1eabc8c3c7610b1/project.aep`.
- Landscape AEP SHA-256: `fd12ea41468200a68db20fe073a938765a655106647e0cf86607685c0e217bb3`.
- Portrait AEP: `workspace/projects/88d9a07596f14a6f994ca0f48cb92419/versions/f65b8909916645d1a164e4c7857e8f7e/project.aep`.
- Portrait AEP SHA-256: `1fd3fdf7f0a32805123aed1ebc9af99a09683357a62a9c6b280756ae2855133c`.
- **26 verified AEP files** retained their hashes after subsequent edits and renders. Original SVG and copied SVG bytes also matched. Expected failed outputs are retained separately and are not counted as verified versions.
- Landscape preview job `187d588dc40843bfa5390eca6cb26379`, MP4 under its job directory; SHA-256 `28db132d2eddad24b993bf285db32e7a21991a61c79601d0b0cc6d9014912667`.
- Portrait preview job `98b6939357c84c7387d8038a3703dd6b`; MP4 SHA-256 `e53cec3bf4936c0b6a0d3360b44436a7a1e316cea3149a658244302b81db02e7`.
- Each preview is **3.000 seconds, 24 fps, 72 frames, silent H.264/yuv420p**. Landscape is 960×540, portrait 540×960. Native sequence, ffprobe count/metadata and full decode passed. The editable compositions are 1920×1080 and 1080×1920, five seconds; only excerpts were rendered.
- Machine-readable acceptance: `workspace/sprint7-acceptance.json`, including immutable token record and SVG fixture location.

## Actual frame review

Inspected entry, middle and independent near-end extractions from both final MP4s. The mark appears initially; typography and the curve are visible after their entries. The title has cyan ASTRA/white STUDIO; accented subtitle lines remain legible with margins in landscape and portrait. No overflow was reported by native composition or the checked safe areas.

The viewer sometimes presented incomplete PNG regions. Independent near-end extractions were opened, and decoded RGB hashes matched the original samples. This is not evidence of missing video pixels. Review provenance and notes are retained in `workspace/sprint7-visual-review.json`, scope sampled_frames_only and full_video_watched=false. The final rerun produced byte-identical videos; `workspace/sprint7-final-review.json` explicitly links their matching video hashes to the actual inspected artifacts from jobs `78f6cb80f72b4d25bd63ee19fc7e7026` and `ad9cf6ef0f884b03bfede9a6a4e64495`. It does not invent another playback. Neither complete rhythm nor client artistic approval is claimed.

## Issues found and corrected

1. AE's 2D text animator retained Z scale at 100 even when XY was 96. Native execution `63042be3c4e347e68e5a2c2e591d68b0` was retained as verification-failed; preserved an inspected copy and changed both assignment and verification to XY=request, Z=100.
2. A layout token requested 32.0004 px over an existing 32 px font. AE retained 32, producing verification failure `18bc8cd080014cf4b4eb87cf5ba054e5`. A separate controlled measurement (`2a4d499caaae4b069348e0380ee3126c`) persisted 32.123456 as approximately 32.12345886, showing that this was a small-change issue rather than integer-only font support. Defined explicit design precision of 0.01 px in both assignment and expected values; no broad numeric tolerance was relaxed.
3. Invalid font and paragraph overflow cases are deliberately exercised. Missing fonts fail before mutation; a known synchronous overflow failure preserves its job-owned file and restores the checked-clean source. These are expected error paths, not timeouts or silent substitutions. No native command was blindly retried.
4. The first complete run reported **232 passed, 1 failed, 1 skipped in 572.91 seconds**. The failing existing-project test had inserted its manual-edit fixture by matching the old result-collection line, which changed for font inventory. It silently failed to inject the simulated edits. Added a stable comment insertion point and an assertion that it appears exactly once; the actual manual-edit/save test then passed in **21.92 seconds**. The prior log is preserved in `workspace/sprint7-regression-before-fixture-fix.log`. The subsequent complete run determines final acceptance.
5. Final review strengthened SVG read/copy consistency: parse and retain the same bounded byte payload, then refuse a source change rather than copying later bytes that differ from the parsed geometry. Added two pure tests for unchanged and concurrently changed sources, plus two for nested viewports/nonplain metadata that the subset must reject. The latest focused design suite passed **45 tests in 0.43 seconds**, recorded in `workspace/sprint7-design-unit-final.log`. These four cases were added after the complete run had collected its tests; counts overlap and must not be added wholesale. Final default-suite verification covers these guards on the final code.

## Unit/MCP coverage and remaining limits

Coverage includes invalid/nonfinite shapes/colors/ranges, tangent counts, immutable token integrity, Unicode code-point→UTF-16 ranges, frame boundaries, exact curve conversion/closure, malformed SVG, UTF-16/NUL/DTD/entity/namespace boundaries, unsupported transforms/external elements/styles and MCP schema output. The final suite also retains all prior native acceptance cases.

Gradient color stops are explicitly unavailable in the bridge. SVG import is a bounded native-path subset, not arbitrary Illustrator/SVG support. Layout needs unparented static local transforms and verifies mid-comp bounds; it is not all-frame collision analysis. Existing transform/keyframe replacement, audio, full delivery packaging and richer art direction remain later roadmap stages.

# Sprint 8 — guarded native animation editing

Implemented six tools (48 total), guarded key CRUD, temporal ease, spatial tangents, grouped transform retime and explicit blur settings. Added the eighth skill anticipate_settle through existing motion/batch/stagger. New files: `animation.py`, fixed `animation_ops.jsx`, unit/native animation tests and `docs/animation-editor.md`. Extended curve/blur inspection, CLI/MCP and preview completion fault propagation. No dependency or paid API was added.

## Restart and bridge evidence

After the operator reported a computer restart, status `acff57cad1b94cd29514a484290daab6` showed historical acknowledgement but stale runtime heartbeat. AE was open, no job/native-render/inbox pending markers existed, and no automatic -r relaunch was attempted. The operator executed the existing bootstrap manually. Status `e72831e6a4674d3b87dce675da936c99` then showed a fresh ready idle bridge and native font read `1676dd35bd9b4b1594561d93b44ae365` was acknowledged by AE 25.5x4.

## Native acceptance and artifacts

An isolated full editor acceptance passed in **168.78 seconds**. Final complete regression with `ASTRA_RUN_AE_TESTS=1`: **269 passed, 1 skipped in 817.60 seconds**, including all ten native AE cases. The sole skip is Windows symlink permission. Exact output: `workspace/sprint8-regression.log`. No implementation changes followed this final regression.

Final diagnostic `workspace/sprint8-final-status.json` reports status ok, idle bridge ready and no active job, with logs separate. No AE/native-render pending marker remains. Source AEP and before/after MP4 hashes were rechecked against the acceptance evidence after the suite.

The public MCP scenario creates a five-second/960×540/24 fps title and independent sentinel. It validates staggered anticipate_settle entries on disposable layers, removes only those fixtures, then creates a baseline entry/scale/fade and exit. It exercises insert/update/move/remove/replace, Linear/Bezier/Hold, stale source/track refusals, preserved-boundary refusal, spatial curve editing, group retime, collision refusal and blur settings/restoration. Two isolated native renders are fully decoded.

- Final project `688197bfe7e64f40a60ca218c4f96241`, composition `4cc82205e1b04b5da02a740febdf11ca`. `workspace/sprint8-acceptance.json` retains the complete evidence.
- AEP: `workspace/projects/688197bfe7e64f40a60ca218c4f96241/versions/c9c37bf187d4494fafa84a348cbf3bd1/project.aep`.
- AEP SHA-256: `d1c48b3f25e7567498c767607afe481c1e87a0f81de3886275a8bedabf14e859`.
- Before preview job `f7c1df264b7b44afada3b520324ed6dc`, MP4 SHA-256 `41d1ee914f056971ac13315b884ab0d8bde1d8863fdc558a8fca4f3fa17dbeaf`.
- After preview job `555255fc7e8c4c859aa375529be80473`, MP4 SHA-256 `31c63b257568a60641656d4a22d6b0445e7c8124f8f7f298e9bbe068384ed099`.
- Both MP4s: **5.000 seconds, 960×540, 24 fps, 120 frames, silent H.264/yuv420p**. ffprobe and independent full decode passed. Native rendering uses the installed TIFF sequence preset.
- **21 verified AEP files** kept their hashes after subsequent edits/renders. Exit position keys and the entire sentinel transform state remained unchanged; opacity/fade track also remained unchanged.
- At 4.5 seconds, before/after decoded RGB mean absolute difference was **0.1379365998/255**. This is one sampled frame with lossy encoding, not a claim of bit-identical exit video.
- A curved trajectory sample before retime at 0.5 seconds was `[409.417109989653,182.318321299879,0]`. After doubling the entry duration, the sample at 1 second was identical, supporting the internal speed rescaling as well as native metadata checks.

## Actual sampled review

Reference `1abcde5861a245cc8eddcc1dc857a3de` sampled the baseline at 0.5/4.5 seconds; reference `1d0abf0307444c9790942fb0469853b7` sampled the revision at 0.5/1/2.5/4.5. Actually viewed all six PNGs. The new entry follows an elevated arc and takes longer to settle; its first sampled frame is partly outside the left edge during entry. At 2.5 seconds the title is centered and legible. Exit samples show similar faded/rightward motion; the lower sentinel is unchanged. This is a functional fixture, not final artistic direction.

`workspace/sprint8-visual-review.json` records matching video hashes, actual inspected files, scope sampled_frames_only and full_video_watched=false. Full playback/overall rhythm is not claimed.

## Issues found and handled

1. Native edit `1c1e40a03f214259b29c35d10247f9a3` saved the intended keys but failed verification because AE derived Linear temporal ease as influence 16.666666667 and segment-dependent speeds (e.g. 280 px/s), while the plan contained placeholder Bezier-style values. Retained the failed artifact and inspected a separate copy. Added semantic comparison/fingerprints that exclude inactive Linear/Hold ease records while strictly retaining actual keys, flags, geometry and Bezier controls. Explicit ease input paired with Linear/Hold is refused. No broad numeric tolerance was relaxed.
2. Preview `67a5a4c899594987be30c8d80ae7d643` produced/decoded media and samples but remained running without a terminal journal; its test owner later exited. The original completion exception was not captured. Direct-Future diagnostic render `cdb7417bbe1c483a87328cce12352ffb` completed successfully, so no unsupported root-cause claim is made. Confirmed the original owner was absent, retained a byte-identical journal backup plus artifacts, and conservatively marked the orphan failed with `recovery.json`; never promoted it or resent its command.
3. Hardened atomic JSON replacement with bounded retries only for PermissionError, observed uncaught Future exceptions, added failure-only fallback reporting and ensured slot release even when terminal recording fails or a Future never starts. Focused tests simulate sharing/permanent denial and finalization faults. This is fault propagation, not general persistent restart/recovery from Sprint 13. Native pending markers are still retained on unknown execution.

## Limits

Edits are manual 2D transform tracks, not arbitrary text/path/effect/audio key editing. Expressions, automatic/continuous/roving tracks and separated dimensions are protected. Boundary preservation covers values/outside-facing controls, not automatic C1 continuity. Retime declares rounding and preserves composition/layer duration. Legacy append-only motion protections remain. No Sprint 9 revision engine is included.


# Sprint 9 — guarded property revisions and manual collaboration

Implementation: five typed MCP tools (`revision_plan`, `revision_apply`, `version_compare`, `version_restore`, `director_revision_plan`), **53 tools total**. Closed content/style/static-transform/timing/manual-animation patches reuse the prior verified contracts. Plans and property/dependency guards are immutable/hash checked. Conflicts are reported before capture/mutation; compatible unsaved edits require explicit capture into a new saved/reopened version. One native patch operation returns intermediate states and only promotes after per-step and disk-round-trip verification. Restore appends a byte-identical workspace copy and retains intervening history. Legacy sidecars are reconstructed from verified native-ID/UUID pairs.

## Automated and native acceptance

- The initial default regression passed **284 tests with 11 skips** before the final three legacy-version tests and new native case were added. The focused revision unit suite then passed **28 tests**. Final complete regression (`ASTRA_RUN_AE_TESTS=1`): **298 passed, 1 skipped in 984.90 seconds (16:24)**, including all **eleven native AE cases**. The sole skip is Windows symlink permission. Exact output: `workspace/sprint9-regression.log`.
- An isolated native acceptance passed in **85.67 seconds**. A test-only reviewed fixture simulated unsaved operator color and anchor edits on a new disposable project; it did not add a public arbitrary-code interface.
- A content + position-entry patch changed the title to `REVISÃO PONTUAL` and shifted only the selected entry keys by **6 frames at 24 fps**. The changed manual fill and anchor, key values and complete sentinel layer metadata were preserved.
- Refusing capture without explicit opt-in left the dirty native state intact. Explicit compatible capture produced a distinct version before patching. A subsequent manual text conflict returned `blocked` with the `/text` property path, left the manifest on the prior verified patch and did not save over the dirty work. The test then explicitly saved that manual state before restoring.
- Native restore kept the chosen AEP bytes identical in a new version. Additional patches exercised text fill, static rotation and static layer timing; a final restore retained the accepted title patch and original sentinel.
- Unit checks cover closed schemas, mixed-style/animated/expression/locked target refusal, disjoint scopes, plan integrity, stale current hash before AE access, conflict reporting without mutation, explicit capture policy, preservation verification, timeout/no-replay/no-promotion, metadata comparison and legacy sidecar/probe normalization.
- All tool schemas and exact 53-tool listing are checked through the real stdio MCP handshake. The native revision fixture uses the same service/bridge implementation directly; this distinction is intentional.
- The first local test invocation encountered Windows temporary-directory access restrictions; a second restricted invocation using a workspace temp directory stalled. Only those exactly identified Python test processes were stopped. The unrestricted normal suite passed; no interactive AE process was terminated and no uncertain native command was resent.

## Artifacts and review scope

The complete-regression run writes `workspace/sprint9-acceptance.json`, linking the exact project, plan/hash, manual capture, parent/patch/final versions, conflict evidence, tracked AEP hashes and rendered video. After the suite, final AEP/video and all nine tracked AEP hashes were checked again. All 68 implementation/test file hashes in `workspace/sprint9-implementation.json` remained unchanged across the final regression; only documentation/evidence was updated. Final status `workspace/sprint9-final-status.json` reports status ok, idle bridge ready and no active job; no AE/native-render pending marker remains. Final audit: `workspace/sprint9-final-verification.json`. Do not infer artistic approval or full playback from metadata or decoding.

## Deliberate limits

Content replacement is a static one-paragraph, uniform inspected-character-style subset without text animators. Text/style is guarded as one native document when styling; transform tracks are guarded independently, including complete selected animation tracks. Overlapping patch writes are rejected rather than sequentially inferred. Existing expression, automatic/continuous/roving, separated-dimension and boundary protections remain. Evidence size is bounded before submission. AEPs modified in place on disk fail their historical hash. Optional manual capture does not promise general reconciliation of added/duplicated objects; save structural manual changes explicitly first.

The Director recognizes only fully matched `trocar título para "TEXT"` and `atrasar entrada N frames entre A e B` clauses separated by semicolons. Delay targets position keys; unknown clauses fail the whole plan. General host interpretation uses typed operations. Full scene rebuild remains separate. External assets are not restored with AEP history. Audio and final delivery remain future sprints.

Final revision acceptance project: `befe836340c74b00a74ff92ba1864bf4`, composition `62d3f0f381504391964e2a26c4d39dda`. New final AEP: `C:\Users\ryanb\Documents\Codex\AstraVideoStudio\workspace\projects\befe836340c74b00a74ff92ba1864bf4\versions\a580f6a329864ec0a80acf89e7af6fff\project.aep`; SHA-256 `0d5fa12b3311f4cb29e824db0a389f306b016da9ad703a90fe325928c5ada42a`. Captured manual version: `e28decaf560842308b8368c93c20ec98`; accepted property patch: `6a8b1391303e4b4185b6bda34ecd0661`; final restored copy: `a580f6a329864ec0a80acf89e7af6fff`. The native case checked **9 tracked AEP files** for retained hashes.

Final video: `C:\Users\ryanb\Documents\Codex\AstraVideoStudio\workspace\jobs\8be1ab7719a9441ea59fe8120a0cf01f\preview.mp4`; SHA-256 `2dc833b37c1a526c247d42983f5d8d1b8b27e80f5f11a8b3436fd106fc7d3dea`. Verified **5.000 seconds, 960×540, 24 fps, 120 frames, silent H.264/yuv420p**, rendered through disposable TIFF Sequence with Alpha and fully decoded. The video source SHA matches the final AEP.

Four frames were actually viewed at **0.25, 0.75, 1.5 and 4.5 seconds**, reference `b25ccb9b3d374d8d9d767e91cf7100fa`. The reference was extracted from the isolated run's MP4; both that MP4 and the final complete-regression MP4 were hashed and are byte-identical, so the sampled observations match the final video. At 0.25s the title enters partially clipped at the left edge with motion blur; at 0.75s it is readable and nearing rest; at 1.5/4.5s it is settled, orange and readable above the cyan sentinel. The manual anchor offset remains visible. Review is `acceptable_functional_samples`, **not full playback or artistic approval**. Exact records: `workspace/sprint9-isolated-reference.json`, `workspace/sprint9-visual-review.json`.

# Stint 9.1 — compact responses and on-demand inspection

Implementation: two new typed queries, **55 tools total**, compact MCP/CLI presentation, immutable full evidence and exact structured full-mode compatibility. Native templates, services, verification, version promotion and original job journals remain unchanged. The roadmap now prioritizes 9.1 before audio and explicitly separates the remaining native-transport work as 9.2.

Final functional regression: **312 passed, 12 skipped in 23.00 seconds**. Log: workspace/stint9-1-final-tests.log. The skips are eleven opt-in native cases and Windows symlink permission. **ASTRA_RUN_AE_TESTS was not enabled. No new AE script or render was submitted.** The existing production preview-pending.json (native timeout) remains untouched; this increment does not recover that render or claim the bridge/project is currently ready.

The new coverage includes 23 focused unit cases and two integration cases. Actual stdio MCP loads all 55 schemas and exercises simulated 3/40/80-layer operations, forty additional 80-layer calls, exact full payload compatibility, job polling, filtered transforms/keys/samples and complete 80-layer pagination without duplication/loss. The fixture server substitutes only the project_create service and does not discover, launch or script AE. CLI uses the same compact/full presentation. Unit cases check complete original evidence, unchanged service data, read-only saved queries, explicitly labelled live/failure fixtures, hashes/tamper refusal, closed input schemas, oversized-item markers, Director plans/executions, hard byte budgets and concurrent immutable publication.

Measured budgets cover the serialized MCP CallToolResult with BOTH text and structured content, excluding the small JSON-RPC envelope: **8,192 bytes compact / 16,384 bytes per page**. These are not native bridge limits. Text content is compact JSON rather than a second pretty-printed scene.

## Presentation measurements (not new native acceptance)

Read-only replay of two historical matching-acknowledgement payloads through the new presentation/legacy full serialization:

| Layers | Full MCP bytes | Compact MCP bytes | Reduction |
| --- | ---: | ---: | ---: |
| 3 | 52,488 | 1,922 | 96.34% |
| 12 | 158,099 | 1,928 | 98.78% |

The original historical result files were hashed before/after and remain unchanged. Their complete content is recoverable from hash-verified evidence. Earlier dense-JSON estimates in workspace/stint9-1-real-evidence-benchmark.json are retained as a separate preliminary measurement; the table above additionally accounts for the actual legacy pretty-printed text copy.

Separate synthetic projections, with 60 keys and 25 samples per layer, measured **1,592 / 1,602 / 1,604 bytes** for **3 / 40 / 80 layers**, while complete evidence files retained **59,490 / 786,863 / 1,573,863 bytes**. These byte counts use the same wire representation checked by the actual MCP fixture integration test. They demonstrate bounded host presentation, not real native 80-layer execution or visual quality.

Machine-readable final scope, metrics, original/evidence hashes, retained pending marker and implementation/test file hashes: **workspace/stint9-1-acceptance.json**. The response cache is workspace/responses. No previous native acceptance, render or visual-review record was overwritten.

## Remaining work and usage limits

The current native acknowledgement remains limited to 2 MB; revision preflight still uses its 1.2 MB estimate. Moving complete native state into per-job artifacts with a small verified acknowledgement requires **Stint 9.2** and separate real AE acceptance. This increment does not increase those limits or bypass quarantine. Full mode is explicitly allowed to exceed the host compact budget. Very large individual page rows are marked and kept in full evidence; general nested path/vertex subdivision is not implemented. Saved queries exclude unsaved edits; explicit refresh uses the existing native protections. Evidence storage grows with distinct snapshots and is not automatically cleaned. Reload an existing MCP server after its work finishes to use the new contracts; no AE bridge restart is required by this change.

# Stint 9.2 — native evidence artifacts and small acknowledgements

The default native result protocol is now **artifact-v1**. Complete original native results are published in a fixed job-owned file with SHA-256/byte count; the deferred acknowledgement contains only identity/status/protocol and its descriptor. The host validates complete evidence before returning full data to unchanged service verification and promotion. ACK and file bounds are independent: **8 KiB and 16 MiB**, respectively. Explicit inline-v1 retains legacy limits and never acts as automatic fallback.

## Functional regression

Final standard regression: **361 passed, 13 skipped in 29.59 seconds**. Log: `workspace/stint9-2-final-tests-v2.log`. Twelve native cases were opt-in/skipped in this run, plus the Windows symlink-permission case. The twelve comprise the eleven earlier native cases and the new read-only transport case. The earlier project/edit/render acceptance suite was **not** rerun while a separate render remains pending.

New coverage includes **47 transport unit cases**, plus two additional legacy-protocol combinations in the original runner tests. It covers strict envelopes/identities/statuses, Unicode/BOM bytes, exact lengths/hashes, duplicate/non-finite JSON refusal, fixed filename/path policy, complete failed results, malformed/missing/oversized/downgraded/publication-error evidence, persistent quarantine/no-resend, legacy success/failure and revision-budget growth. Independent Python hashlib vectors check the actual ES3 function through an optional Node harness, including zero/short/million-byte input, binary chunk boundaries and 55/56/63/64/65/127/128/129-byte padding boundaries. Node is a test helper, not a product dependency.

## Real native acceptance through MCP

The targeted opt-in test **passed in 25.69 seconds**, separately from the standard suite. Log: `workspace/stint9-2-native-tests-v3.log`. It used actual AE font-inventory operations through actual stdio MCP, augmented only by a reviewed read-only test fixture. The fixture added deterministic result data and project-state observations; it did not open, save, edit or render a project.

| Operation | Native outcome | ACK bytes | Complete evidence bytes | MCP result bytes |
| --- | --- | ---: | ---: | ---: |
| `cfd28baad12b489d8956804bcf92c56b` baseline | succeeded | 227 | 1,698 | 2,052 |
| `38bb1cf4145a4333ae17f20df6eb1750` large | succeeded | 230 | 2,098,834 | 2,058 |
| `88c6a47a32db41e4b9886363c814fe5e` expected read-only failure | failed | 224 | 1,753 | 2,164 |
| `d32e0c0eb10f4761ba99e8119657fcc7` after | succeeded | 227 | 1,698 | 2,052 |

The large result exceeded the previous 2,000,000-byte acknowledgement limit. Its actual file SHA-256, independently verified by Python, is **85d0238ead1e5bad6f455dd627622c7a5fcb8e443fa7605a0da3fc1f719994ad**. Byte counts/native hashes matched for every operation, complete original data remained in journals, Unicode/newline content round-tripped correctly, and the expected native failure retained its full diagnostic without being mistaken for success. Active-project item/layer metadata, dirty state and render-queue count were equal across the probes. The approved workspace AEP's saved bytes remained unchanged.

Evidence: `workspace/stint9-2-native-acceptance-cfd28baad12b489d8956804bcf92c56b.json`, with each operation's small `result.json`, complete `native-result.json` and journal in its own job directory. Earlier native test logs and records are retained. The first fixture assertion exposed a literal non-ASCII string in the **test-generated script source**, decoded by AE with the wrong script encoding; it was corrected to a serialized ASCII-escaped JSON literal. The matching first native result/hash was already confirmed, so new tests used new job IDs rather than replaying any uncertain command. The prior successful three-probe acceptance is retained in `workspace/stint9-2-native-acceptance.json` and `workspace/stint9-2-native-tests-v2.log`.

## Default production path and preservation

After staged native acceptance, artifact-v1 became the default. A separate **unmodified production MCP** `project_query(refresh=true)` read the actual active verified project with no transport environment override or test template. Operation **bc94c31f21254d87aafdc03377031f7b** succeeded: one composition, **16,693-byte native evidence**, **1,730-byte MCP result**. Record: `workspace/stint9-2-default-inspection.json`.

The active AEP was `workspace/projects/1e50c22c5c0f44359d3392c9a7eccb21/versions/86658f49aa31473b9d19ee77973d2c84/project.aep`; its disk SHA-256 remained **0ea4c2bf599c11554eae6fd1eddb7b37021c51495663b5eb4eb9ea3c5f5e7a92**. There was no AEP mutation/snapshot/save/open or new renderer. The independent `preview-pending.json` for prior job **bb9cf0bad5c4488e99deec75356973a9** was retained byte-identically (SHA-256 **eac56a8073180b36f6401e80fb6479f93a7488196322e76d2988ad0d7965c12a**). Its render outcome was not recovered or reclassified. No interactive AE process was terminated. Matching new native reads/failure completed without leaving `ae-pending.json`.

Final audit: **workspace/stint9-2-acceptance-final.json**, with the functional/native scopes, exact descriptor hashes, production read, source preservation, retained render marker and **77 implementation/test file hashes**. The earlier point-in-time `stint9-2-acceptance.json` and preceding logs remain available. Documentation-only updates followed the final functional run.

## Limits

This proves complete native-result delivery beyond 2 MB and valid failed-result delivery in read-only operations. It is not new native 80-layer animation/render acceptance, full historical editing regression, maximum-size latency evidence, visual review or artistic approval. The file limit is 16 MiB but the existing 60-second runner deadline remains; hashing/inspection still scale with data size. Oversized or uncertain publication retains incomplete files and quarantine. Revision estimates now account for per-step state/generated tracks on the artifact channel; schemas, complete semantic checks and version/source protections remain. See `docs/native-result-transport.md`. Audio remains Sprint 10.

## Astra Asset Studio film delivery — 2026-11-08

Completed production artifacts: `workspace/deliveries/astra-asset-studio-20261108/`.
The fictional service film has native After Effects picture, 30 seconds, 1920×1080, 30 fps, 900 frames, H.264/yuv420p and original synthesized stereo AAC audio. The typed Astra workflow produced 9 compositions, 55 layers and 112 motions, with guarded finishing, masks/matte, path morphs, text animation and selective motion blur. Audio synthesis/mux is external, not an Astra audio capability.

Final native AEP SHA-256: `9f390cbb7a0f84b505864bc2bd7cab1da363fec785b10a8aaaad367c75d869fc`.
Final MP4 SHA-256: `08fc8b7d72614bc0a7dcbf73365489c756e20ac1edf2ae278e4ddb99a8019012`.
Final native render jobs: f630f05b2a2b4844952931bae6001461, a0f0b7aeed0f49fb90df91b0d5b91e13, af4585bffbac471da3d447d499f4381b. All three source hashes match the final AEP; frame count, duration and complete final decode passed.

The first render passed technical validation but actual viewed frames showed native SVG painter-order occlusion. It was rejected visually. Amendment 06 preserves existing animation/mattes while placing card backgrounds below art and importing front-first paint groups for UI/poster/mark. Original sources, first-pass AEP/renders and rejected evidence remain preserved. No raster substitute or relaxed verifier was used.

Sampled final-video frames were actually viewed and accepted within their limited scope; full playback, audio listening and human artistic approval were not performed. See `delivery-verification.json` and `paint-fix-verification.json`. Metadata/native acknowledgements, technical render evidence and sampled visual review remain separate.

The prior operator AEP and its snapshot remain byte-identical. The old timeout marker for bb9cf0bad5c4488e99deec75356973a9 was archived intact only after explicit operator authorization and a mutex-protected check found no renderer active. The old job remains a timeout; no AE process was killed or unknown job replayed. See `render-pending-resolution-audit.json`.

This task changes production artifacts and documentation only. Functional product code and test contracts were not changed; pytest was not rerun for these artifact-only changes. This delivery is not general regression acceptance or proof of every historical native workflow.


## Roadmap and external review incorporation — 2026-11-08

Documentation-only update: roadmap1.1, planned host acceptance9.3, gated EffectCraft EC-0 and conditional migration stages. The two-page Claude PDF was text-extracted and both rendered pages were viewed; claims are approximate line counts/extrapolation, not a measured current MCP regression. Source hash and limitations are in docs/claude-response-review.md.

Static source inspection confirms that current MCP registration uses response_policy and its wrapper defaults to compact, including the three tools named in the report. This does not reproduce the affected host. No live MCP/AE call, render, native job, EffectCraft build/execution, performance measurement or new functional acceptance occurred. Prior test/native evidence is retained without reclassification. Pytest was not rerun because no functional code or test contracts changed. Documentation links, source-copy hashes and planning statuses were checked separately; this is not functional regression evidence.


## Stint9.3 — local acceptance; external host pending (2026-11-08)

Final functional command: .\.venv\Scripts\python.exe -m pytest -q (TEMP/TMP directed to an owned workspace test directory). **370 passed,13 skipped in42.31s**; ASTRA_RUN_AE_TESTS was not enabled. Log:workspace/stint9-3-functional-tests-v2.log. Initial restricted execution could not create temp/IPC resources and was interrupted; the outside-restriction run exposed a containment race (first full log retained). This was diagnosed and fixed before the final complete run.

Real stdio MCP exercised layer_create/text_style_set/motion_apply with explicit native-disabled service fixtures,3/5/40/80 layers and omitted/compact/full modes:36 calls, all24 compact outputs1,885–1,901 bytes including text/structured/metadata. Full80-layer outputs approximately2.42MB were explicit only; evidence SHA/bytes, complete keys/samples/masks/styles/shapes and journals verified. Pagination covered all layers, keys/samples required explicit sections, and invalid mode created no fixture job. Runtime/schema/output defaults and per-process identity checked. Final acceptance:workspace/stint9-3-9dfac0708d3b4b2ca4c05d6c5053dfcf/acceptance.json.

The Windows prefix race was reproduced across concurrent fixture writers, then30 rounds/four writers/360 publications completed with no failure after the fix:workspace/stint9-3-concurrency-fixed-a0cbb9d926eb4678837fd0f41b1b882a/diagnostic.json. Deterministic tests preserve external drive/UNC/device rejection and existing escape checks. Symlink privilege-dependent skip remains explicit.

An unmodified production MCP subprocess performed only studio_status and synthetic operation_query calls (layers14,788bytes/transforms1,914/keys5,636/samples3,054). Three pending markers remained absent before/after. Record:workspace/stint9-3-production-readonly-0090c2656ce3456893f7a17d79cefbe9/acceptance.json. No native scripts, AEP mutation, renderer, application restart or configuration edit occurred.

Operator reports identify Claude Desktop and its current presentation_policy as9.3. This is not a raw affected-host payload measurement; its remaining query/three-route acceptance is pending. Do not mark9.3 closed or claim the review cause fixed. See docs/host-response-acceptance.md. Earlier9.1/9.2 evidence, production samples and render outcomes remain unchanged.


### External query confirmation — operator report (2026-11-08)

Claude Desktop operation_query returned succeeded/layers, total80, offset0, limit3, three rows, next_offset3 and zero oversized omissions; no full transforms/keys/samples arrays. This matches the requested synthetic page semantics. Evidence:workspace/stint9-3-claude-query-confirmation.json. No affected-host wire-byte measurement/raw capture was supplied. Three editing routes remain pending there. No code changed and pytest was not rerun for this documentary follow-up; previous370 passed/13 skipped result remains historical evidence for the unchanged implementation.


## Sprint10 — audio and synchronization acceptance (2026-11-08)

Functional regression: **384 passed,14 skipped in50.17s**. Command:.\.venv\Scripts\python.exe -m pytest -q, with TEMP/TMP in owned workspace; ASTRA_RUN_AE_TESTS unset. Final log:workspace/sprint10-functional-tests-v2.log. Initial383/14 run retained in sprint10-functional-tests.log; a final negative integration case added loud-mix and owned-PCM-tamper refusal. Default tests remain non-native.

Actual MCP/FFmpeg fixture acceptance:workspace/sprint10-offline-17e447f88aaa4b4d9037463fa65ebc6c/acceptance.json. Five audio tools, compact results, explicit audio queries, guarded audio-preview rejection before native job, immutable states, trim/gain/fades, manual/uncertain energy cues and sync plans were exercised.20s/320×180/24fps synthetic picture/bed/two SFX;480frames, complete decode, decoded pixel checks around flash frames and cue errors<=1frame. AEP metadata here is explicitly fake: this is not AE execution. AEP conflicts, invalid fades/ranges/nonfinite inputs, duplicate markers, preserved non-target clips, source/evidence tampering and no clipping are covered by units/integration.

Separate targeted real AE run: **1 passed in66.75s**. Only tests/integration/test_audio_ae_live.py was run with ASTRA_RUN_AE_TESTS=1, sequentially after default tests. Operator manually restored the known idle bootstrap; no automatic -r repeat. File:workspace/sprint10-native-tests.log.

Native acceptance:workspace/sprint10-native-4367a34cc06c4190a10346d9cde94b87/acceptance.json. New project b4f850dfb37e4793bb7c017ff4323aec; final source versions/9f5a59a3c913403598b76de58afa2dbe/project.aep, SHA2566c5723f9cd4501d3fe4bbd2685d1685834dcca10efdbef5a42a751b3916b9696. Matching native acknowledgements for create/motion/preparation and native TIFF/PNG picture render followed by FFmpeg mux. Job5ad82bbf321e4791af39b62a12b620e4 produced20s/640×360/24fps/480frames H.264yuv420p plus AAC48kHz/stereo. Audio state aaf984dffdcdc9ac87b73ba3a6516334a8ef4b4b4009fb21ad81924bc8588b15, bed/two SFX/fades.

Cue detection in final decoded audio measured0frame error against native saved opacity keys3s/10s. Encoded audio20.0s/start delta0; decoded AAC20.010667s (512samples padding, within1frame), peak-15.105dBFS. PCM mix960,000samples/20s, peak-15.481dBFS. Full A/V decode passed; generic stream verification still labels event_sync_measured=false, with this fixture-specific cue measurement recorded separately.

All1,138 preexisting managed AEPs in the native test baseline retained hashes; final source retained its hash through preview. New test AEP remains open. No source original replaced, application killed, uncertain script resent or quarantine cleared. No native/result transport template changed. Existing sidecar/asset outputs remain retained.

Three matching-video samples were actually viewed at0/10/19.9375s: dark beginning, centered AUDIO SYNC at mid-point, dark end. Additional immutable sampled review:workspace/sprint10-native-4367a34cc06c4190a10346d9cde94b87/sampled-visual-review.json. No full human playback, human listening, artistic approval or general1080p/final package acceptance. This native test does not close9.3 external Claude acceptance. See docs/audio-tools.md. Sprint11 remains next; EffectCraft deferred by operator.


## Sprint11 — final render/package native acceptance (2026-11-08)

Default regression before native:411 passed/15 skipped (sprint11-functional-tests-v4.log,55.67s), after synthetic MCP/FFmpeg color/alpha and collection guards. Native targeted run: **1 passed in125.47s**, only tests/integration/test_delivery_ae_live.py with ASTRA_RUN_AE_TESTS=1, sequentially after default/mutex tests. Log:workspace/sprint11-native-tests-v3.log. Known earlier failures remain in sprint11-native-tests.log and -v2.log; native-result evidence shows matching failed/succeeded acknowledgements, not uncertain execution. The second attempt's completed distribution output remains preserved.

Native record:workspace/sprint11-native-424560b9381d4a9d8c89fb81fafb3885/acceptance.json. Source project d3da919d503d4f3b8c7f16901d1a2cb1, version49cc04d25ca04a80a9e9fd00f482a4b0, SHA4a9679fdf5f1d9459d011fd2d94b20f3f4f433e8724696f633c959d94bb7ebe7. Distribution job cba7f19bc5654cc2a8ad1b5cdad1240a:30s/1920×1080/24fps/720frames, H.264yuv420p, range tv/matrix+primaries bt709/transfer iec61966-2-1. MP4 SHAac91f42976b80ed493e8f5df385472a762bff042f37446d7fdee1b8622b88435. AAC48k/stereo30s, stream-start delta0; PCM decoded30.016s padding within1frame, peak-15.105dBFS. Cue errors measured0frames at3s/20s against saved native keys. Full A/V decode passed.

Intermediate job b87914e749e140d5a3e6ea60875d7121: six native1080p TIFF frames over0.25s at3s, pix_fmt rgba/8bit, output module RGB+Alpha/Millions of Colors+/Premultiplied (Matted). Source TIFF bytes were preserved by per-file hashes, no resampling/unpremultiply. Complete alpha decode matched expected pixel/frame count, min0/max255; transparent pixels were exercised, not inferred from a preset name.

Collection delivery d2f25eeeeb034a7c8acfc462bcb14c3e: nine manifest files plus manifest; collected AEP saved/reopened and PNG source relinked inside package, all inspected comp/layer/interpretation state preserved. Fonts Arial-BoldMT available/not copied; ADBE Fill listed native. Native inspect5d05b2d16ceb4e92a2d5c9637513761b, collect613bab7cfaec45a48e17267a7c4652d4, validate b284d3a2246d4ea3885f2eaaaf3f3d86. Manifest SHAc8feb73a03bf7cb135b6a579e1a69f14e4686cc65701d45d81cb0c021d01643d. Validator checked exact file membership/hash, fonts/links/native reopen, full A/V decode, and bit-identical audio reconstruction from packaged original/PCM/recipe.1,150 preexisting managed AEPs remained unchanged; new test source left open. No pending marker cleared or AE terminated.

Three matching-video samples were viewed at0/15/29.9375s: media square remains on dark background, title FINAL DELIVERY visible/readable/centered at midpoint, nearly invisible at exit. Immutable review:workspace/sprint11-native-424560b9381d4a9d8c89fb81fafb3885/sampled-visual-review.json. No full human playback, listening or artistic approval. No general HDR/wide-gamut/other-codec/cross-machine-relink acceptance.9.3 Claude editing-route acceptance is not closed by this sprint.

After native acceptance, metadata guards were tightened for optional TIFF-sidecar WAV copy hashes and package-native refusal under retained render quarantine; the existing picture/codec/native templates were unchanged. A final default regression and separate read-only package validation are recorded in the final audit. No second long native render is implied by that read-only check. See docs/final-delivery.md for scope and contracts.


### Sprint11 final-code closure

Final command:.\.venv\Scripts\python.exe -m pytest -q, default native flag unset: **412 passed,15 skipped in57.51s**, workspace/sprint11-functional-tests-v5.log. Added the explicit render-quarantine guard and optional TIFF WAV hash verification; final real-MCP/FFmpeg fixture covers H.264/AAC plus TIFF both silent and with WAV:workspace/sprint11-fixtures-9c88be151da0437c8b37d1f2bef55c51/acceptance.json. Native provider is explicitly fake only in that fixture process.

Unmodified production MCP on final code performed read-only delivery_validate for d2f25eeeeb034a7c8acfc462bcb14c3e: native cf194629a54640a68c3821c7c699f8cc acknowledged, all package/source hashes unchanged, full A/V decode and bit-identical PCM rebuild passed. Record:workspace/sprint11-readonly-validation-76e5ab86a71441a888e85f4c00640fc3/acceptance.json. No new render, app restart, unknown replay or pending-marker deletion. Source hashes/final files/schema and scopes are registered in workspace/sprint11-acceptance-final.json; doc-only follow-up is not another functional run.


### Sprint12 - storyboard V2 technical acceptance (2026-11-09)

Seven new MCP tools,72 total. Final default regression command:.\.venv\Scripts\python.exe -m pytest -q, native flag unset: **434 passed,16 skipped in61.62s** (workspace/sprint12-functional-tests-final.log). Unit coverage includes immutable plans/dependency changes, reading/contrast, complete Portuguese grammar, root-wide attempt slots, actual exit-phase sampling, midpoint scale/rotation/parent/expression guards, frame evidence integrity and bounded paginated scenes. Real stdio+FFmpeg planning fixture sends no AE scripts. Existing native/mutex tests were not run concurrently.

Targeted opt-in only:tests/integration/test_storyboard_ae_live.py, **1 passed in149.84s** (workspace/sprint12-native-tests-v2.log). New18s1280x720/24fps/432-frame piece, three precompositions plus master, hero/split/editorial, slide/reveal/scale/fade techniques, installed Arial-BoldMT, native editable text/shapes, post-production synthetic test tone. Each original/revision movie passed frame/duration/codec checks and full A/V decode. Two complete Portuguese patches changed scene1 title and scene2 body. A separately tool-saved accent-position edit remained unchanged across both patches; this is compatible saved-edit evidence, not a new human manual-action claim. Earlier Sprint9 manual acceptance remains distinct. Budget2 rejected the third revision before native work.

Native attempt directory:workspace/sprint12-native-414fbe4ed3a04f8ebb65f568fff070d1. Preservation baseline/result:all1,157 preexisting managed AEP hashes unchanged. Final execution3525476042304779949da8a9f2f4329b, AEP SHA87c080931d78417501e1fe2e90908ef9209da7df4d70abcbb5b36270f96b5da3. Final movie:workspace/storyboards/renders/3525476042304779949da8a9f2f4329b/final.mp4. Source and original/revision AEPs/renders/audio states remain separate. No unknown native replay, pending-marker deletion, AE kill, automatic external import root or arbitrary script tool.

The first native attempt (workspace/sprint12-native-e2eb7f7ddf27460c9cca061dacc22a83;56.95s) successfully created/rendered and then stopped at an invalid layer_transform argument in the test, before that edit executed. Its outputs were retained and1,155 earlier AEPs preserved. After correcting the test and left-aligned layout, the complete second attempt used new plan/project IDs. No timeout or uncertain job was retried.

Final-code follow-up:midpoint geometry now evaluates native samples with scale/rotation, and exit samples fall inside fades. The unchanged final AEP was inspected read-only through production MCP (native operation1e6cfda7ac3e415a9f061af198d7c4e8), compared to saved metadata, all three AEP versions passed final geometry checks, and all three existing videos were resampled without new native rendering. Record:workspace/sprint12-final-verification-4e5a51ab02f04f85a3fee38dc9c770af/acceptance.json. All1,162 managed AEPs in that follow-up remained unchanged.

Actual viewing:initial scene1 hold; revision1 scene1/2 holds; final entry frame12, holds78/222/360, transitions150/294 and exit426. Holds show revised Portuguese text without clipping, consistent contrast/hierarchy and distinct left/center/split layouts. Transition frames show simultaneous titles during crossfade; this was recorded as a minor continuity/artistic issue, not silently approved. Five append-only production-MCP reviews include two retrospective text-issue/reverification pairs and a final needs_revision frame review. These reviews were recorded after the preplanned test patches; they are not evidence of an autonomous artistic decision loop. See recorded-reviews.json in the final-verification directory.

Full human playback/listening and artistic approval remain pending. The test tone is not a professional music deliverable. Automated visual asset generation here is native text/shapes; existing image/vector tools are separate. General semantic brand compliance/reference interpretation remains caller/human work. EffectCraft remains deferred; Claude Desktop9.3 external editing-route acceptance remains pending. Frozen sources/logs/scopes:workspace/sprint12-acceptance-final.json.

Final compact follow-up on the final source:72 tools, completed storyboard status exposes video path/SHA in5,708 protocol bytes including text/structured/meta. Issues page returned the recorded continuity issue. Record:workspace/sprint12-final-verification-4e5a51ab02f04f85a3fee38dc9c770af/compact-final-code.json. This last presentation change sent no AE scripts; the native builder/templates remain the accepted versions.


### Sprint13 - persistent queue and constrained recovery (2026-11-09)

Final default command:.\.venv\Scripts\python.exe -m pytest -q, native flag unset: **462 passed,18 skipped in93.56s**, workspace/sprint13-functional-tests-closure.log.76 MCP tools. Coverage includes process creation identity/PID reuse, exclusive four-slot admission, one-shot worker start, dead-owner never-started release, terminal-slot hash guards, late/corrupt native evidence, read-only versus mutation quarantine release, post-ack heartbeat, cancellation by stage, missing media/fonts/unverified plugins, retained journals/outputs, hardlink/snapshot cleanup protection and public stdio input/output/compact paging. Existing missing-AE, native render-error and insufficient-disk tests remain included.

Six real-MCP interruption/diagnostic cases use controlled Python hosts and explicitly synthetic backend acknowledgements/outputs, never Adobe. Kill only the fixture host, restart MCP, and preserve its journal. A queued owner can release only proven unstarted work; build/read intent with late ack remains unpromoted, native-render and encode interruptions retain uncertain/partial state. Four independent live hosts fill four durable slots and reject the fifth. These fixture cases do not certify native build/render interruption or engine shutdown. The direct base interpreter avoids the Windows venv redirector PID mismatch encountered in an earlier test fixture; exited fixture owners were checked by OS process identity.

Targeted native acceptance only:tests/integration/test_recovery_ae_live.py main case **1 passed in72.93s**, workspace/sprint13-native-tests.log. New3s640x360/24fps AEP, imported owned PNG, acknowledged live font/media/plugin report, temporary relocation of only the owned test media/restoration with hash verification, a fully decoded1s/24-frame H.264 preview using durable worker claims, and cancellation requested while aerender PID3652 was observed alive. Native cancellation waited for confirmed exit; the interactive AE was never terminated. Cancelled outputs/copy/logs remain. Queue claims were released and all1,162 preexisting managed AEP hashes remained unchanged. Native directory:workspace/sprint13-native-f9ea4c10d3924fb79114fe1f8a073020.

Source left open:workspace/projects/6d6cf1c81f694f38b2370349ed9ec015/versions/361f071dbd80481eb4db2b398177c4d7/project.aep, SHA2f61eeda2d35295759924094145d1101047769c9683ed1c915fe06fbd1371111. Verified preview job17000f1d40374a9a9d3da177fc0df108, MP4 SHAda8ae1fdba2615c30769d707c79af19b92ed89de0c901be1ffafe958ebe80e93. No new artistic/sample-viewing claim; recovery technical acceptance only.

Real read-host interruption: **1 passed in11.58s**, workspace/sprint13-native-read-recovery-tests-v2.log. A controlled Python host submitted an actual read, paused after publishing, and was killed only after complete matching native evidence and a later idle heartbeat. New MCP inspected the dead-owner journal, archived exact marker bytes and explicitly released this read quarantine; a subsequent guarded native dependency read succeeded. Original interrupted journal SHA remained unchanged; no service/AEP result was promoted and no native mutation was replayed. Record:workspace/sprint13-native-read-recovery-35266ad599864a228e519623d0be59d8/acceptance.json. All1,164 managed AEPs remained unchanged.

The first read-interruption test saw result.json between truncate/write/close and stopped before parsing completed. Its pending marker was retained. The eventual strict matching read result was recovered through the production MCP without resending the job (workspace/sprint13-partial-ack-recovery-604cc2e4a98f4da7befb237c2cae4971.json). The acceptance wait and release guard now require complete validated evidence and a heartbeat after acknowledgement publication. No uncertain job was blindly retried and no renderer marker was removed.

Final-code production MCP verification:workspace/sprint13-final-verification-5134dcb16d124b0999b1893f97638fde/acceptance.json. Four new tools stayed within8KiB including text/structured/meta; a recovered native layer page returned RECOVERY without full transforms/keys/samples. Queue had zero outstanding claims and ready bridge; cleanup performed no deletion. The known read job remains blocked/unpromoted in the full status recovery view. A final-code live dependency read (native6a0fbbcc78644f3db8702cd155622fb0) completed before a verification helper incorrectly expected an extra recovery field in compact status; its completed journal was retained, not replayed. The corrected verifier reads that detail in full mode and reuses the recorded live result. No new native render was needed. All1,164 AEPs stayed unchanged.

Legacy ownerless jobs remain unknown. Started uncertain mutations/renders are not resumed or promoted. No automatic AE kill, repeated known-session bootstrap, external root addition, font/plugin install, relink or cleanup-apply tool. Full human playback/listening/artistic approval and Sprint12 crossfade follow-up remain open; Claude Desktop9.3 editing-route acceptance is not closed, and EffectCraft stays deferred. Frozen sources/scopes/log hashes:workspace/sprint13-acceptance-final.json.

## Final reference base - in progress (2026-11-09)

Default regression before native acceptance:462 passed/18 skipped in95.90s, workspace/final-acceptance-regression.log. New VÉRTICE24s1920x1080/30fps base built through70 sequential public MCP calls:five compositions/29 layers, native SVG paths, Trim, word animator, explicit spatial Bezier keys, alpha matte and controlled motion blur. All calls acknowledged and saved/reopened by their services. Font/dependency report has no issues; text inspection has no overflow/substituted fonts. All1,164 earlier managed AEPs and67 new build versions kept hashes. Base record:workspace/final-acceptance-df109fb5616b4c45a5e85c34b9169ba6/base-acceptance.json.

Current gate:operator must change only the unsaved X position of Assinatura editorial in scene04 before capture. No human manual edit, Portuguese patches, movie decode, sample viewing, listening, landscape approval or vertical version is claimed yet. Original synthesized24s48kHz stereo score/SFX passed local PCM analysis; this is not artistic listening. Original AEP work was preserved; no pending marker removed or app killed.

### VÉRTICE landscape technical acceptance

Operator reported Ajustei sem salvar; native read confirmed only the requested static X960->980 change in scene04. project_save captured it to a new AEP; both Portuguese content patches preserved the complete manual layer and every retained source hash. Final24s/1920x1080/30fps/720-frame H.264/AAC passed full decode, source/hash guards and all15 text midpoint safe-area/overflow checks. Decoded SFX correlation measured0-frame offsets on an8-sample grid at0.4/6.4/13.4/19.4s, fixed minimum correlation0.5; no true-peak/LUFS or listening claim. Sixteen matching-video frames were actually viewed; scene transitions pass through the common background without overlapping titles in the samples. Native delivery collection/reopen/validation passed, including audio reconstruction. Preserved1,164 preexisting managed AEPs and70 build/capture/revision versions. Report:workspace/final-acceptance-df109fb5616b4c45a5e85c34b9169ba6/landscape-acceptance.json. Human playback/listening/landscape approval pending; portrait not started.

### 2026-11-10 — creation optimization

Final default regression: **480 passed /19 skipped,94.23s**, with native opt-in disabled. Log:workspace/optimization-functional-final-tests.log. Added coverage for receipt envelopes including Unicode diagnostics/metadata, exact full compatibility, verified local evidence/tampering/identity, terminal polling, batch bounds/roles/closed scope/hash preflight, failed non-target/stacking/animation verification preventing promotion, and real stdio receipt resolution/schema. Existing compact/full/native transport checks remain intact. Tool count77.

Targeted native grouped-creation comparison: **1 passed,76.07s** initially; **1 passed,61.55s** with final transaction-wide mutex. No default integration flag was enabled. Three texts and two shapes: initial8 mutation calls/37.387s versus1/4.691s; final8/37.316s versus1/4.946s. Exact inspected visual metadata (identity excluded) and sentinels matched. Source/snapshot/non-target/native reopen checks passed. Initial baseline1,234 managed AEPs and final baseline1,245 preserved by SHA. Final report:workspace/optimization-acceptance/0f1f63b3b1ea4982b029c085ba652aec/acceptance.json; log:workspace/optimization-native-final-tests.log. Two runs are not a statistically established speed distribution or an end-to-end film benchmark.

Additional public-MCP native render/error check on initial fixtures: two0.2s/30fps/six-frame H.264320×180 previews, full decode and identical first decoded PNG SHA c80c79ca89801febfb503f8c8dd1f2c343888af5197761f97247399a1d23f438. The grouped PNG was actually viewed; this is a static equivalence fixture, not layout/animation/artistic acceptance of VÉRTICE. Missing-font and tiny-box overflow were acknowledged failures, retained failed evidence, left the parent current source unchanged and released no uncertain work. Preserved1,245 then-managed AEPs. See workspace/optimization-acceptance/25e88d556ac548ad8be80286de138932/render-check.json. Neither quarantine marker remained after completion.

Audit reconstructed70 historical build result envelopes:full14,662,657B /compact243,558B /receipt104,126B. This is not historical raw protocol capture and excludes requests/tool schemas/framing. Updated build recipe has37 calls by static count, not a new executed/accepted film. Existing VÉRTICE AEP/plan/audio/render/package were preserved. SFX/easing recommendations were documented; artistic changes, new film render/listening/landscape approval/portrait remain pending. EffectCraft and external Claude9.3 acceptance unchanged. See docs/creation-optimization.md and workspace/optimization-closure.json.

### 2026-11-10 — EC-0 first milestone, not final EC-0 acceptance

Default regression after adding the isolated harness: **486 passed /19 skipped,93.31s**; log workspace/ec0/evidence/astra-regression.log. Native AE opt-in stayed disabled. New Python checks cover bounded/strict receipt decoding, duplicate/non-finite/ambiguous values, matching job/revision/status/required verification and reachable versus unused GUI graph edges. Production MCP tools remain77.

Private Rust1.95.0/x86_64-pc-windows-msvc toolchain installed with verified official Rustup1.28.2 installer. Minimal core build passed in1m33s initially; final helper build/test passed with2 Rust unit tests (job-name/path refusal and exact project roundtrip without repair). Dedicated Cargo.lock pins upstream a41ff5015c6687db15a6f074a47b870b8f09fece; target-filtered graph87 reachable packages, no identified GUI frontends. No upstream CLI/GUI/engine-host command surface was exposed and no AE script was sent.

Final smoke:workspace/ec0/smoke-e19230ba7faa40f7a97a656bafc7a435/verification.json. Fixed opaque solids,160×90/30fps/0.2s/six frames. Three1/2/1-thread CPU runs saved/reopened identical ecproj state and produced identical PNG hashes, with reference center/corner pixels checked. H.264/yuv420p encode, FFprobe frame/FPS/duration checks and full decode passed.2,439 prior AEP/snapshot files under workspace/projects retained hashes. A separate negative check refused a known completed slot and two invalid IDs without modifying its files:workspace/ec0/evidence/refusal-99d36a48a92940a29e868318ba19018f.json. No timeout occurred; timeout recovery itself was not tested or accepted as production recovery.

Summary/inventory are versioned in docs/effectcraft/ec0-first-milestone.json and ec0-dependency-inventory.json. Local job artifacts remain outside Git. These results do not approve text/fonts, curves, effects, alpha, AEP import/export, AE parity, GPU/native encoder, stress, memory/performance gates or complete license/notices/SBOM closure. EC-0 stays in progress; see docs/effectcraft/ec0-progress.md. No new human playback/listening/artistic approval or Claude9.3 closure is claimed.

### 2026-11-10 — EC-0 second milestone: fixed text and manual curves

Final Astra regression: **499 passed /19 skipped,94.39s** (workspace/ec0/evidence/text-curves-astra-regression.log). Native AE tests stayed disabled. Added tests for closed-form scalar/boundary values, arc symmetry/nonzero passage reference, strict finite typed samples, missing data/raster refusal and bounded/strict font-case receipts. Final Rust tests: **4 passed**, including2 new checks for exact-font/hash/glyph rejection, Unicode style ranges and roundtrip/manual flags (text-curves-rust-tests-03.log). Initial Rust layout failures remain in text-curves-rust-tests.log and -02.log; Inter ink extended0.563156px above its box, corrected through the declared baseline-2px amendment, not by relaxing the overflow gate.

Final run:workspace/ec0/text-curves-03f19e0df7eb4464a925da6e041fd602/verification.json. Three positive1/2/1-thread sequences of61frames640×360/30fps matched PNG hashes; three negative font cases failed with matching status/job/case, no system scan and no output slot. Text uses exact Inter-Regular hash40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82; native shaping glyph IDs/faces were checked; no fonts were installed system-wide or added as binary files to this repository (the private executable uses upstream embedded OFL bytes). Point/box layouts and a four-code-point color range roundtripped; both text raster bounds errors were1px. That geometry/raster comparison is internal to EC, not an AE comparison.

Independent oracle results: scalar maximum absolute error2.842170943040401e-14; spatial maximum2.6912235943070386e-7px;63samples including before/after key interval,9start/stretch and16frame/tick checks. Interior180px/s finite probes had maximum velocity error0.03574741416914963px/s and difference0.004321609310409258px/s, below the predeclared0.2 gate. No automatic/continuous/roving edits or general continuity claim. H.264/FFprobe61frames/30fps/duration/full decode passed;2,439 AEP/snapshot files preserved without AE commands. V1 solids smoke revalidated in smoke-821783bf43c34b9ab2374fccae414df6 with full decode and preserved prior files. Current Windows graph95 reachable packages, no identified GUI frontends; the old87-package report remains historical.

Three matching MP4 frames0/30/60 of first successful run1e19b5bea136423e825977fc04e27d74 were extracted and actually viewed: text legible without apparent clipping/collision in samples, and moving-solid positions differed. No full playback, listening, artistic approval or AE parity was performed. Review and hashes are retained in that run's sampled-review/review.json. Versioned summary/inventory:docs/effectcraft/ec0-text-curves-milestone.json and ec0-text-curves-dependency-inventory.json; seven embedded OFL assets are listed in experimental/ec0/font-assets-manifest.json. Full dependency/notices/SBOM clearance remains pending. Text animators/general fonts, effects/paths/mattes/dependencies, AEP corpus, AE parity, stress/performance/GPU/adoption are not approved by this milestone. EC-0 stays in progress; production77-tool API/backend unchanged.

### 2026-11-10 — EC-0 third milestone

Astra regression passed with 499 tests and 19 skips in 102.90s. Four Rust unit tests passed across the earlier probes. The compositing integration ran separately with `run_compositing.py`. All three runs produced identical project and PNG hashes for 12 images per run. Pixel checks covered Fill, Gaussian Blur, native path paint order, Trim Paths, morph at frames 0, 15 and 30, Add/Subtract masks, alpha and luma mattes, and nested parenting. Seven graph cases were refused in preflight. The 2,439 existing AEPs and snapshots matched their baseline hashes. See `docs/effectcraft/ec0-compositing-milestone.json` for the complete measured samples and evidence pointer. The SVG import and AE comparison gates remain pending.

### EC-0 fourth milestone

The Astra SVG subset produced three native EffectCraft paths. Reopen checks matched vertices, tangents and paint parameters. A single fill edit in a separate project changed exactly 4,032 target pixels. The JetBrainsMono-Regular fixture matched the pinned PostScript name and SHA-256. Its character selector revealed zero, one and two glyphs at frames 0, 15 and 30, and the second glyph's alpha was identical at frames 15 and 30. Each fixture matched project and PNG hashes across three CPU runs. The compositing and text-curve probes passed again. The latest of those runs checked 2,448 AEP and snapshot hashes. See `docs/effectcraft/ec0-svg-selector-milestone.json` for individual run counts and evidence.

Four Rust unit tests passed. The full Python run recorded 498 passes, 19 skips and one failure in `test_mutex_blocks_other_thread`. The test and its direct retry could not acquire the production mutex at entry while the workspace recorded active AE jobs. The same test passed when only its mutex name was redirected to a temporary Windows name in the test process. The shared-name test remains unverified in this run. Logs are under `workspace/ec0/evidence/svg-selector-*-regression.log`, `svg-selector-mutex-rerun.log` and `svg-selector-isolated-mutex.log`.

### EC-0 fifth milestone

The offline integration used the retained Sprint 11 AE 25.5 inspection and verified native TIFFs at composition frames 72, 75 and 77. Both graphic ROIs scored SSIM 1 with RGB MAE 0 and alpha maximum error 0. Six scalar opacity keys and five samples passed the declared tolerance. The comparison excluded title pixels. The probe preserved all 2,498 preexisting managed AEP and snapshot hashes without submitting AE commands.

The corpus probe verified 20 locked hashes, analyzed all 17 AEP/AEPX projects and exercised strict import in scratch memory. Fifteen imports succeeded and two refused with the scratch project unchanged. The three FFX fixtures were hash-checked only. The upstream suite with mandatory corpus was outside this run. Four Rust tests passed and the Windows dependency inventory found 96 reachable packages and no identified GUI frontend. See `docs/effectcraft/ec0-parity-milestone.json` and `workspace/ec0/parity-5ff6a64b30a644b0935fd77f25ba1b43`.

The comparator accepted identical pixels and irrelevant RGB under zero alpha. It rejected a wrong visible color and a missing opaque pixel. The full Python regression completed with 499 passes and 19 skips in 101.17 s using a workspace pytest temp directory and host subprocess access. Native AE tests remained disabled.

### 2026-11-11 — EC-0 sixth milestone

The unmodified upstream AEP integration target ran with the isolated probe dependency graph, pinned corpus and `EFFECTCRAFT_AEP_FIXTURES_REQUIRED=1`. It passed 602 tests, failed zero and ignored five in 168.21 s. All 101 archived upstream test/fixture files, 20 locked corpus files and 2,498 preexisting managed AEPs retained their hashes. No mandatory fixture was skipped. The five ignored cases cover two exploratory AEP/AEPX checks, two version-family checks and an unpinned Cryptomatte fixture. Library unit and example targets remain pending.

The controller initially expected four ignored cases. Its successful child exit and raw outputs were preserved, then audited against the pinned source and corrected parser. The post-exit inspection finalized that same run without resubmission. The report binds both the raw output and inspection hashes. See `docs/effectcraft/ec0-aep-suite-milestone.json` and `workspace/ec0/aep-suite-cfeac096f37f4589a1181cfc965c7696`.

The final Python regression passed 499 tests with 19 skips in 101.72 s. Native AE tests remained disabled.

### 2026-11-11 — EC-0 seventh milestone

The fixed release worker passed sampled 1080p CPU stress for 3/40/80 root layers plus three nested layers. Each scene had five fresh-process two-thread runs and ten warm runs after an excluded warmup. The repeated sample consists of frames 0/225/450/675/899. The 80-layer case additionally matched hashes across a 1/2/1-thread series and a complete 900-frame sequence. Warm and fresh sample hashes matched for every scene, and the fixture exercised visible motion.

The full sequence used 18.604 s of renderer calls, 36.444 s of RGBA conversion/hash and 2.809 s of PNG writes. Native process wall time was 59.646 s. The maximum native-worker PeakWorkingSetSize was 77,352,960 bytes, with successful post-exit queries and a 4 GiB fixed ceiling. The monitor passed a known-allocation check against the real Python interpreter. An initial venv-launcher-only check was excluded and retained with its inspection record.

All 900 PNGs decoded to the expected RGBA hashes. H.264 encoding took 4.957 s, and FFprobe confirmed 1920×1080, 30 fps, 900 frames and 30 seconds. Full video decode passed. The 2,526 prior managed AEP and snapshot hashes were preserved. There were no AE commands or human playback/artistic approval. See `docs/effectcraft/ec0-stress-milestone.json` and `workspace/ec0/stress-bcaddadb9ec1468fa31ed49298a6765e`.

Python regression passed 499 tests with 19 skips in 103.46 s. Four Rust unit tests passed and the experimental stress integration completed. The first release build attempt had an argument-splatting failure, followed by a build that found two layer-container type mismatches. Both were corrected before measurements, and the final release build passed. Logs remain under `workspace/ec0/evidence/stress-*`.

These measurements cover the solids/precomp fixture and sampled repetitions. Full-sequence repeat distributions, matched AE performance, text/effect-heavy stress, VRAM and complete license/notices acceptance remain pending.

### 2026-11-12 — EC-0 eighth milestone

The audit produced a schema-validated CycloneDX 1.6 BOM for 96 resolved Cargo packages and seven embedded fonts. Dependency references and component identities passed semantic checks. Registry archives matched Cargo.lock, and source files matched their verified archive bytes. Git package files and inherited notices matched pinned commits, with CRLF/LF equivalence recorded for text. The audit recorded 4,166 per-package file checks and retained 104 distinct text candidates. Shared repository notices count in each applicable package's checks.

The font inventory matched the seven include_bytes declarations, exact font bytes, OFL license hashes, attribution hashes and Git objects. All declared license identifiers had matching text markers. Both COPYRIGHT files found during the final scan, in euclid and unicode-bidi, are included. A modified source, wrong archive checksum, dangling BOM reference and invented SPDX ID were refused in independent negative probes.

The initial run failed on a font path resolved relative to the crate. The corrected run resolved fonts from the pinned repository root. A subsequent scan added the two COPYRIGHT files and generated a fresh final audit. All earlier evidence remains. The 2,578 prior managed AEP and snapshot hashes were preserved. No native AE work was dispatched.

Final evidence is under `workspace/ec0/license-audit-cec6c264c6854a789a4801f3e91a40af`. Versioned files are `docs/effectcraft/ec0-bom.cdx.json`, `ec0-third-party-notices.txt` and `ec0-license-milestone.json`. Marker coverage and schema validation leave distribution obligations, embedded-data/source-level review, trademarks, linked-binary attestation and full external encoder closure pending.

Final Python regression passed 499 tests with 19 skips in 95.57 s. The three generated export files use explicit LF checkout rules so their recorded byte hashes survive Windows Git newline conversion.

### 2026-11-12 — EC-0 ninth milestone

Two pinned archived AEPs were strictly imported offline with no reported losses, missing footage or missing fonts. Current ArialMT and Arial-BoldMT bytes matched configured SHA/PostScript identities. Text resolution and coverage checks passed and the worker did not scan system fonts. Historical font bytes remain unattested.

The design case passed 70 static transform checks. The animation case passed 304 checks covering 16 native transform keys and 20 samples, including applicable Bezier controls and temporal/spatial flags. Eight imported keys on the design card's other groups were outside that semantic comparison.

Three design and four animation frames were compared against hash-verified H.264 previews. A separate one-frame codec control retained the original diagnostics. Four moving-title regions passed the fixed numeric SSIM/MAE limits. The twelve design regions and four sentinel regions remained outliers. Their bounds are measured in preview pixels. All 16 outlier regions in the codec control were inspected through five actually viewed contact sheets. No lossless parity, historical font identity, full playback or artistic approval is inferred.

Evidence is under `workspace/ec0/visual-diagnostic-68893060beb44e79a7da49341113acd0`. The original summary, codec-control summary, sampled-review record and images retain separate hashes. The diagnostic preserved 2,598 preexisting managed AEP/snapshot hashes. Four Rust tests passed. The previous TIFF/corpus probe was rerun with the modified worker. See `docs/effectcraft/ec0-visual-diagnostic-milestone.json`.

Final Python regression passed 499 tests with 19 skips in 99.24 s. The TIFF/corpus compatibility run passed in `workspace/ec0/parity-cc5b7ac1ef0e4736a3e9fc36f39a60e8`. Initial build errors in the new mode were corrected to use the unit Text source with its property document, Project::item and the PNG encoder's actual return type before execution.

### 2026-11-12 — Lossless-reference preparation

The protected capture and native-resolution TIFF comparison controllers are implemented. The source/font copies and frozen plan were prepared in `workspace/ec0/lossless-40f58a46e5554ea9a67ae436cbc6a37e`. New native TIFF collection and active-project restoration have not run. Recent operations from another client prompted a request to coordinate exclusive AE use.

Read-only font queries succeeded with matching native acknowledgements. Operation ff05d655a15b4c84b25ece1afba205aa returned actual Arial locations. Operation c80955d3eeb046139b41f7ae8d151488 returned the explicitly requested active saved path and a false dirty flag. Operation b9af7dcc909848618b09120cc98d4cde confirmed that the default query omits project context. Evidence is retained under `workspace/ec0/evidence/lossless-*-query-*.json`.

The RGB/alpha comparator passed independent known partial-alpha values and refused a two-byte alpha error and an incorrect transparent matte. It also passed the archived native mark/edge ROI with SSIM 1, RGB MAE 0, alpha maximum error 0 and equal bounds. Native TIFF bytes were preserved. That check is retained in `workspace/ec0/evidence/lossless-comparator-legacy.json`.

The updated worker compiled and four Rust tests passed. Python regression passed 499 tests with 19 skips in 95.50 s. The full offline design/animation diagnostic was rerun with separate RGBA outputs in `workspace/ec0/visual-diagnostic-e9ec1c37cd6c48749aca0eaf9c790e1b`. The new native capture/restore workflow remains unverified.

Final font metadata flags are independently opt-in. Operation b31ccc11403548518e36c431218907b8 returned locations and project context when requested. Operation 10e151dc7365445fbc3048f84004628b omitted both from the default response. The final Python regression passed 499 tests with 19 skips in 95.03 s. A synthetic preflight accepted a matching acknowledged bootstrap and refused an unresolved native submission without dispatch. Preparation evidence is versioned in `docs/effectcraft/ec0-lossless-preparation.json`.
