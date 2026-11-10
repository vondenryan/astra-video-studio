# Architecture — Sprints 0–4

Historical foundations are retained below. Current extensions are documented by sprint at the end of this file.

`MCP stdio → typed studio_status → configuration, executable discovery, media version checks, workspace permission probe`.

The MCP server uses the official Python SDK's FastMCP v1 API. Pydantic defines its structured output contract. AE discovery reads PE version metadata without starting AE. FFmpeg/ffprobe run only fixed `-version` arguments with a five-second timeout, without a shell or visible console window.

The configured workspace is the only artifact destination. `contained_path` resolves traversal and symlinks before permitting artifact paths. Executable locations are trusted operator configuration, outside the workspace by design. There is no external media import, generic shell tool, arbitrary JSX execution tool or network listener.

`prepare-probe` creates a unique job directory, a manifest and a trusted read-only JSX script. `verify-probe` checks the acknowledgement ID, status, size, AE 25.x version and item-count type. These commands do not run AE. Missing acknowledgement is unconfirmed, never success. The probe reads only `app.version` and project item count. It never saves, opens, closes or creates a project. A local acknowledgement is diagnostic evidence, not a security attestation.

Sprint 1 adds `MCP → ProjectManager → BridgeRunner → reviewed JSX template → AfterFX.exe -r → matching JSON acknowledgement`. A Windows-session named mutex serializes submissions across Astra processes. Synchronous calls return within the 60-second acknowledgement deadline; launcher exit is not completion. Jobs journal prepared/submitting/submitted/terminal states with UTC timestamps, validated command arguments, PID and artifact paths. Manifests and journals use atomic JSON replacement.

Creation allocates an exclusive UUID directory. A fixed JSX template checks active-project safety, creates one composition/text layer, fits and centers the visible text bounds, saves the AEP, closes and reopens **that new output only**, and reports persisted project metadata. Python independently checks file size/path, dimensions, fps, duration, stable comment IDs, text, centered position/anchor and records the AEP hash. AE 25.5 returns 3-component vectors even for these 2D transforms; Z must be zero. AE native IDs are reported alongside Astra comment IDs and are not used as array indexes.

Untracked/nonempty or modified open projects are protected. A saved Astra-managed project may be replaced only if AE reports `dirty === false`. This property is documented by the community as unofficial; if unavailable, protection fails closed. An empty untitled project is allowed. An internal snapshot template is reserved for explicitly approved preservation workflows; it is not exposed as an MCP tool. During validation the operator explicitly authorized a snapshot of additional manual edits.

Before submission, `ae-pending.json` is persisted. Missing, oversized or invalid/mismatched acknowledgements cause timeout quarantine. A cancellation marker prevents a queued script from starting mutations after timeout. Already-running AE operations are never terminated. Quarantine persists across restarts **in the same configured workspace**; use one workspace per AE session. The named mutex serializes other workspaces during an active call, but persistent quarantine cannot coordinate independently configured roots after a caller exits. Cross-workspace recovery is unsupported; do not switch roots to bypass a pending job.

Sprint 2 introduces `MotionService → frame-aware declarative planner → versioned motion/transform templates`. The inspector now reports every transform's native key times/values, interpolation types, temporal ease, sample values and expression/blur state. Host enums are decoded via native string values because strict identity comparisons misclassified AE enums during real testing. Vector dimensions come from actual property values, including AE's three-component 2D returns; spatial temporal ease uses one speed.

Combined real testing exposed a host completion gap: publishing JSON at the end of a script could allow the next `-r` before AE released its running-script state. The operator observed a concurrent-script warning. The template now stores the serialized report in a per-operation global record and uses a fixed `app.scheduleTask` callback after 500 ms to publish it after the main invocation returns. Only the internally generated operation UUID is part of that callback's code string; all report content stays data. The runner holds the mutex another 750 ms after acknowledgement before returning. This is empirically tested conservative spacing, not a guarantee against manual scripts or modal dialogs. Missing deferred acknowledgement still times out and quarantines the workspace.

Every edit verifies the saved source hash, inspects the active target, validates parameters/timeline, and copies a source snapshot before submitting mutations. The fixed template checks active path, unsaved state, stable target IDs and protected animation again in AE. It saves to an exclusive version path before changes, applies native values/keyframes within an undo group, saves and reopens the output. Python compares output metadata against the planned keys/ease, verifies unrelated target transforms and the unchanged source hash, and only then updates the root manifest's `current_version`. Previous verified versions remain recognized as managed files. The inspector follows the latest verified version; failed artifacts are retained without silently becoming current.

