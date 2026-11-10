import logging
from mcp.server.fastmcp import FastMCP

from astra_video_studio.schemas import StudioStatus, ProjectCreateRequest, OperationResult, JobStatus, ProjectOpenCopyRequest
from astra_video_studio.existing_projects import ExistingProjectService
from astra_video_studio.config import Settings
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.motion_engine.schemas import MotionRequest, TransformRequest
from astra_video_studio.motion_engine.service import MotionService
from astra_video_studio.status import studio_status as collect_status
from astra_video_studio.treatments import EffectRequest, MaskRequest, TreatmentService
from astra_video_studio.media.preview import PreviewRequest, PreviewSubmission, PreviewService
from astra_video_studio.layers import LayerCreateRequest, MediaImportRequest, LayerService
from astra_video_studio.motion_engine.batch import BatchRequest, BatchService, StaggerRequest
from astra_video_studio.director import Director, SceneBrief, ScenePlan, SceneRevision, SceneExecution, ReviewRecord
from astra_video_studio.references import ReferenceRequest, ReferenceReport, analyze as analyze_reference
from astra_video_studio.scene_editing import (SceneService, CompositionCreate, CompositionUpdate, Precompose, LayerInsert, NullCreate, LayerDuplicate, LayerUpdate, LayerRemove, LayerParent, TrackMatte)
from astra_video_studio.design import (DesignService, FontsQuery, TextStyleSet, TextAnimatorApply, ShapePathSet, ShapeStyleSet, ShapeTrimApply, ShapeMorphApply, VectorImport, DesignTokens, TokenRecord, LayoutApply, store_tokens)
from astra_video_studio.animation import (AnimationService, AnimationInspect, KeyframesEdit, EasingSet, MotionPathSet, AnimationRetime, MotionBlurSet)
from astra_video_studio.revisions import (RevisionService, RevisionPlanRequest, RevisionApplyRequest, VersionCompareRequest, VersionRestoreRequest, DirectorPatchRequest)

from astra_video_studio.responses import (response_policy, EvidenceQuery, ProjectQuery, EvidencePage, query_evidence, query_project)
from astra_video_studio.audio import (AudioService, AudioInspect, AudioClipSet, AudioMarkersCreate, TimelineMarkersSet, AudioSyncPlan)
from astra_video_studio.media.preview import AudioPreviewRequest
from astra_video_studio.media.final_render import RenderService, FinalRenderRequest
from astra_video_studio.delivery import DeliveryService, DeliveryCollect, DeliveryValidate
from astra_video_studio.storyboard import (StoryboardService, StoryBrief, StoryExecute, StoryRevision,
    ReviewSamples, StoryReview)
from astra_video_studio.recovery import RecoveryService, QueueInspect, JobReconcile, ProjectDependencies, CleanupPlan
from astra_video_studio.layer_batch import LayerBatchService, LayersCreate

mcp = FastMCP("Astra Video Studio")


def tool():
    def register(fn):
        return mcp.tool()(response_policy(fn))
    return register


@tool()
def studio_status() -> StudioStatus:
    """Diagnose Windows, AE 2025, workspace write access, FFmpeg and ffprobe.

    Does not start AE or edit projects. Creates the workspace if needed and
    writes/deletes one temporary permission-probe file inside it.
    """
    return collect_status()


@tool()
def project_create(request: ProjectCreateRequest) -> OperationResult:
    """Create, save and reopen a NEW editable AEP with one centered title.

    Leaves it open in AE. Refuses to replace untracked or modified projects.
    Only an empty untitled project or an unchanged Astra-managed project may
    be closed. Every call uses a new output directory; never overwrites AEPs.
    """
    return ProjectManager(Settings.from_env()).create(request)


@tool()
def composition_inspect(project_id: str, sample_time: float = 0) -> OperationResult:
    """Read compositions/layers of the requested managed project already open in AE.

    Does not open, save or modify projects. IDs come from persistent comments.
    """
    return ProjectManager(Settings.from_env()).inspect(project_id,sample_time)


