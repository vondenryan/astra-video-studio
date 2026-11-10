# Tool contracts

## studio_status

Input: empty object `{}`. Local stdio only. No user-supplied commands or paths accepted in tool arguments.

Output: `StudioStatus` (Pydantic schema published as MCP output schema):

- `operation_id`: unique hexadecimal UUID; `timestamp`: UTC ISO 8601.
- `status`: `ok` if platform, workspace and all three binaries pass diagnostics and no pending AE submission exists; otherwise `degraded`.
- `platform`, `windows_supported`, `python_version`.
- `after_effects`, `ffmpeg`, `ffprobe`: `available`, `path`, `version`, `error`.
- `workspace`: configured `path`, actual `writable` probe result and optional `error`.
- `bridge_status`: `not_validated` before a verified Sprint 1 creation in this workspace, or `acknowledged` when persisted creation evidence exists. This is historical evidence, not a live probe.
- `artifacts`: empty (the temporary permission probe is deleted); `warnings`: actionable limitations.

Expected absence, timeout and permission problems are returned as diagnostics. Invalid MCP arguments are handled by SDK schema validation. Configuration is loaded per call, never taken from tool payload. `windows_supported` checks the Windows 10/11 OS family; Windows 11 can report the NT release as 10. The full platform string remains visible.

## Local CLI only

`astra-studio status`: same diagnostics, JSON to stdout.

`astra-studio prepare-probe`: emits a unique `job_id`, `script`, `result`, and `prepared_not_executed` state; creates `workspace/bridge-probes/<job_id>/manifest.json` and `probe.jsx`.

`astra-studio verify-probe --job-id <id>`: validates an AE-produced result or returns `unconfirmed` if missing. Invalid result files exit with an error; no AE launch, wait, retry, or cancellation is performed.

## Sprint 1 MCP tools

`project_create(request: ProjectCreateRequest) -> OperationResult`: creates a new unique project with a centered editable title, saves it, reopens it, and verifies its metadata. Defaults: `name="Astra Demo"`, `title="ASTRA VIDEO STUDIO"`, width 1920 (64–7680), height 1080 (64–4320), fps 30 (1–120), duration 5 seconds (0.1–300), font size 90 (8–500). No arbitrary paths or code are accepted. Title is at most 500 characters; project name at most 120. Nonfinite values, unsupported controls, empty text and unknown fields are rejected. Multi-line titles are allowed and AE newline normalization is accounted for. Leaves the new project open in AE. Replaces only empty untitled or unchanged Astra-managed projects; never an untracked or modified project.

`composition_inspect(project_id: str) -> OperationResult`: reads the already-active verified project, returning comps, layers, stable comment IDs, native AE IDs, text, bounds, transforms and timings. Does not switch projects or save. Unknown IDs and unverified creations are rejected before submission.

`job_status(operation_id: str) -> JobStatus`: reads the persisted journal with timestamps, action, status, command/PID when submitted and result. Never retries or clears quarantine. IDs must be 32 lowercase hexadecimal characters.

`OperationResult` has `operation_id`, status (`succeeded`, `failed`, `blocked`, `timeout`, `busy`), optional `project_id`/`project_path`, `artifacts`, `data` and readable `error`. A created path is not an assertion of success: use status and the inspection evidence. Malformed arguments and unknown IDs are MCP tool errors. AE and runner failures are structured operation results. Calls are bounded synchronous operations in this increment; a job ID remains available for historical inspection, not a background rendering API.

Additional CLI commands: `create-demo`, `inspect --project-id <id>`, `job-status --job-id <id>`. These call the same services as MCP.

## Sprint 2 MCP tools

`layer_transform(request: TransformRequest) -> OperationResult`: target UUIDs plus typed `values` for position, anchor, scale, rotation and/or opacity. Requires the latest verified Astra version to be active and unchanged. Snapshots its saved source, saves a unique new version, reopens and verifies it. Does not overwrite static values on a keyed or expression-driven property. See `motion-skills.md` for numeric bounds.

`motion_apply(request: MotionRequest) -> OperationResult`: target UUIDs, `skill`, `start_time`, `duration`, typed `params` for slide_in/scale_pop/fade_in_out/smooth_zoom. Times round to frames; the plan must fit comp/layer lifetimes. Expressions, touching/overlapping keyed spans, ambiguous IDs and 3D layers are refused. Saves/reopens a unique version with source snapshot and hash preservation. `data.applied_plan` contains the actual keyed timeline. Motion blur enables both switches when requested; false preserves prior blur state.