Static edits refuse keyed/expression properties. Motion appends only outside existing key spans; it never removes keys or expressions. Four skills compile bounded parameters into cubic/linear tracks with frame-quantized times and optional explicit overshoot. The product exposes typed intent, not user-supplied JSX or shell commands. Cross-call concurrency may cause a safe active-path rejection if another operation switches the project between inspection and mutation; it must not force a project switch or overwrite.

Sprint 3 adds `ExistingProjectService`, approved source read roots and sidecar identity mapping. Open-copy hashes a trusted source, produces byte-identical source/working copies, opens only the working AEP and normalizes inspection IDs in Python. No client comment writes are needed. Every later inspector/transform receives the map and resolves native IDs to the same UUIDs. Root manifests track the current verified version; versions carry source/snapshot/result evidence.

Explicit `project_save` differs from edit tools: its purpose is to preserve the current managed state, so it can capture unsaved manual edits into a new version. It extends mappings from verified native IDs, snapshots the saved parent, saves/reopens/verifies all inspected state, then advances the manifest. Other operations still reject dirty state and unexpected saved-source hash changes. Inspector capabilities/locked/separated flags are checked in Python and again in AE.

Selective-edit verification now compares all non-target inspected layers/compositions and the target's untouched metadata, not just its transform tracks. This is metadata isolation, not exhaustive pixel/effect/plugin equivalence. Native AE reads of project-linked media/expressions remain governed by the trusted source project; Python restricts source-file reads and owned artifact writes but does not sandbox AE itself. External read roots are operator environment configuration.

Sprint 4 replaces repeated command-line delivery with a reviewed idle inbox: one `-r` bootstrap (manual execution fallback when needed) installs a scheduled AE dispatcher; later submissions are generated UUIDs only. The listener evaluates the fixed owned `workspace/jobs/<UUID>/operation.jsx` path, then waits for deferred acknowledgement before accepting another item. The product still exposes no arbitrary-code or path execution tool. Heartbeat, occupied inbox, active-job and stale-session checks fail closed; pending bootstrap/session metadata remains available for review. No remote service/listener is created.

`TreatmentService` appends only allowlisted native Fill/Gaussian Blur or static rectangle/ellipse masks, using the same snapshot/save/reopen/version promotion boundary. The inspector reports selected effect values and mask paths/modes. Host-derived mask enum values required explicit numeric-difference checks; strict comparisons misclassified an actual Add value during live testing. All existing treatments and unrelated inspected state are checked before promotion.

`PreviewService` is a bounded four-slot, single-worker local queue. A preview job snapshots its source identity/hash and plan; preparation temporarily opens a private AEP, writes only its one-item render queue and restores the previous saved interactive project. `aerender` uses that private queue; no `-reuse` is requested. An exclusive persistent renderer marker precedes process launch so crashes/interruption leave a review boundary. The marker is removed only after confirmed process exit; unknown native renders block another preview. Helper processes have bounded stages; active native cancellation never kills interactive AE.

The actual installed lossless sequence preset is detected (TIFF Sequence with Alpha on this host, with PNG supported where available). Exact frame sequence validation precedes FFmpeg H.264 encoding, ffprobe count/duration/resolution/FPS checks and full error-checked decode. Three sample PNGs are retained with logs, AEP copy and MP4; owned intermediates are cleaned only after verification. Async jobs require a live host; durable journals are evidence, not an auto-resume mechanism.

Frame samples may be inspected visually when that actually occurs and must be reported as sampled-frame review, not full motion/artistic approval. Reference analysis, broader direction/review automation and scene planning remain later increments.
# Sprint 5: Director and expanded editing

`director.py` owns immutable scene plans, integrity hashes, bounded Portuguese revisions and execution checklists. A plan contains typed elements and motion requests, stable IDs and explicit timeline phases. `scene_build` creates a native owned scene (or rebuilds its unchanged parent into a new version); `BatchService` preflights and verifies all motions before `PreviewService` renders. A scene reaches success only after its child preview passes full decoding. Plans/executions/reviews live in `workspace/plans`, journals in `workspace/jobs` and native versions in `workspace/projects`.

`layers.py` adds typed text/shape/solid/media and approved local asset copying. `motion_engine/batch.py` provides one-project bounded batch and stagger compilation. Seven individual skills now include native text mask reveal, seeded shake and 2D parallax. Inspection exposes mask path keys and explicit text styling. New texts reset character/paragraph styles to avoid inherited AE defaults.