@tool()
def job_status(operation_id: str) -> JobStatus:
    """Read a persisted operation journal. Does not submit/retry any AE scripts."""
    return JobStatus.model_validate(ProjectManager(Settings.from_env()).job_status(operation_id))


@tool()
def layer_transform(request: TransformRequest) -> OperationResult:
    """Set static 2D transforms by stable IDs in a NEW saved version of an active Astra project.

    Preserves source/snapshot, refuses unsaved edits and keyed/expression properties.
    """
    return MotionService(Settings.from_env()).transform(request)


@tool()
def motion_apply(request: MotionRequest) -> OperationResult:
    """Apply a bounded slide/scale/fade/zoom/reveal/shake/parallax skill as native keys.

    Times snap to nearest frames. Preserves source/snapshot, refuses expressions,
    unsaved changes and overlapping keyed intervals. Saves/reopens a new version.
    """
    return MotionService(Settings.from_env()).apply(request)


@tool()
def project_open_copy(request: ProjectOpenCopyRequest) -> OperationResult:
    """Open an existing AEP as a unique workspace copy with byte-identical backup.

    Source must be in the workspace or operator-configured ASTRA_IMPORT_ROOTS.
    Never saves the original or rewrites its comments. Refuses unsaved/unrelated
    active projects; allows the explicitly requested source if already open/clean.
    AE may resolve linked media/expressions in a trusted source project.
    """
    return ExistingProjectService(Settings.from_env()).open_copy(request)


@tool()
def project_save(project_id: str) -> OperationResult:
    """Explicitly preserve the active managed project state in a NEW saved version.

    May capture unsaved manual edits; snapshots the prior disk file, never
    overwrites it, reopens/verifies the result and preserves stable sidecar IDs.
    """
    return ExistingProjectService(Settings.from_env()).save(project_id)


@tool()
def effect_apply(request: EffectRequest) -> OperationResult:
    """Append allowlisted Gaussian Blur or Fill to a layer in a new verified AEP version.

    Preserves source/snapshot and existing effects; no arbitrary effect names/code.
    """
    return TreatmentService(Settings.from_env()).apply(request)


@tool()
def mask_create(request: MaskRequest) -> OperationResult:
    """Append a static rectangle/ellipse mask in layer coordinates in a new AEP version.

    Supports bounded feather, opacity, add/subtract and inversion; preserves old masks.
    """
    return TreatmentService(Settings.from_env()).apply(request)


@tool()
def preview_render(request: PreviewRequest) -> PreviewSubmission:
    """Queue an isolated saved-project preview: AE PNG sequence → silent H.264 MP4.

    Poll job_status with returned job_id as operation_id. Success requires duration,
    FPS, frame count/resolution and full decode validation. Queue capacity is four.
    """
    return PreviewService(Settings.from_env()).submit(request)


@tool()
def audio_inspect(request: AudioInspect) -> OperationResult:
    """Copy approved local audio and inspect decoded duration/channels/peak/RMS. No AE write."""
    return AudioService(Settings.from_env()).inspect(request)


@tool()
def audio_clip_set(request: AudioClipSet) -> OperationResult:
    """Add/replace/remove a trimmed/gained/faded clip in an immutable audio sidecar, not AE."""
    return AudioService(Settings.from_env()).clip_set(request)


@tool()
def audio_markers_create(request: AudioMarkersCreate) -> OperationResult:
    """Create immutable manual source cues or uncertain energy-rise candidates; not semantic beats."""
    return AudioService(Settings.from_env()).markers_create(request)


@tool()
def timeline_markers_set(request: TimelineMarkersSet) -> OperationResult:
    """Version manual frame markers in the audio sidecar; does not insert markers into AE."""
    return AudioService(Settings.from_env()).timeline_set(request)


