# Astra Video Studio

**Sprint 13 — recuperação:** quatro ferramentas novas,76 no total, para fila persistente entre processos, reconciliação sem reenvio, dependências e plano de limpeza sem exclusão. Consultas nativas confirmadas podem liberar sua própria quarentena com guardas explícitas; mutações e renders incertos permanecem protegidos. Veja [persistência e recuperação](docs/recovery.md).

**Sprint 12 — Director V2:** storyboard tipado com três a seis cenas, famílias hero/split/editorial, tokens, leitura/contraste, áudio fixado, amostras por fase e revisões pontuais em português com orçamento compartilhado. Sete ferramentas novas;72 no total. Veja [contratos e limites do storyboard](docs/storyboard-director.md). A avaliação humana de reprodução, audição e qualidade artística é separada do aceite técnico.

Standalone production evidence (2026-11-07): an operator-supplied AEP received a new stereo SFX layer with 30 cue markers through direct After Effects scripting, saved/reopened as a separate AEP. This commission used no Astra service/bridge and adds no product audio API. See the separate SFX evidence in `docs/test-report.md`.

Production note (2026-11-07): the Team Aureon commission has a verified editable native project, but its separate `aerender` attempt timed out before producing frames. `workspace/preview-pending.json` is retained. The delivery uses independent local graphic composition and an original synthesized score; this is not additional native-render acceptance. See the production evidence in `docs/test-report.md`.

Local Python MCP tools for editable motion graphics in Adobe After Effects 2025 on Windows 11. **Sprints 0–13 are implemented:** safe project copies, versioned motion/effects, validated silent MP4 previews, scene planning, property revisions with manual collaboration, multi-composition editing, typography/vectors/layouts and guarded editing of native animation curves, versioned FFmpeg audio sidecars with verified20-second audio previews, final1080p renders, collected/reopened delivery packages, multi-scene storyboard direction with bounded iterative reviews, and persistent queue/recovery diagnostics. No paid services, API keys, or model inference are used.

**Stint 9.1 adds bounded host responses (55 tools then;65 after Sprint11).** Rich MCP/CLI results are compact by default, while complete immutable evidence and internal verification remain intact. `project_query` and `operation_query` inspect filtered state in bounded pages; keyframes/samples are explicit. Request `response_mode="full"` (CLI `--response-mode full`) for legacy full output. See [compact responses and inspection](docs/compact-responses.md).

**Stint 9.2 adds verified native result files.** AE now publishes a small acknowledgement (8 KiB bound) referencing complete job-owned evidence (16 MiB bound) by byte count and SHA-256. Native/Python identity, integrity and semantic checks precede promotion; failed/uncertain evidence remains quarantined. Real read-only AE acceptance transferred over 2 MB without changing the active project. Legacy inline mode is explicit. See [native transport contracts and limits](docs/native-result-transport.md). Audio is now delivered through [Sprint10 post-production sidecars](docs/audio-tools.md).

Sprint 5 delivers a local Director: a 10–15 second brief becomes an inspectable plan, nine editable native layers, keyframes and a verified preview. `scene_revise` creates a new plan/version while preserving the earlier AEP. See [scene direction and revision](docs/scene-direction.md) for the complete workflow, supported language and review limits.

## Stint 9.3 — host response diagnosis (2026-11-08)

[Stint9.3](docs/host-response-acceptance.md) adds process/source identity to studio_status and rich response metadata, counts metadata within compact budgets, aligns output-schema defaults with compact, and fixes Windows extended-path comparison during concurrent evidence publication. The three reviewed tool routes were exercised through real stdio MCP with explicit service fixtures:3/5/40/80 layers, omitted/compact/full modes; compact results were1,885–1,901 bytes. Complete evidence and legacy full payloads remain intact. Regression:370 passed,13 skipped;360 concurrent fixture publications passed after the fix. No AE native tests, scripts or renders were run.