`references.py` probes approved images/video and extracts bounded samples using FFmpeg. It makes no semantic claim. `visual_review` stores only observations of actually viewed samples, matches reference video hashes and leaves full-playback rhythm pending. The host performs rich language interpretation through typed requests; the local backend has no paid model dependency. See [scene workflow](scene-direction.md).

# Sprint 6: scene structure and dependency verification

`scene_editing.py` defines ten closed request schemas, dependency-graph validation, frame timing policies and a versioned scene service. `scene_ops.jsx` is a fixed template included by `templates.py`; it is not user-provided script input. Native code compares preflight metadata before mutation, saves only a new AEP and reopens it. Python verifies the requested edits and retained inspected state before advancing the manifest.

The inspector includes source/native relations, matte and blend state, null status, composition background and recursive animation/expression counts. Scene editing samples a 2D world basis for static parent compensation; ordinary inspection leaves this derived internal field null. Source native IDs define composition edges independently of native type labels. Both Python and native insertion preflight reject composition cycles. Existing motion verification accounts explicitly for the added key counts.

See [scene editing contracts and limits](scene-editing.md). Frame-preserving FPS changes support only static still contents, not arbitrary retiming. Structural edits refuse stored expressions and preserve dependency boundaries. This increment does not replace the Director's scene template or implement the remaining professional roadmap.

# Sprint 7: editable design and responsive identity

`design.py` owns typed text/path/paint/animator/layout requests, immutable token records and a verified design service. `svg.py` parses a bounded UTF-8 subset into native Bezier data without external resources or rasterization. The fixed `design_ops.jsx` helper performs native font resolution, typography, vector operations and layout; the action allowlist adds only `design_fonts` and `design_edit`.

Inspection now records character style runs, paragraph overflow, text animators, shape groups/paint/Trim Paths/morph keys and local bounds. Known synchronous design errors retain the output and restore the source that was confirmed clean before mutation; unknown/timeout execution still uses existing quarantine. Post-reopen verification failures do not advance manifests.

Layout profiles use explicit bindings, mid-composition bounds, immutable tokens and safe areas. General transform key replacement and art-direction synthesis remain separate future work. See [design contracts and limitations](design-tools.md), including unavailable gradient-stop editing and the strict SVG subset. No dependency or paid service was added.

# Sprint 8: guarded native animation editor

See also the Sprint 9 addition below for coordinated property revisions.

`animation.py` defines explicit version/semantic-state guards, frame-window CRUD, side-specific temporal/spatial patches, grouped transform retime and blur settings. `animation_ops.jsx` is another fixed trusted helper included in the existing template; no property path, expression, JSX or shell escape is exposed. Native mutation compares preflight state, saves a unique version, reconstructs manual tracks and reopens them. Verification compares native keys/active curves and retained inspected project state before promoting a manifest.

The inspector now includes spatial tangents, automatic/continuous/roving flags and complete blur parameters. Semantic hashes omit display samples and AE-derived Linear/Hold temporal ease records; Bezier controls remain strict. The editor protects automatic/continuous tracks and expressions, preventing implicit recalc or conversion. Group retime adjusts speeds for actual rounded segment durations without changing composition/layer duration.

Preview completion was hardened with bounded PermissionError retries for atomic JSON replacement, observed Future exceptions, failure-only fallback records and slot release even if the main terminal journal write fails. This is fault propagation, not persistent queue restart/resume from future Sprint 13. Native pending markers continue to block unknown execution. See [editor contracts](animation-editor.md).


# Sprint 9: property revision orchestration

`revisions.py` defines closed discriminated patch schemas, immutable plan storage, property/dependency fingerprints, explicit manual capture, one-shot application, metadata comparison and append-only restore. It delegates preflight and verification to scene/design/animation modules. `revision_ops.jsx` executes the selected bounded operations in one new native AEP and returns per-step inspection evidence. All steps plus saved/reopened metadata must pass before the manifest advances. The 1.2 MB estimate guards the existing 2 MB native acknowledgement limit. Unknown execution remains quarantined.

Director.revision_patch produces a plan using the declared PT grammar and stable explicit targets. It is distinct from full owned-scene rebuilding. Restore copies a selected verified AEP, reconstructs the native-ID sidecar from stored metadata and opens only that new workspace copy. See [revision contracts](revisions.md).

# Stint 9.1: bounded host presentation

responses.py is a presentation boundary around rich MCP/CLI results. It persists complete immutable content-addressed snapshots and projects only constant-size summaries into normal responses. Service return types and full verification are unchanged. The MCP decorator adds an explicit response_mode keyword; full mode preserves the original structured payload. Compact and page budgets include the actual duplicated MCP text/structured representations.