@tool()
def audio_sync_plan(request: AudioSyncPlan) -> OperationResult:
    """Plan audio clip alignment to verified saved transform keys; never moves native animation.

    Returns a candidate audio_state_sha256; use it explicitly for audio_preview_render.
    Energy cues retain detector uncertainty; mathematical alignment is not perceptual proof.
    """
    return AudioService(Settings.from_env()).sync_plan(request)


@tool()
def audio_preview_render(request: AudioPreviewRequest) -> PreviewSubmission:
    """Queue a separate <=20s/900-frame preview with versioned FFmpeg audio and full decode.

    Requires exact saved AEP/audio-state hashes, explicit gains/fades and no clipping.
    Uses the existing isolated AE render/queue; does not add native AE audio layers.
    """
    return PreviewService(Settings.from_env()).submit(request)


@tool()
def render_presets_list() -> OperationResult:
    """Discover bounded final presets from installed FFmpeg; AE template/alpha verified per actual render."""
    return RenderService(Settings.from_env()).presets()


@tool()
def render_submit(request: FinalRenderRequest) -> PreviewSubmission:
    """Queue a separate final render with explicit resolution/FPS/color/source hash and fresh destination.

    h264_aac requires audio; tiff_rgba8 verifies native alpha and every output frame.
    Shared isolated AE worker/quarantine; source FPS must match (no implicit retiming).
    """
    return RenderService(Settings.from_env()).submit(request)


@tool()
def delivery_collect(request: DeliveryCollect) -> OperationResult:
    """Collect a verified final job, copied AEP and approved media/audio into a fresh hashed package.

    Relinks/saves/reopens only the package copy; refuses unsupported/missing dependencies.
    Fonts/plugins are listed, never copied. Native timeout remains quarantined.
    """
    return DeliveryService(Settings.from_env()).collect(request)


@tool()
def delivery_validate(request: DeliveryValidate) -> OperationResult:
    """Hash-check package, acknowledge native reopen, inspect links/fonts and fully decode output.

    Read-only package validation; restores the checked-clean operator project.
    Technical verification is distinct from human playback, listening and artistic approval.
    """
    return DeliveryService(Settings.from_env()).validate(request)


@tool()
def job_cancel(operation_id: str) -> JobStatus:
    """Request cancellation of a preview. Does not kill interactive AE.

    Queued jobs stop before execution. An active renderer finishes or times out;
    cancellation_requested is not proof of completion. Poll job_status.
    """
    return JobStatus.model_validate(PreviewService(Settings.from_env()).cancel(operation_id))


@tool()
def layer_create(request: LayerCreateRequest) -> OperationResult:
    """Create text/shape/solid or imported-media layer in a new verified AEP version."""
    return LayerService(Settings.from_env()).create(request)


@tool()
def media_import(request: MediaImportRequest) -> OperationResult:
    """Copy approved local media into owned assets and import into a new AEP version."""
    return LayerService(Settings.from_env()).import_media(request)


@tool()
def stagger_layers(request: StaggerRequest) -> OperationResult:
    """Apply validated staggered motions to unique layers in one atomic saved version."""
    return BatchService(Settings.from_env()).apply(request.batch())


@tool()
def motion_batch(request: BatchRequest) -> OperationResult:
    """Preflight a bounded multi-layer motion batch, then save/reopen/verify one version."""
    return BatchService(Settings.from_env()).apply(request)


@tool()
def scene_plan(request: SceneBrief) -> ScenePlan:
    """Plan a 10–15 s local editable scene. Does not alter AE. Brief hints + typed fields.

    Stores immutable phases, elements, IDs and motions; no paid model inference.
    """
    return Director(Settings.from_env()).plan(request)


@tool()
def scene_execute(plan_id: str) -> SceneExecution:
    """Build a validated plan, apply native motion and queue a full-length preview.

    Returns rendering state. Poll scene_status; no success claim before decode.
    """
    return Director(Settings.from_env()).execute(plan_id)