The operator identified Claude Desktop, reported policy9.3 and confirmed an80-layer fixture query returned only three summaries with next_offset3 and no full transform/key/sample arrays. Final acceptance of the three editing routes in that affected host is still pending; the operator report is not a wire-byte measurement. Local SDK tests are not a reproduction of the external session or proof of its cause. See the [external review](docs/claude-response-review.md) and [roadmap](ASTRA_VIDEO_STUDIO_PRO_ROADMAP.md). EffectCraft is deferred by operator direction; Sprints10–11 are now delivered and Sprints12–13 remain planned; [the assessment](docs/effectcraft/README.md) does not implement or authorize replacing AE.

## Sprint 10 — audio and synchronization

Six new typed tools provide imported audio inspection, trimmed/gained/faded clips, source cues, timeline sidecar markers, guarded sync plans and audio_preview_render. Audio plans are immutable and bound to the verified saved AEP hash; they do not embed sound or markers into AE. Mix/encode uses FFmpeg, with exact PCM samples, peak rejection, AAC stream checks and full video/audio decode. Existing silent preview limits remain; the separate audio preview supports<=20s/900frames.

Regression: **384 passed,14 skipped**; separate opt-in native acceptance: **1 passed**. A real new AE composition rendered20s/640×360/24fps (480frames), with a bed/two SFX/fades and measured cue errors0frames against two saved native keys. All1,138 checked preexisting managed AEPs retained their hashes. The new test AEP remains open. Three extracted frames were viewed; human playback/listening/artistic approval were not performed. See [contracts, workflow and evidence](docs/audio-tools.md). Reload an idle MCP connection to see the current65 tools; no automatic app configuration changes or new AE bootstrap are required by the code update.

## Sprint 11 — final renders and delivery packages

Four new tools (65 total) discover final presets, submit bounded final renders, collect editable AEP/media/audio/output and validate the package. Distribution is H.264/AAC; intermediate is native8-bit RGBA TIFF, copied byte-for-byte with recorded alpha association. Existing15s/20s previews keep their limits. Final requests declare resolution/FPS/color/source hash and a fresh workspace destination. No implicit FPS retiming, HDR conversion or global color changes.

Regression: **412 passed,15 skipped**; targeted native acceptance: **1 passed** plus final-code read-only revalidation. Real acceptance produced **30s/1920×1080/24fps (720frames)** with audio, verified native TIFF alpha and a9-file package whose AEP was relinked/reopened in AE. Validation checked links/fonts/file hashes, complete A/V decode and a bit-identical PCM rebuild from collected audio. Fonts/plugins are listed, not copied.1,150 preexisting managed AEPs remained byte-identical. Sampled frames were viewed; human playback/listening/artistic approval remain separate. See [final-render/delivery contracts and evidence](docs/final-delivery.md). EffectCraft remains deferred and9.3 external editing-route acceptance is not closed by this sprint.