project_query reads a verified saved state by default or explicitly requests one live native inspection; operation_query reads an immutable hash reference. Filtering/pagination controls composition/layer/transform/key/sample sections and other known records. A small full-state evidence file is not a replacement for source AEP snapshots; both are retained. See [contract, examples and limits](compact-responses.md).

Native JSX/bridge/renderer transport is unchanged. Stint 9.2 will separately address file-backed native evidence with a small acknowledgement, subject to live testing. Host compaction does not remove native inspection cost or its current limits.

# Stint 9.2: native result publication and verification

The default BridgeRunner protocol is artifact-v1. The controlled template writes the complete original result inside a versioned native-result.json, hashes actual file bytes using chunked ES3 SHA-256 and publishes only a small descriptor via the existing idle acknowledgement callback. result_artifacts.py validates fixed ownership/filename, strict schema, status/UUID, bounded bytes, stable file metadata, hash and parsed content before returning the hydrated original result. Full data then follows unchanged service verification and version promotion; native_evidence records the raw artifact separately from normalized service metadata.

ACK and evidence bounds are independent (8 KiB / 16 MiB). Revision preflight budgets intermediate snapshots and prepared track growth against the latter; explicit inline-v1 preserves the legacy estimate. Publication/validation failure never frees quarantine or triggers fallback/retry. The dispatcher/mutex/bootstrap are unchanged. See [native transport](native-result-transport.md) for staged compatibility and acceptance limits.


## Sprint10 — immutable audio sidecars and isolated audio previews

MCP61 tools → AudioService → approved owned audio copy/decode → content-addressed AudioState/AudioMarkers. Five audio operations are synchronous and never call AE. AudioTarget binds project/composition, saved AEP SHA and optional parent audio-state SHA; all range/source/dependency guards run before snapshots. New states branch explicitly; no mutable project audio head or automatic rebase. AEP/audio parents and asset manifests/PCM are retained and hash checked.

The sixth tool audio_preview_render subclasses the preview request with a separate20s cap and required AEP/audio hashes. It shares the existing single worker/four slots, isolated AE picture render and pending/cancel safeguards. Audio mix is checked before native preparation; picture is encoded silently then muxed with AAC. Source AEP/audio dependencies and final streams/decode are checked before job success. Native code/bridge templates are unchanged; there is no native AE audio layer/marker insertion. Silent preview_render remains15s. Full details/units/limits: [audio tools](audio-tools.md).

FFmpeg inputs are local approved media; filters are generated from closed numeric schemas and no shell. Inspection normalizes PCM to48kHz/stereo/16-bit; sample-peak/RMS and energy candidates are not true-peak/loudness/semantic beat analysis. Package/advanced delivery and durable recovery remain11/13. EffectCraft is deferred; no engine abstraction or integration is introduced by Sprint10.


## Sprint11 — final render and collected delivery

RenderService reuses the same single worker/four slots/isolated native pipeline as previews with independent FinalRenderRequest and operator ceilings. Color8bit/sRGB interpretation, source FPS/resolution and byte budgets are explicit. Per-render acknowledgements report effective output templates/settings/color. H.264 uses per-frame setparams plus final ffprobe tags; TIFF alpha is native, hash-preserving, no guessed unpremultiply/resize/depth conversion. Every frame/alpha channel decodes before success.

DeliveryService snapshots the saved source and opens a disposable inspection copy, collects only approved roots, then relinks/saves/reopens only the package AEP. Trusted delivery_inspect/collect/validate templates preserve all inspected composition/layer state and interpretation, restore the checked-clean operator project and use normal native UUID/SHA acknowledgement/quarantine. Proxies/sequences/layered sources/stored expressions/unknown plugins/missing fonts fail conservatively. Fonts/plugins are listed, not copied. No project manifest/history is promoted by collection.

Package manifest/index pin file size/hash and exact membership. Read-only validation reopens AEP, verifies contained media paths/fonts, decodes output and reproduces PCM from relative audio assets. The delivery_audio_v1 recipe is separate from the original immutable AudioState; it is not an implicit rebase to the relinked AEP hash. Package native calls wait on existing render quarantine. Atomic journal sharing denials have bounded read-only retries, not operation replay. See [final delivery](final-delivery.md).

## Aceite final VÉRTICE

Orquestração de aceitação usa somente o MCP público existente, sem nova rota de execução. Plano/assets imutáveis, receipts por chamada, comparação de hashes e fonte nova por operação. O gate manual precede project_save/revisões; render e aprovação humana precedem a reconstrução vertical em projeto separado. Estado:docs/final-reference-acceptance.md.