@tool()
def scene_status(execution_id: str) -> SceneExecution:
    """Update a scene's child-preview status and functional review checklist."""
    return Director(Settings.from_env()).status(execution_id)


@tool()
def scene_revise(request: SceneRevision) -> ScenePlan:
    """Create an immutable revised plan from bounded natural phrases or typed changes.

    Supports quoted title/subtitle, overshoot to N%, duration to N seconds,
    slower entrance. Unknown requests fail explicitly; Codex can supply typed changes.
    Execute the revised plan to save a new version, preserving the original.
    """
    return Director(Settings.from_env()).revise(request)


@tool()
def visual_review(request: ReviewRecord) -> SceneExecution:
    """Record actual sampled-frame observations and provenance; never claims full playback."""
    return Director(Settings.from_env()).review(request)


@tool()
def reference_analyze(request: ReferenceRequest) -> ReferenceReport:
    """Inspect approved local reference metadata and extract frames; no semantic claim."""
    return analyze_reference(Settings.from_env(),request)


@tool()
def composition_create(request: CompositionCreate) -> OperationResult:
    """Add an empty composition to the active saved project in a verified new version."""
    return SceneService(Settings.from_env()).apply('composition_create', request)


@tool()
def composition_update(request: CompositionUpdate) -> OperationResult:
    """Change composition settings. FPS requires preserve_seconds/preserve_frames policy.

    Frame-preserving retime is limited to static still layers; no nested/video/audio retime.
    Shrinking cannot trim layers or referenced compositions. Never rescales layout implicitly.
    """
    return SceneService(Settings.from_env()).apply('composition_update', request)


@tool()
def precompose_layers(request: Precompose) -> OperationResult:
    """Move contiguous layers and all attributes into a precomp, preserving stable IDs.

    Parent/matte relations must remain inside selection. Refuses expressions that
    may depend on layer names/indices. Saves/reopens/verifies a new version.
    """
    return SceneService(Settings.from_env()).apply('precompose_layers', request)


@tool()
def composition_layer_add(request: LayerInsert) -> OperationResult:
    """Insert a composition as a layer, at integer start_frame; rejects dependency cycles."""
    return SceneService(Settings.from_env()).apply('composition_layer_add', request)


@tool()
def null_create(request: NullCreate) -> OperationResult:
    """Add a native 2D null controller in a verified new version."""
    return SceneService(Settings.from_env()).apply('null_create', request)


@tool()
def layer_duplicate(request: LayerDuplicate) -> OperationResult:
    """Duplicate a 2D layer with a fresh stable ID; preserves original and prior versions."""
    return SceneService(Settings.from_env()).apply('layer_duplicate', request)


@tool()
def layer_update(request: LayerUpdate) -> OperationResult:
    """Rename/reorder/set blend or visibility; static timing in integer composition frames.

    Relative shift or absolute start/in/out; animation retiming is protected.
    Blend modes: normal/multiply/screen/add. Name/order edits refuse project expressions.
    """
    return SceneService(Settings.from_env()).apply('layer_update', request)


@tool()
def layer_remove(request: LayerRemove) -> OperationResult:
    """Remove a 2D layer in a new file only if no parent/matte dependents or expressions."""
    return SceneService(Settings.from_env()).apply('layer_remove', request)


@tool()
def layer_parent(request: LayerParent) -> OperationResult:
    """Set/clear a 2D parent, rejecting cycles. Policy is explicit.

    preserve_local retains local values; preserve_world compensates static transforms
    and verifies world basis. Animated/auto-oriented ancestor chains are protected.
    """
    return SceneService(Settings.from_env()).apply('layer_parent', request)


@tool()
def track_matte_set(request: TrackMatte) -> OperationResult:
    """Set alpha/luma (or inverted) matte or remove it; preserve matte visibility.

    Uses AE23+ native API, stable IDs and dependency-cycle checks. Does not reorder layers.
    """
    return SceneService(Settings.from_env()).apply('track_matte_set', request)