## Quick start (PowerShell)

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e '.[dev]'
.\.venv\Scripts\astra-studio.exe status
.\.venv\Scripts\python.exe -m pytest -q
```

Python 3.11+ is required. The verified local environment uses Python 3.14.0. Configuration is via environment variables; `.env.example` documents them but is not loaded automatically. The default workspace is `workspace` beneath the current directory. `status` creates that directory and writes/deletes one temporary permission probe; it never launches AE.

## MCP host configuration

Configure a local **stdio** server using the following host-neutral fields. No app settings are automatically modified.

```json
{
  "command": "C:\\Users\\ryanb\\Documents\\Codex\\AstraVideoStudio\\.venv\\Scripts\\python.exe",
  "args": ["-m", "astra_video_studio.mcp_server"],
  "env": {
    "ASTRA_WORKSPACE": "C:\\Users\\ryanb\\Documents\\Codex\\AstraVideoStudio\\workspace"
  }
}
```

Tools: `studio_status`, `project_create`, `composition_inspect`, `job_status`, `layer_transform`, `motion_apply`, `project_open_copy`, `project_save`. All publish typed structured output. Logs go to stderr; stdout is reserved for MCP messages. The server is not automatically registered in the Codex app.

Sprint 4 additionally exposes `effect_apply`, `mask_create`, `preview_render`, `job_cancel`. The reviewed idle-dispatch bridge replaces repeated per-operation `-r` calls. Start it once with `astra-studio bridge-start`; if startup is unconfirmed, `studio_status.bridge_runtime.bootstrap_script` identifies the generated script for manual AE execution. Manual initialization was needed on this host. After confirmation, operations reuse the local idle inbox. Do not repeatedly launch the bootstrap or bypass pending-job records. See [preview rendering and current limits](docs/preview-rendering.md).

Sprint 5 adds `layer_create`, `media_import`, `stagger_layers`, `motion_batch`, `scene_plan`, `scene_execute`, `scene_status`, `scene_revise`, `visual_review` and `reference_analyze`: **22 MCP tools total**, all with structured output. Keep the MCP server running until queued previews finish. The CLI is also available; for scene rendering use the persistent MCP workflow described in the guide.

Sprint 6 adds ten scene tools, reaching **32 MCP tools at that stage**: `composition_create`, `composition_update`, `precompose_layers`, `composition_layer_add`, `null_create`, `layer_duplicate`, `layer_update`, `layer_remove`, `layer_parent`, `track_matte_set`. Build multiple scenes/precomps, organize static timing in frames, set 2D parenting, alpha/luma mattes and four blend modes in verified new versions. FPS changes require an explicit policy. Dependencies/cycles and stored expressions are protected. See [scene editing](docs/scene-editing.md) and the [professional roadmap](ASTRA_VIDEO_STUDIO_PRO_ROADMAP.md).

Sprint 7 adds `fonts_list`, `text_style_set`, `text_animator_apply`, `shape_path_set`, `shape_style_set`, `shape_trim_apply`, `shape_morph_apply`, `vector_import`, `design_tokens_set`, `layout_apply`: **42 tools at that stage**. Use installed font identities, point/box text and style ranges, native word/character animators, Bezier shapes, Trim Paths, compatible morphs, strict-subset SVG conversion and token-based landscape/square/portrait layouts. See [design tools and limits](docs/design-tools.md). Native gradient color-stop editing is explicitly unavailable; no raster fallback is used. Audio and final-delivery packaging remain future work.

Sprint 8 adds `animation_inspect`, `keyframes_edit`, `easing_set`, `motion_path_set`, `animation_retime`, `motion_blur_set`: **48 tools at that milestone**. Edit manual 2D transform keys with explicit version/state hashes, frame windows, edit modes and boundary policies; control temporal ease, spatial tangents, grouped retime and blur sampling. The eighth motion skill, `anticipate_settle`, also works with batch/stagger. Existing motion tools still refuse replacement. See [animation editor](docs/animation-editor.md). Expressions, automatic/continuous/roving tracks and non-transform key editing remain protected.

Sprint 9 adds `revision_plan`, `revision_apply`, `version_compare`, `version_restore`, `director_revision_plan`: **53 tools at that milestone**. Preview immutable typed patches, capture compatible unsaved manual changes explicitly, identify property conflicts, retain revision history and restore a prior AEP as a new byte-identical version. Content, text style, static transforms/timing and Sprint 8 animation operations share their existing guards. The Director's bounded patch vocabulary is separate from full scene rebuilds. See [revision and manual collaboration](docs/revisions.md). Audio and final delivery remain future sprints.

## Create a real editable demo

```powershell
.\.venv\Scripts\astra-studio.exe create-demo
.\.venv\Scripts\astra-studio.exe inspect --project-id <returned-project-id>
.\.venv\Scripts\astra-studio.exe job-status --job-id <returned-operation-id>
```

The demo creates a 1920×1080, 30 fps, 5 s composition with centered `ASTRA VIDEO STUDIO` text. Each creation saves a unique `workspace/projects/<id>/project.aep`, reopens that file in AE and checks the persisted dimensions, title and transforms. The latest project stays open. The default title uses Arial Bold and automatically fits inside the composition; text remains editable.

`project_create` takes a `request` object with optional `name`, `title`, `width`, `height`, `fps`, `duration`, `font_size`. Values have explicit size/timing limits. It only replaces an empty untitled project or an **unchanged Astra-managed** project. Untracked or modified projects are refused. Save and close your other work yourself before running it. No tool overwrites original `.aep` files or discards unsaved edits.

Use one workspace per AE session. On timeout, the runner creates a cancellation marker and leaves `ae-pending.json` to block further submissions. A delayed script checks that marker before mutations; an already-running operation cannot be forcibly cancelled safely. Inspect AE and the job before manual recovery; do not blindly delete the marker or retry.

Acknowledgements are published by AE's deferred task queue after the main script returns, and the runner retains the mutex for a further 750 ms before allowing another submission. Repeated `-r` delivery still proved intermittent in Sprint 4, so new operations use the reviewed idle inbox after a single confirmed bootstrap. Avoid running scripts manually while Astra is executing; modal dialogs and other scripts can still delay or block delivery.

## Real AE integration tests (explicit opt-in)

Default pytest runs do not change AE projects. To create multiple real projects, verify round-trip/IDs/hashes, exercise the protection guard and test MCP-to-AE calls:

```powershell
$env:ASTRA_RUN_AE_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_ae_live.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_motion_ae_live.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_existing_ae_live.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_preview_ae_live.py -q
Remove-Item Env:\ASTRA_RUN_AE_TESTS
```

`studio_status.bridge_status` becomes `acknowledged` after a verified Sprint 1 creation in this workspace; that records prior evidence, not live runtime readiness. Other workspaces begin at `not_validated`.

## Sprint 2: editable motion and safe versions

`layer_transform` sets static position, anchor, scale, rotation and opacity. `motion_apply` supports `slide_in`, `scale_pop`, `fade_in_out`, `smooth_zoom`. Both target a verified **already-active Astra project** and stable composition/layer IDs. Pass the 32-character UUID after the `astra:composition:` / `astra:layer:` prefix reported by inspection. See [motion skills](docs/motion-skills.md) for schemas, defaults and timelines.

Every edit first copies the saved source to `versions/<version-id>/source-snapshot.aep`, saves edits to `versions/<version-id>/project.aep`, and reopens/inspects the version. The parent manifest advances only after verification. The base AEP and all prior versions remain unchanged. `composition_inspect` follows the latest verified version. Failed versions remain artifacts but are not promoted automatically. Do not manually edit/save a source while automation is running; changed hashes and unsaved edits are refused.

Example MCP arguments for a slide entry:

```json
{
  "request": {
    "project_id": "<32-character project ID>",
    "composition_id": "<32-character composition ID>",
    "layer_id": "<32-character layer ID>",
    "skill": "slide_in",
    "start_time": 0.3,
    "duration": 0.9,
    "params": {"direction": "left", "distance_px": 420, "overshoot": 0.06}
  }
}
```

CLI equivalents: `astra-studio motion-apply --request '<JSON request without the outer request wrapper>'` and `astra-studio layer-transform --request '<JSON request>'`. The motion engine runs locally and produces native keyframes and temporal Bézier handles, without expressions or baked video. Times snap to the nearest frame; overlapping keyed intervals, enabled expressions and static replacement of keyed properties are refused. Motion blur is enabled on both layer and composition when requested. This increment has functional metadata validation; MP4 previews and visual review are still later work.

## Sprint 3: work on an existing AEP without changing its source

Place a trusted source AEP under the configured workspace, for example `workspace/incoming/client.aep`, then:

```powershell
.\.venv\Scripts\astra-studio.exe open-copy --source 'incoming\client.aep'
.\.venv\Scripts\astra-studio.exe inspect --project-id <returned-project-id>
.\.venv\Scripts\astra-studio.exe save --project-id <returned-project-id>
```

`project_open_copy` takes `request: {"source_path": "incoming/client.aep"}`. Relative paths are workspace-relative. It creates a unique managed `project.aep` and byte-identical `original-source.aep` backup, opens only the copy, checks all three hashes and returns composition/layer IDs. Existing comments, duplicate names and locked layers are preserved. UUIDs are stored in a sidecar map to persistent native AE IDs; indexes and names are not identities.

For sources outside the workspace, the operator must explicitly configure `ASTRA_IMPORT_ROOTS` (semicolon-separated folders on Windows). Tools cannot grant themselves access or write into those roots. Example: `$env:ASTRA_IMPORT_ROOTS = 'D:\ApprovedClientProjects'`. AE itself can resolve linked media and evaluate expressions when opening a project, so use trusted sources. The copy workflow does not collect/relink media or guarantee third-party plugin availability; see [existing projects](docs/existing-projects.md).

Use `layer_transform`/`motion_apply` with returned IDs to edit the active working copy in new versions. Locked/unsupported 2D targets, separated position dimensions, expressions and protected keyed intervals are refused. Verification compares other layers and compositions as well as the target's untouched properties. Originals and previous saved versions are never overwritten.

`project_save(project_id)` explicitly captures the active managed state, including unsaved manual changes, into another unique version. It snapshots the prior disk file, saves/reopens the new AEP and checks that the inspected state survived. New manually added/duplicated layers receive new IDs while existing UUIDs remain attached to their native IDs, even after reordering. It does not switch to another project or save arbitrary paths. Other edit tools continue to refuse unsaved changes; use this explicit save operation first.

## Sprint 4: native treatments and a rendered preview

`effect_apply` appends allowlisted `fill` or `gaussian_blur` effects. `mask_create` appends editable static rectangle/ellipse masks in layer coordinates, with feather, opacity, add/subtract and inversion. Both preserve snapshots and earlier treatments in new verified AEP versions.

`preview_render` takes project/composition IDs plus a start/duration and maximum width. It returns a queued `job_id`; poll `job_status` with that ID as `operation_id`. The worker prepares a disposable AEP/queue, restores the prior saved interactive project, renders lossless frames with a separate `aerender`, and encodes a silent H.264 MP4. It detects the installed sequence template: this AE uses **TIFF Sequence with Alpha** because PNG Sequence is absent. Validation requires the expected frame count, duration, dimensions, FPS and full MP4 decode, then extracts three sample PNGs. A path or exit code alone is not success.

`job_cancel` requests cancellation of preview jobs. Queued work stops before dispatch; active native rendering is allowed to finish or reach its timeout before later stages are skipped. A persistent `preview-pending.json` is written before starting the renderer and cleared only after confirmed exit. Unknown/interrupted native renders block another preview until reviewed. Keep the MCP host alive for its preview worker; journals are durable but interrupted jobs are not automatically replayed. See the [test report](docs/test-report.md) for actual acceptance evidence and limits.

See [Windows installation and controlled bridge test](docs/installation-windows.md), [architecture](docs/architecture.md), [decisions](docs/decisions.md), [tool contracts](docs/tool-contracts.md), and [actual test evidence](docs/test-report.md).

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

**Aceite final em andamento:** a referência VÉRTICE de24s/1080p30 foi construída em cinco composições/29 camadas. Está pausada para a edição manual do operador; revisões, render, aprovação paisagem e adaptação vertical ainda não foram concluídos. Veja [estado do aceite final](docs/final-reference-acceptance.md).

**VÉRTICE paisagem:** render24s1080p30, duas revisões e preservação do ajuste manual passaram no aceite técnico, incluindo pacote reaberto/validado. Aprovação humana e versão vertical continuam pendentes. Estado em [aceite final](docs/final-reference-acceptance.md).

**Otimização de criação (2026-11-10):** 77 ferramentas, criação agrupada `layers_create` (1–20 camadas com tipografia em uma versão verificada), respostas opcionais `receipt` de até3KiB e leitura local de evidência por hash. No ensaio de cinco camadas: oito chamadas/37,39s → uma/4,69s, com metadados equivalentes e primeiro frame decodificado idêntico. Não é benchmark do filme inteiro. Veja [revisão e contratos](docs/creation-optimization.md), incluindo diagnóstico de SFX/curvas e limites do aceite.
