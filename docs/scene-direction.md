# Scene direction and revision — Sprint 5

The local Director implements the final MVP acceptance: a 10–15 second brief becomes a structured plan, an editable AEP, a fully decoded silent MP4 and a precise revision in Portuguese. It uses a deterministic native scene template. Codex interprets richer creative requests into typed fields; the backend does not call a language model or generate raster video.

For property-level changes that preserve compatible captured manual edits, use the separate [Sprint 9 revision workflow](revisions.md). The historical `scene_revise` + `scene_execute` route below rebuilds the clean owned scene; it is not the property-patch route.

## Persistent MCP workflow

1. Confirm `studio_status` and the idle bridge are ready. Keep the MCP host alive through rendering.
2. Call `scene_plan` with `request`, for example:

```json
{"request":{"brief":"Crie um motion de 12 segundos com o título \"ASTRA VIDEO STUDIO\", entrada suave e encerramento elegante.","width":1280,"height":720,"fps":24}}
```

3. Inspect the returned `ScenePlan`: elements, stable IDs, actions, phases, assumptions and techniques. The plan and its SHA-256 are stored under `workspace/plans/<plan_id>/`.
4. Call `scene_execute` with `plan_id`. It builds native layers, applies a verified motion batch and returns a rendering execution. Poll `scene_status` with `execution_id` until `succeeded` or `failed`.
5. Read `data.preview`: MP4 path, SHA-256, frame count, duration, dimensions and samples. Open actual samples before writing observations. Full decode verifies file integrity; it does not assess aesthetics or rhythm.
6. Call `scene_revise`:

```json
{"request":{"plan_id":"<previous-plan-id>","instruction":"Troque o título para \"ASTRA EM AÇÃO\" e reduza overshoot para 3%."}}
```

7. Execute the new plan and poll again. The same project ID gets new AEP versions; the original remains byte-identical. Plans cannot be executed twice. Revisions require a successful parent preview and unchanged current scene.

## Supported inputs and scene

`SceneBrief` accepts `brief`, optional `title`, `subtitle`, `closing`, `duration`, `width`, `height`, `fps`, RGB `accent`, `entry_duration` and `overshoot`. Defaults: 12 seconds, 1920×1080, 30 fps, cyan/navy, 0.9 second entrance and 5% overshoot. Explicit quoted titles and numeric seconds can be extracted from the brief. Explicit durations outside 10–15 seconds are rejected. Timings are quantized to composition frames.

The scene has nine editable layers: background, ambient circle, two accents, kicker, title, subtitle, closing and signature. It combines slide, scale, fade, mask reveal, staggered entries, parallax and a subtle shake, with entrance/hold/closing phases. Text style is explicitly reset so AE's prior All Caps setting cannot alter new text.

The bounded Portuguese revision parser handles quoted title/subtitle, explicit overshoot percentage, duration in seconds and slower entrance. Unknown or partly unparsed changes fail rather than silently disappear. For richer language, the host supplies `SceneRevision.changes`: typed title/subtitle/closing/duration/entry_duration/overshoot/accent. This is a template-based MVP, not unrestricted automatic art direction.

A revision rebuilds the Director's owned one-composition scene into a new file. External edits, changed hashes, different current versions and unsaved changes are refused. Preserve and inspect manual work before making a separate plan; revisions do not merge arbitrary manual edits.

## Layers, imports and references

`layer_create` adds typed text, shape (rectangle/ellipse), solid or imported-media layers in a new verified version. `media_import` accepts approved local media, copies it into workspace assets and returns an `asset_id` for media layers. Imports use the existing workspace/`ASTRA_IMPORT_ROOTS` boundary, supported suffixes and a 2 GB limit. Original media is never overwritten.

`reference_analyze` accepts `request.source_path` and optional `sample_times` (1–8 times). It returns technical metadata and sampled PNGs for approved local images/videos. It explicitly reports `visual_analysis_performed=false`. It does not infer style, shots or semantic similarity. Codex or an operator must actually view the samples.

`visual_review` accepts `execution_id`, `inspected_samples` (indices 0–2 of the preview samples), `notes`, `assessment` (`acceptable_samples` or `needs_revision`), `reviewer` and optional `reference_ids`. References must match the video SHA-256. Review evidence records `scope=sampled_frames_only` and `full_video_watched=false`. Functional verification, sampled appearance and full-playback rhythm remain distinct checklist items.

## CLI and limits

CLI commands mirror the tools: `plan-scene`, `execute-scene --plan-id`, `scene-status --job-id`, `revise-scene`, `review-scene`, `reference-analyze`, `layer-create`, `media-import`, `stagger-layers` and `motion-batch`. Typed payload commands use `--request` JSON. Use the persistent MCP server for asynchronous rendering; a short-lived CLI process does not provide a durable background worker.

Previews remain silent and bounded by the Sprint 4 renderer. Human playback is required to assess rhythm and final artistic approval. Audio synchronization, arbitrary scene synthesis, camera automation, plugin/media recovery, semantic video analysis and an application panel remain future work. No paid dependency is introduced.