Both return `project_id`, new `project_path`, operation ID, saved version/source snapshot/manifest artifacts and inspected metadata. `data.version_id` identifies the version. Validation errors are MCP tool errors; acknowledged AE/runner failures remain structured operation results. `composition_inspect` now follows the root manifest's last verified version and reports transforms with keys, in/out interpolation/native enum values, temporal ease and samples. `job_status` remains a read-only journal query.

The acknowledgement deadline is 60 seconds after submission. Reports are deferred through AE's task queue; after receipt, the runner retains the instance mutex for 750 ms before returning, so total call time can slightly exceed the acknowledgement deadline. This spacing is included in the end-to-end acceptance test. Modals or manual scripts can still cause timeout; there is no automatic resend.

Additional CLI: `motion-apply --request '<JSON>'`, `layer-transform --request '<JSON>'`, using the request object itself (without the MCP outer `request` wrapper). No JSX, executable or filesystem path parameters are accepted.

## Sprint 3 MCP tools

`project_open_copy(request: ProjectOpenCopyRequest) -> OperationResult`: `source_path` is a string (1–32767 characters) naming an existing `.aep` of at least 64 bytes. Relative to workspace, or absolute under workspace/operator-approved `ASTRA_IMPORT_ROOTS`. No per-call root overrides or authorization booleans. Produces an exclusive working copy and original-source backup, checks source/backup/copy hashes, opens the copy, maps native IDs to UUIDs without comment writes. Returns new `project_id`, working `project_path`, source/backup paths, file-footage warnings when reported by AE, and compositions/layers. Refuses dirty/unrelated active projects; a clean requested source may already be active.

`project_save(project_id: str) -> OperationResult`: explicitly preserve the active managed state in a unique new version, including unsaved manual edits. Snapshot prior disk file; extend mappings for manual additions/duplication; save/reopen; compare inspected state and source/snapshot hashes before updating the current pointer. Does not overwrite or accept output paths, switch projects, or silently save an unrelated open AEP.

`composition_inspect` and versioned edit tools now support mapped existing-project copies. Inspection includes original comments, native IDs, locked/enabled/3D/editable capability, parent IDs, timing and available/separated transform flags. Target UUID inputs remain 32 lowercase hex characters; output ID prefixes are representations, not comment rewrites. Camera/light/3D/locked/separated targets can be inspected but are refused by 2D edit operations. Unrelated-layer/composition verification uses this inspection metadata.

CLI equivalents: `open-copy --source <path>`, `save --project-id <id>`. External roots remain read-only permissions for source selection; AE may resolve project-linked media itself. Collecting/relinking media, previews and broad effect/mask editing remain deferred. Submission, executable presence and diagnostic `ok` must never be presented as successful project editing.

## Sprint 4 MCP tools

`effect_apply(request: EffectRequest) -> OperationResult`: normal target IDs, `effect` fill/gaussian_blur and typed allowlisted params. Appends a native effect to a new saved/reopened version; preserves old effects/source snapshot. `data.item_id` is the UUID embedded in its generated name. No arbitrary match names, plugins or code accepted.

`mask_create(request: MaskRequest) -> OperationResult`: normal target IDs, rectangle/ellipse shape, `[x,y,width,height]` layer-coordinate bounds, add/subtract mode, bounded feather/opacity and inversion. Appends a static editable path in a verified new version. Schema details in `preview-rendering.md`.

`preview_render(request: PreviewRequest) -> PreviewSubmission`: project/composition UUIDs, start_time 0–300 s, duration 0.1–15 s, max_width 64–1920. Frame-quantized comp-bounded interval, source ≤4K/900 frames. Returns `job_id`, queued/busy, optional error. Use `job_status(operation_id=job_id)` for completion. Four outstanding jobs maximum, one worker per process; native-render marker prevents concurrent process rendering in the same workspace. Output is currently silent H.264/yuv420p MP4.

Preview journal status can be queued/running/succeeded/failed/blocked/timeout/cancelled/busy. `OperationResult` now permits these additional queued/running/cancelled states. Completed result data contains video path/hash, source hash, render-copy path, applied plan, verified dimensions/FPS/duration/decoded count, sample PNG paths and AE preparation evidence. Logs/partial artifacts remain available for failures. A queued response or renderer exit alone never means success.

`job_cancel(operation_id) -> JobStatus`: preview jobs only; writes a cancellation request marker. `cancel_requested=true` is not terminal completion. Queued work stops before dispatch; active native work finishes or reaches its timeout before further stages are skipped. Never kills interactive AE or automatically replays a job. Native unresolved/interrupted rendering keeps `preview-pending.json`; AE delivery retains its separate `ae-pending.json` quarantine.