@tool()
def fonts_list(request: FontsQuery) -> OperationResult:
    """List installed AE fonts by actual PostScript/session IDs; no project edits."""
    return DesignService(Settings.from_env()).fonts(request)


@tool()
def text_style_set(request: TextStyleSet) -> OperationResult:
    """Set exact installed font, typography and Unicode code-point style ranges.

    Supports point text and existing paragraph boxes. Rejects overflow by default,
    substitution and animated source text; saves/reopens/verifies a new AEP version.
    """
    return DesignService(Settings.from_env()).apply('text_style_set', request)


@tool()
def text_animator_apply(request: TextAnimatorApply) -> OperationResult:
    """Append editable native character/word entry: position, scale, opacity, range keys."""
    return DesignService(Settings.from_env()).apply('text_animator_apply', request)


@tool()
def shape_path_set(request: ShapePathSet) -> OperationResult:
    """Add a managed native Bezier group or update its static path; preserves old groups."""
    return DesignService(Settings.from_env()).apply('shape_path_set', request)


@tool()
def shape_style_set(request: ShapeStyleSet) -> OperationResult:
    """Set managed path fill/stroke/width/opacity in a new version. Gradients fail explicitly."""
    return DesignService(Settings.from_env()).apply('shape_style_set', request)


@tool()
def shape_trim_apply(request: ShapeTrimApply) -> OperationResult:
    """Append native Trim Paths with frame-quantized linear keys; protects existing trim."""
    return DesignService(Settings.from_env()).apply('shape_trim_apply', request)


@tool()
def shape_morph_apply(request: ShapeMorphApply) -> OperationResult:
    """Animate a static Bezier path between compatible vertex counts/order and closure."""
    return DesignService(Settings.from_env()).apply('shape_morph_apply', request)


@tool()
def vector_import(request: VectorImport) -> OperationResult:
    """Copy and convert a strict local SVG subset into editable native paths.

    No rasterization: unsupported transforms/compound subpaths/arcs/CSS/external
    references fail. Requires approved read roots and an existing shape layer.
    """
    return DesignService(Settings.from_env()).apply('vector_import', request)


@tool()
def design_tokens_set(request: DesignTokens) -> TokenRecord:
    """Store immutable color/type/spacing/safe-area tokens with integrity hash. No AE edit."""
    return store_tokens(Settings.from_env(), request)


@tool()
def layout_apply(request: LayoutApply) -> OperationResult:
    """Resize/reflow landscape, square or portrait using explicit layer bindings/tokens.

    Fits static local transforms and verifies safe areas/box overflow. Requires all
    visible visual layers; supports alignment/distribution and a background-cover role.
    """
    return DesignService(Settings.from_env()).apply('layout_apply', request)


@tool()
def animation_inspect(request: AnimationInspect) -> OperationResult:
    """Inspect native 2D tracks, spatial/temporal curves and samples; return version/state hashes."""
    return AnimationService(Settings.from_env()).inspect(request)


@tool()
def keyframes_edit(request: KeyframesEdit) -> OperationResult:
    """Explicit insert/update/remove/replace/move in an inclusive frame window.

    Requires base AEP and expected-track hashes, mode and boundary policy. Protects
    expressions and automatic/roving tracks; preserves keys outside the chosen scope.
    """
    return AnimationService(Settings.from_env()).apply('keyframes_edit', request)


@tool()
def easing_set(request: EasingSet) -> OperationResult:
    """Edit temporal speeds/influences/interpolation of existing selected keys with state guards."""
    return AnimationService(Settings.from_env()).apply('easing_set', request)


@tool()
def motion_path_set(request: MotionPathSet) -> OperationResult:
    """Set native position/anchor spatial tangents; explicit frame window and boundary policy."""
    return AnimationService(Settings.from_env()).apply('motion_path_set', request)


