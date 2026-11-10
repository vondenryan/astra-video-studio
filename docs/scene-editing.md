# Scene editing — Sprint 6

The scene tools edit the active, clean, verified project in a new AEP version. They reuse the existing idle bridge, source-hash checks, snapshots and save/reopen verification. No original AEP is overwritten. Public inputs are typed JSON; no JSX or shell execution is exposed.

## Tools and requests

All operations require `request.project_id`. Existing composition/layer targets use stable 32-character UUIDs without the `astra:` prefix. Creation responses include `data.created_composition_id` and/or `data.created_layer_id`.

| Tool | Main request fields | Behavior |
| --- | --- | --- |
| `composition_create` | name, width, height, fps, duration, background | Adds an empty composition inside the current project |
| `composition_update` | composition_id; optional name/width/height/fps/duration/background; fps_policy | Updates only requested settings; no automatic layout scaling |
| `precompose_layers` | composition_id, layer_ids, name | Moves contiguous layers with all attributes into a new precomp |
| `composition_layer_add` | composition_id, source_composition_id, name, start_frame | Inserts an existing composition as a layer, trimmed to the destination duration |
| `null_create` | composition_id, name | Adds a native 2D null controller |
| `layer_duplicate` | composition_id, layer_id, name | Duplicates a layer with a fresh UUID, preserving the original identity |
| `layer_update` | composition_id, layer_id; optional name, before_layer_id/after_layer_id, timing, blend_mode, enabled | Renames/reorders, changes visibility/blend or static frame timing |
| `layer_remove` | composition_id, layer_id | Removes only if no unresolved parent/matte dependents exist |
| `layer_parent` | composition_id, layer_id, optional parent_layer_id, policy | Sets/clears parenting; rejects cycles |
| `track_matte_set` | composition_id, layer_id, matte_layer_id, mode | Assigns/removes a native AE23+ matte without changing layer order or matte visibility |

CLI commands use the same names with hyphens and `--request` JSON, for example `composition-create` or `layer-parent`.

## Composition policies

Creation defaults to 1920×1080, 30 fps and 5 seconds. Limits are 64–7680 px width, 64–4320 px height, 1–120 fps and 0.1–300 seconds. Background is RGB in [0,1]. AE persists composition backgrounds in 8-bit steps; verification compares against the quantized value. This setting does not add a visible background shape or solid.

Changing FPS requires `fps_policy`:

- `preserve_seconds`: layer/key times remain in seconds; composition duration is unchanged unless explicitly supplied.
- `preserve_frames`: duration and static layer start/in/out times scale by old_fps/new_fps. Explicit duration is not accepted simultaneously. This mode refuses keyed/expression properties, locked/unsupported targets, nested comps and moving/audio footage. It does not implement general animation retiming.

Duration changes cannot trim existing layer lifetimes. A composition used by another composition cannot be shortened or frame-retimed in this sprint. First review/edit the dependency deliberately. Resizing does not move or scale the contents.

Example:

```json
{"request":{"project_id":"<id>","composition_id":"<id>","fps":30,"fps_policy":"preserve_seconds"}}
```

## Layer timing, order and dependencies

Timing fields are integer frames in the destination composition: `start_frame`, `in_frame`, `out_frame`; alternatively `shift_frames` shifts all three by the same amount. A changed start without explicit in/out shifts the lifetime by the same amount. Times must produce a nonempty interval inside the composition. Negative source start is allowed within schema bounds. These timing operations require static properties; existing animation is protected for the future animation-editor sprint.

Choose at most one of `before_layer_id`/`after_layer_id`. Blend modes are the tested allowlist `normal`, `multiply`, `screen`, `add`.

Precompose uses `moveAllAttributes=true`, preserves original comments and stable layer IDs, and creates distinct composition/layer IDs for the new wrapper. Selection must be contiguous and include both ends of any parent/matte relation that crosses its boundary. Source references, relation IDs, property summaries, layer settings and retained composition metadata are verified after reopening. This is metadata/structure verification, not a universal pixel-equivalence claim for every external plugin or compositing arrangement.

Dependency validation rejects cycles in composition references, parenting and matte chains. Removal reports dependent layer IDs and refuses to detach them silently. Scene edits are refused while project expressions exist, including disabled stored expressions, because they can refer to names, indices or timing outside the chosen layer. Existing inspection and other protected operations remain available.

## Parenting and mattes

`layer_parent.policy` is mandatory:

- `preserve_local`: native setParentWithJump with an explicit layer/null; verifies local transform data remains unchanged. Appearance can move.
- `preserve_world`: native compensation; requires static supported 2D ancestry with no auto orientation. Verifies the world-space origin and two basis points at time zero, as well as the requested relation. Unsupported compensation is a verification failure, not a silent approximation.

Matte modes are `alpha`, `alpha_inverted`, `luma`, `luma_inverted`, `none`. Non-none modes require another layer in the same comp. `none` requires no matte ID. Visibility of the matte is restored to its prior value after native assignment, so the caller controls whether that layer is also visible. Matte API availability is inspected on the actual target.

## Verification and failure behavior

The inspector now reports composition background, source native ID/kind, moving-source flag, null status, blend/matte state, matte API availability, auto-orientation status and recursive counts of keyed properties/stored expressions. Internal scene preflight additionally samples a 2D world basis. General inspections return null for that internal field to avoid treating derived child positions as independent edits.

Before mutation, the native template compares the current inspected state with preflight data to catch intervening edits. After save/reopen, Python validates the dependency graph and requested changes, then compares all retained inspected metadata. Floating point checks use a small numeric tolerance; identity and relation checks remain exact. Existing motion verification also checks the new animation counts.

Failed outputs and journals are retained, and the project manifest stays on the last verified version. A failed-version AEP left open is not automatically promoted or treated as a known clean version. Recovery must inspect/preserve that artifact and restore a known managed state. Timeouts retain the existing quarantine and must not be blindly retried.

This sprint does not add cameras, 3D, arbitrary animation retiming, expression editing, typography/vector controls from Sprint 7, or longer previews. The 20-second master can be inspected/edited and previewed in bounded excerpts with the existing renderer.

API references used during implementation: [AVLayer matte APIs](https://ae-scripting.docsforadobe.dev/layer/avlayer/), [Layer parenting](https://ae-scripting.docsforadobe.dev/layer/layer/), [LayerCollection precompose](https://ae-scripting.docsforadobe.dev/layer/layercollection/). Native tests on AE 25.5 are the acceptance evidence; documentation alone does not establish support.