`studio_status` adds `bridge_runtime`: transport, readiness/active job, instance ID and reviewed bootstrap path when available. Readiness is a heartbeat snapshot; legacy `bridge_status` preserves historical project acknowledgement. `bridge-start` is a non-mutating CLI setup command. Other CLI additions: effect-apply/mask-create/preview-render with --request JSON, job-cancel with --job-id.

MCP operations now dispatch through the reviewed local idle inbox after one confirmed bootstrap; no new per-operation -r launcher. Pending/stale sessions require review. Source/queue hashes and render verification replace assumptions about execution success. Media import/collect/relink, audio previews, broad plugin/mask animation and automated visual direction remain outside this increment.
# Sprint 5 additions (22 tools total)

All additions expose typed structured output. Requests reject extra fields and nonfinite numbers. IDs are 32 lowercase hex characters. Existing tools and protections remain available.

| Tool | Input | Output/behavior |
| --- | --- | --- |
| `layer_create` | `request: LayerCreateRequest` with project/composition IDs and `layer: LayerSpec` | OperationResult; text/shape/solid/media in a new saved/reopened version; media requires imported asset ID. |
| `media_import` | `request` with project ID and approved `source_path` | OperationResult with asset ID, owned copy, hash and native footage metadata. |
| `stagger_layers` | `request` with project/composition IDs, unique layer IDs, start/duration/interval, base skill/params, reverse | OperationResult; up to 20 validated motions in one version. |
| `motion_batch` | `request.motions` | OperationResult; 1–40 MotionRequests for one project, collision preflight and native verification. |
| `scene_plan` | `request: SceneBrief` | ScenePlan; immutable hashed plan, no AE mutation. |
| `scene_execute` | `plan_id` | SceneExecution; build, verified motion batch and queued preview. Keep server alive. |
| `scene_status` | `execution_id` | SceneExecution; success only after child preview validates, with functional/visual checklist. |
| `scene_revise` | `request: SceneRevision` with plan ID, instruction, optional typed changes | New ScenePlan; explicit supported Portuguese changes or host-supplied typed changes. |
| `visual_review` | `request: ReviewRecord` | SceneExecution with actual sampled-frame review, provenance and full-playback pending. |
| `reference_analyze` | `request` with approved source path, optional sample_times | ReferenceReport; metadata, hashes and samples; visual_analysis_performed=false. |

`composition_inspect` additionally accepts `sample_time` (default 0) for current position/anchor evaluation. Motion duration defaults to 2 seconds. See [motion schemas](motion-skills.md) and [Director workflow](scene-direction.md) for limits, examples and language coverage. File integrity and rendering checks do not imply aesthetic approval.

# Sprint 6 additions (32 tools total)

Ten new tools accept `request` and return OperationResult: `composition_create`, `composition_update`, `precompose_layers`, `composition_layer_add`, `null_create`, `layer_duplicate`, `layer_update`, `layer_remove`, `layer_parent`, `track_matte_set`. All use the current saved project, preserve source/snapshot and promote a new version only after save/reopen verification.

Detailed fields, examples, frame/FPS policies and dependency guards are in [scene editing](scene-editing.md). Creation responses expose created_composition_id/created_layer_id. The inspector adds source identity/kind, matte/blend state, null/auto-orientation status, background and recursive animation/expression counts. Earlier tools retain their inputs and protected behavior.

# Sprint 7 additions (42 tools total)

`fonts_list` returns an OperationResult containing actual installed fonts/capabilities without editing a project. `design_tokens_set` returns an immutable TokenRecord. Eight design mutations return OperationResult: `text_style_set`, `text_animator_apply`, `shape_path_set`, `shape_style_set`, `shape_trim_apply`, `shape_morph_apply`, `vector_import`, `layout_apply`.

See [design tools](design-tools.md) for full inputs, examples and limits. Existing `layer_create` additionally supports `text_box` for paragraph text and `shape="empty"`. New design mutations preserve saved sources/snapshots and verify controlled content after reopen. The inspector reports text styles/overflow/animators and native shape data/keys. Native gradient color-stop editing is explicitly not exposed; unsupported SVG features fail before mutation.

# Sprint 8 additions (48 tools total)

`animation_inspect` reads native transform curves/samples and returns saved-AEP, composition and track fingerprints. Five mutation tools return OperationResult: `keyframes_edit`, `easing_set`, `motion_path_set`, `animation_retime`, `motion_blur_set`. All require explicit saved-version/state guards; key edits also declare frame scope/mode/boundary intent. See [animation editor](animation-editor.md) for request examples and restrictions.