@tool()
def animation_retime(request: AnimationRetime) -> OperationResult:
    """Retime selected transform tracks together, preserving comp duration and rejecting collisions.

    Requires rounding policy and expected state per track; adjusts internal temporal
    speeds for actual rounded segment durations. Does not retime text/path/effect tracks.
    """
    return AnimationService(Settings.from_env()).apply('animation_retime', request)


@tool()
def motion_blur_set(request: MotionBlurSet) -> OperationResult:
    """Set explicit comp/layer blur, shutter phase/angle and bounded sampling in a new version."""
    return AnimationService(Settings.from_env()).apply('motion_blur_set', request)


@tool()
def revision_plan(request: RevisionPlanRequest) -> OperationResult:
    """Preview/store an immutable typed property patch without changing the active AEP.

    Captures expected property hashes and preserved scope. Save manual edits first.
    Accepts bounded content, text style, static transform/timing and manual animation edits.
    """
    return RevisionService(Settings.from_env()).plan(request)


@tool()
def revision_apply(request: RevisionApplyRequest) -> OperationResult:
    """Apply one hashed patch in a new verified version, preserving unrelated manual edits.

    Requires current AEP hash; capture_manual explicitly saves compatible unsaved
    edits first. Conflicting properties are reported without mutation. Never retries.
    """
    return RevisionService(Settings.from_env()).apply(request)


@tool()
def version_compare(request: VersionCompareRequest) -> OperationResult:
    """Compare inspected metadata of two immutable verified versions; no visual judgement."""
    return RevisionService(Settings.from_env()).compare(request)


@tool()
def version_restore(request: VersionRestoreRequest) -> OperationResult:
    """Restore a verified AEP as a NEW byte-identical version, retaining complete history.

    Refuses unsaved edits; save those explicitly first. No original version is overwritten.
    """
    return RevisionService(Settings.from_env()).restore(request)


@tool()
def director_revision_plan(request: DirectorPatchRequest) -> OperationResult:
    """Emit a property patch, distinct from scene_revise's complete owned-scene rebuild.

    Closed PT grammar, semicolon-separated: trocar título para "TEXT";
    atrasar entrada N frames entre A e B. Delay targets position keys only.
    Rejects any unknown clause; typed revision_plan supports broader operations.
    """
    return Director(Settings.from_env()).revision_patch(request)


@tool()
def operation_query(request: EvidenceQuery) -> EvidencePage:
    """Read immutable evidence by hash, with filtered sections and bounded pages.

    No AE submission or arbitrary paths. Keys/samples are separate explicit sections.
    Use evidence.sha256 from a prior response, then next_offset for stable paging.
    """
    return query_evidence(Settings.from_env(), request)


@tool()
def project_query(request: ProjectQuery) -> EvidencePage:
    """Inspect selected comps/layers/properties, max 50 rows and 16 KiB per page.

    Default reads verified saved metadata and explicitly excludes unsaved manual edits.
    refresh=true performs one read-only AE inspection, retaining the full native result.
    Continue with operation_query against the returned evidence hash for stable paging.
    """
    return query_project(Settings.from_env(), request)


@tool()
def brief_validate(request: StoryBrief) -> OperationResult:
    """Validate V2 structured brief, frame/reading budgets, tokens, pinned audio and reference notes. No AE edits."""
    return StoryboardService(Settings.from_env()).brief_validate(request)


@tool()
def storyboard_plan(request: StoryBrief) -> OperationResult:
    """Store immutable V2 multi-scene plan. Hero/split/editorial layouts; caller interprets brand and references."""
    return StoryboardService(Settings.from_env()).plan(request)


@tool()
def storyboard_execute(request: StoryExecute) -> OperationResult:
    """Execute an immutable storyboard ONCE into a new editable AEP, audio sidecar and queued final render.

    Leaves a new project open; refuses modified/unrelated active work. Poll storyboard_status.
    Keep this MCP process alive for the render worker. Failed/unknown attempts are not resent.
    """
    return StoryboardService(Settings.from_env()).execute(request)


