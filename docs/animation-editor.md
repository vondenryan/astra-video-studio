# Guarded animation editing — Sprint 8

Host responses now default to the [Stint 9.1 compact contract](compact-responses.md). Query selected transforms for track hashes and explicit key/sample sections for detail, or use top-level response_mode=full for older examples requiring complete state. Internal verification and editing protections are unchanged.

Six tools extend the server to 48 MCP tools: `animation_inspect`, `keyframes_edit`, `easing_set`, `motion_path_set`, `animation_retime`, `motion_blur_set`. The new `anticipate_settle` skill also works through the existing motion/batch/stagger interfaces. Legacy motion tools still refuse overlap/replacement; this sprint adds a separate explicit editing contract.

## Workflow and guards

1. Call `animation_inspect` with project/composition IDs, optional layer_ids and sample_times.
2. Read `data.animation_state.base_sha256`, the composition hash and the target track hashes/data.
3. Submit a typed edit with that base hash, expected track hash, inclusive frame window, explicit mode and boundary policy.
4. Inspect the returned new AEP version and native keys/curves. Refresh hashes before the next edit.

Every edit requires the active verified saved project to be clean. A source SHA mismatch is rejected before AE inspection/mutation. Track/composition hashes detect stale requested state; a native preflight comparison catches intervening project changes. Snapshots preserve the saved source; only verified outputs advance the manifest.

Expression-bearing projects, unsupported/locked/3D targets, separated dimensions and automatic/continuous/roving transform tracks are protected. This editor handles manual 2D position, anchor, scale, rotation and opacity tracks. It does not edit source text, text animators, shape-path/mask/effect/audio keys or expressions.

## Inspection and state fingerprints

Inspection reports native values/times, interpolation, temporal ease speed/influence, spatial tangents, temporal/spatial automatic/continuous flags and roving. Optional sample_times are 0–300 seconds, up to 32 times, and must lie inside the composition. Track IDs use the existing stable layer/composition UUIDs.

`base_sha256` fingerprints the saved AEP bytes. Semantic track/composition hashes omit display-only samples and the internal world basis. They also omit temporal ease records on Linear/Hold sides: AE derives those records from the segment rather than storing them as editable controls. Native inspection still reports their actual values. Bezier speeds/influences remain part of the hash and verification.

## Key editing

All times in editing requests are integer composition frames. The inclusive source window uses `start_frame`, `end_frame`, with positive duration. `keyframes_edit.mode` is mandatory:

| Mode | Behavior |
| --- | --- |
| insert | Add supplied keys; refuse collisions with existing keys |
| update | Change supplied values/optional controls at existing frames; unspecified controls remain |
| remove | Remove keys in the selected window; keep all keys outside it |
| replace | Replace the selected interval with supplied keys; keep keys outside it |
| move | Shift keys in the selected interval by nonzero shift_frames |

`keys` contains frame/value plus optional in_type/out_type, in_ease/out_ease and in_tangent/out_tangent. Values are arrays: XY for position/anchor/scale; one number for rotation/opacity. Native Z stays appropriate to the 2D property. Interpolation accepts linear/bezier/hold. At most 300 supplied keys and 900 resulting keys per track are accepted. Keys must remain inside layer/composition lifetime and at least one frame apart. Removing the last key is refused; implicit conversion to a static value is not exposed.

Example after inspecting a position track:

```json
{"request":{"project_id":"<id>","composition_id":"<id>","layer_id":"<id>","property":"position","base_sha256":"<64 hex>","expected_track_sha256":"<64 hex>","start_frame":0,"end_frame":24,"boundary_policy":"preserve_boundaries","mode":"update","keys":[{"frame":0,"value":[200,270],"out_type":"bezier","out_ease":[{"speed":400,"influence":50}]}]}}
```

## Boundary policies and curves

`boundary_policy` must be explicit:

- `preserve_boundaries`: existing keys must exist at both window endpoints and remain there with the same values. The incoming controls at the first endpoint and outgoing controls at the last endpoint remain unchanged, preserving the adjacent external segments.
- `allow_change`: permits boundary/neighbor interpolation changes implied by the requested edit or movement. Keys outside the selected source interval remain retained, but this is not a promise that all neighboring sampled values remain unchanged.

Boundary preservation protects C0 values and external controls; it does not automatically guarantee C1 velocity continuity. Independent incoming/outgoing speed and tangent controls allow deliberate shaping. No automatic smoothing or conversion of auto-Bezier tracks occurs.

`easing_set.edits` specifies existing key frames and optional side interpolation/ease. An ease is `{speed, influence}`; influence is 0.1–100, speed ±1,000,000 units/second (nonnegative for spatial speed). Spatial/scalar properties use one ease; XY scale uses two components. Providing ease controls implies Bezier unless explicitly selected; combining explicit controls with Linear/Hold is rejected.

`motion_path_set.edits` sets incoming/outgoing XY tangents, up to ±20000 px, at existing spatial keys. Values/times stay unchanged. Tangents are relative vectors, not absolute control-point coordinates. Boundary policy still applies to outside-facing tangents. Curved trajectories are verified through native tangents and sampled positions.

## Group retime

`animation_retime` accepts 1–20 distinct layer/property targets, each with its expected track hash, within one composition. Supply the source window, new_start_frame, new_duration_frames, boundary_policy, rounding (`nearest`, `floor`, `ceil`) and duration_policy (`preserve_composition`). Nearest uses half-up rounding.

Selected key times map proportionally into the destination interval. Collisions, subframe spacing and lifetime violations fail before mutation. Internal Bezier speeds scale by the actual old/new neighboring segment durations after rounding; spatial tangents and values remain unchanged. Outside-facing controls remain copied. The composition and layer durations are not extended or moved silently. Effects/text/path animation is not part of this transform retime.

## Motion blur and composed skill

`motion_blur_set` requires the base AEP hash and expected composition hash, explicit layer IDs and both composition/layer enable switches. Shutter angle: 0–720°, phase: −360–360°, samples per frame: 2–64, adaptive limit: 16–256. The save/reopen check verifies actual engine values and unchanged unrelated layers.

`anticipate_settle` uses native position keys for entry offset → anticipation farther from the destination → overshoot → settlement. It inherits slide direction/distance/easing/blur parameters and adds anticipation_ratio (0–0.25, default 0.08). It needs at least ten frames. Combined with stagger intervals shorter than the motion duration, it creates overlapping element entries. Existing track overlap remains protected in motion_apply/motion_batch.

## Versioning, native failure and limits

The native template writes only a new AEP. Manual tracks are rebuilt with explicit values, interpolation, ease and spatial controls, while retaining the verified semantics of keys outside scope. Automatic/continuous/roving input is refused because reconstruction could recalculate neighboring handles.

A known synchronous animation error preserves the job-owned output and restores the source checked clean immediately before mutation. Verification failure does not promote its file. Unknown execution/timeouts keep quarantine and must not trigger retries or termination of interactive AE.

Sampled before/after frames and full file decode support acceptance; they do not replace complete playback or artistic approval. Preview duration/audio limits remain unchanged.

Non-target verification concerns inspected saved metadata. Editing a parent/null can intentionally change dependent layers' appearance through existing relationships; this is not a universal pixel-isolation guarantee. The acceptance fixture uses an independent sentinel and compares an exit frame separately.

Preview completion now observes uncaught Future errors, keeps a failure-only fallback record, releases slots even if terminal journal writing fails, and retries atomic JSON replacement only for bounded PermissionError cases. A failed worker status does not clear native pending markers or authorize a retry. Persistent restart/resume and general orphan recovery remain future work. The earlier orphan was reviewed manually and never promoted as success.

API references: [Property keyframe/curve APIs](https://ae-scripting.docsforadobe.dev/property/property/), [composition motion blur](https://ae-scripting.docsforadobe.dev/item/compitem/). Actual AE 25.5 tests determine acceptance.