`anticipate_settle` expands the motion skill union to eight presets while retaining existing request compatibility. New inspector fields expose spatial/temporal flags, tangents and blur sampling. Only Bezier temporal ease controls are writable; Linear/Hold ease inspection is derived. Worker completion faults are exposed as failed status, including a durable failure fallback when the main preview journal cannot be updated; no native retry is implied.


# Sprint 9 additions (53 tools total)

All five tools return OperationResult. `revision_plan` takes a typed immutable patch with base hash; `revision_apply` takes revision ID, plan hash, expected current hash and explicit manual-capture policy. `version_compare` compares two verified version IDs (or `initial`); `version_restore` appends a byte-identical restored version with an explicit reason/current hash. `director_revision_plan` is a bounded PT instruction-to-patch adapter for one explicit layer. See [full revision contracts and limits](revisions.md).

Conflict results have status `blocked` and identifiable property paths/hash pairs; validation/stale-file errors occur before mutation. A consumed attempt cannot be replayed. Native output/snapshot/step evidence, manifest promotion and sampled visual review remain separate.

# Stint 9.1 additions (55 tools total)

Rich tool results are compact by default, capped at 8 KiB per MCP CallToolResult including text/structured copies. A top-level response_mode=full returns the exact original structured payload and puts the complete evidence reference in _meta.astra_evidence. Internal Python services keep full results. CLI --response-mode full preserves its original shape.

project_query and operation_query return EvidencePage, capped at 50 rows and 16 KiB. Use filters and next_offset, with keys/samples in explicit sections. Project queries label verified saved state versus live acknowledged state. Snapshots are workspace-contained, immutable and hash verified; no arbitrary paths or scripts are accepted. See [full compact response contracts](compact-responses.md). Native transport limits are unchanged.

# Stint 9.2 transport (55 tools unchanged)

Public typed operations and full service result data retain their prior shape. The native default now uses a small verified artifact-v1 acknowledgement; complete data is hydrated from the fixed per-job evidence before existing verification. Job journals retain native_evidence with raw artifact path, byte count and hash; failures/unknown evidence keep their original protection boundaries. No new execute/file-path tool is exposed. ASTRA_AE_RESULT_TRANSPORT is operator configuration, not a request field. See [protocol, bounds and compatibility](native-result-transport.md).


## Sprint10 — audio tools (61 total tools)

See [audio contracts](audio-tools.md) for schemas, exact units, guard semantics and acceptance. audio_inspect/audio_clip_set/audio_markers_create/timeline_markers_set/audio_sync_plan return OperationResult through the existing compact/full policy. New query sections audio_clips/audio_markers/sync_events are explicit and byte-bounded. Audio source markers and timeline markers use different immutable evidence hashes.

audio_preview_render returns the existing small PreviewSubmission and uses job_status/job_cancel. It requires base_aep_sha256 and audio_state_sha256, allows<=20s/900frames, and preserves the silent15s route. Audio clips live in FFmpeg sidecars; no native source/keys/markers are changed. Planning produces a candidate audio state, not automatic promotion of an AEP or audio project head. Source-state hashes, asset hashes, ranges, gain/fade limits, no expressions for visual references and failure preservation are enforced. Full mode remains explicit; no arbitrary code/filter/path tools were added.


## Sprint11 — final delivery (65 tools total)

render_presets_list returns compact OperationResult with content-addressed preset evidence; inspect section render_presets. render_submit takes FinalRenderRequest and returns the existing small PreviewSubmission/job_id; job_status/job_cancel handle render_final too. Separate final ceilings do not change silent/audio preview contracts. Source hash, same FPS, explicit8bit/sRGB interpretation, even dimensions, safe interval and fresh relative destination are required. h264_aac requires an audio state; tiff_rgba8 preserves native source resolution/bytes/alpha association, with optional separate WAV.

delivery_collect takes project_id/base_aep_sha256/render_job_id/destination; requires completed verified final output matching the source. It returns delivery_id and manifest hash only after source/collected AEP comparison and acknowledged save/reopen. delivery_validate accepts the registered delivery_id and performs exact file/hash/links/font/native-reopen/decode checks plus audio recipe reconstruction. Fonts/plugins are dependency reports, not installed/copied. ready_for_delivery is technical local scope, not client/artistic approval or cross-machine portability proof. Full units, limits, unsupported dependencies and evidence: [final delivery](final-delivery.md).

## Fluxo de aceite final

Nenhuma ferramenta adicional: composition/layer/design/animation montam a referência24s; project_save captura ajuste manual confirmado; director_revision_plan/revision_apply executam dois patches em português; áudio/sync/render/delivery mantêm seus contratos próprios. Aprovação humana do layout paisagem é gate antes da versão vertical, não inferida de metadata/frames. Estado:docs/final-reference-acceptance.md.