@tool()
def storyboard_status(execution_id: str) -> OperationResult:
    """Read V2 execution/render status, retaining immutable prior evidence. Does not retry operations."""
    return StoryboardService(Settings.from_env()).status(execution_id)


@tool()
def storyboard_revise(request: StoryRevision) -> OperationResult:
    """Apply one Portuguese title/body patch, preserving non-target saved edits and native keys.

    Grammar: trocar título/texto da cena N para "...". Requires explicit current AEP hash
    and rebuild_audio=true; creates new versions/audio/render, consumes root-wide attempt budget.
    Save compatible manual edits with project_save first. Never rebuilds the whole scene.
    """
    return StoryboardService(Settings.from_env()).revise(request)


@tool()
def review_samples_create(request: ReviewSamples) -> OperationResult:
    """Extract hash-bound entry/hold/transition/exit/changed-interval frames from a verified render.

    Does not assert these frames have been viewed, the soundtrack heard, or the full video watched.
    """
    return StoryboardService(Settings.from_env()).samples(request)


@tool()
def storyboard_review(request: StoryReview) -> OperationResult:
    """Record an immutable caller-attested frame review with severity/evidence/correction and optional parent recheck.

    Call only after actually viewing the identified images. Sampled frames cannot certify audio or full playback.
    """
    return StoryboardService(Settings.from_env()).review(request)


@tool()
def queue_inspect(request: QueueInspect) -> OperationResult:
    """Inspect durable render claims, process owners, quarantine, bridge/manual bootstrap and disk. Never starts AE."""
    return RecoveryService(Settings.from_env()).queue(request)


@tool()
def job_reconcile(request: JobReconcile) -> OperationResult:
    """Classify a persisted job after interruption without replay or promotion.

    Default inspect authenticates late native evidence and retains all quarantines.
    release_unstarted requires the inspected journal hash, a confirmed exited owner
    and a durable claim proving the worker never began. Releases only that queue slot.
    release_completed requires an exited owner, matching source/output hashes and
    recorded completion/cancelled-child exit with no quarantine. Never reprocesses.
    release_acknowledged_read requires the hash, exited owner, intact reviewed
    script/acknowledgement and matching idle bridge; archives then releases only
    a completed read quarantine. Never clears mutation/render quarantine, kills
    processes or promotes a lost service operation.
    """
    return RecoveryService(Settings.from_env()).reconcile(request)


@tool()
def project_dependencies(request: ProjectDependencies) -> OperationResult:
    """Report media/fonts/plugins without installing or relinking. Saved-state default.

    refresh=true performs an acknowledged read of the requested active project;
    never opens/saves projects. Plugin presence outside known native effects stays unverified.
    """
    return RecoveryService(Settings.from_env()).dependencies(request)


@tool()
def workspace_cleanup_plan(request: CleanupPlan) -> OperationResult:
    """Plan hash-pinned cleanup of old atomic JSON staging files in completed owned jobs.

    Never deletes anything. Retains all AEPs, snapshots, evidence, logs, media,
    renders and uncertain outputs. No cleanup-apply tool is exposed.
    """
    return RecoveryService(Settings.from_env()).cleanup(request)


@tool()
def layers_create(request: LayersCreate) -> OperationResult:
    """Create 1–20 native text/shape/solid layers with exact fonts/style in ONE new verified version.

    Requires saved base hash, rejects dirty state/media import and duplicate roles.
    Preserves all non-target state and the source snapshot. Native order follows
    sequential add operations (last item is topmost). Overflow/font failure never
    promotes. Compact responses include bounded role/UUID mapping; its immutable
    evidence is also queryable with operation_query(section=created_layers).
    """
    return LayerBatchService(Settings.from_env()).create(request)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from astra_video_studio.host_runtime import runtime_identity
    runtime_identity()  # Freeze source identity before accepting any MCP requests.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
