# Motion Engine — Sprints 2–8

Supported targets are 2D layers in verified Astra-created projects already active in AE. Schema definitions live in `motion_engine/schemas.py`; models reject extra fields, nonfinite numbers and invalid IDs. Every edit snapshots the saved source, saves a distinct version, reopens it and verifies the result. Keyframes and curves remain directly editable in AE.

## Motion request

`project_id`, `composition_id`, `layer_id`: 32 lowercase hex characters (strip inspection's `astra:composition:` / `astra:layer:` comment prefix). `skill`: one of the eight names below. `start_time`: 0–300 seconds, default 0. `duration`: greater than 0 and at most 300 seconds, default 2. `params`: typed per skill; unknown or mismatched fields are rejected. Fade durations must fit inside the requested window.

Time boundaries round to the nearest composition frame, with half frames rounding upward. The returned `applied_plan` records actual times, property tracks, key values and tangent speeds. An animation must remain inside the composition and target layer lifetime. Nonzero overshoot needs enough frames for the peak and two-frame settlement. Cubic ease-in-out segments need at least two frames. Requests that collapse key times fail before AE mutations.

| Skill | Parameters and defaults | Limits/behavior |
| --- | --- | --- |
| `slide_in` | `direction="left"`, `distance_px=null`, `distance_ratio=0.24`, `easing="ease_out_cubic"`, `overshoot=0.06`, `motion_blur=true` | direction left/right/up/down; explicit distance >0–10000 px; ratio >0–2 of comp width or height; overshoot 0–0.25. Uses the inspected baseline position as destination; adds an explicit peak then settles. |
| `scale_pop` | `initial_scale=70`, `final_scale=100`, `overshoot=0.08`, `easing="ease_out_cubic"`, `motion_blur=true` | initial >0–1000%, final >0–800%, overshoot 0–0.25. Uniform XY scaling with an optional peak at final × (1 + overshoot). |
| `fade_in_out` | `fade_in=0.6`, `fade_out=0.8`, `easing="ease_in_out_cubic"`, `motion_blur=false` | Fade durations >0–60 s each. Total fade intervals must fit in request duration without overlap. Opacity 0→100, hold, 100→0. |
| `smooth_zoom` | `initial_scale=100`, `final_scale=110`, `easing="ease_in_out_cubic"`, `motion_blur=true` | Both scales >0–1000%. Uniform XY scaling. Use the static anchor transform to establish the zoom center before adding animation. |
| `text_reveal` | `direction="left"`, `padding_px=8`, `easing="ease_in_out_cubic"`, `motion_blur=false` | Native animated mask fitted to inspected text bounds; four directions, padding 0–100 px. Sampled cubic progress with linear path interpolation between native keys. |
| `shake` | `amplitude_px=6`, `frequency_hz=4`, `decay=3`, `seed=0`, `motion_blur=true` | Seeded position keys; amplitude >0–100 px, frequency 0.5–12 Hz, decay 0–10, at most 900 keys. Starts/ends at baseline. |
| `parallax_2d` | `depth=0.5`, `displacement=[0.04,0]`, `easing="ease_in_out_cubic"`, `motion_blur=true` | Position displacement relative to composition size × depth. Depth >0–2; displacement components ±1. No 3D camera. |
| `anticipate_settle` | Slide parameters plus `anticipation_ratio=0.08` | Entry offset → farther anticipation → overshoot → settlement, using native position keys. Anticipation ratio 0–0.25, at least ten frames; compatible with batch/stagger for overlapping element entries. |

`stagger_layers` expands up to 20 unique layer IDs into validated motions with an interval, forward/reverse order and a base skill. `motion_batch` accepts up to 40 motions for one project, compiles all before mutation, rejects track collisions and verifies one saved version. Appended position motions use the preceding held position. Existing keys, expressions and unrelated layers remain protected.

`easing` accepts `linear`, `ease_in_cubic`, `ease_out_cubic`, `ease_in_out_cubic`. Cubic endpoint slopes compile to `KeyframeEase` velocities with 33⅓% temporal influence. Ease-in-out uses two cubic segments; for odd frame counts, the split value follows elapsed time to keep velocity continuous across the quantized midpoint. This is frame-aware cubic easing, not a claim that a quantized midpoint exactly matches an arbitrary continuous-time reference curve. Position uses one spatial speed and straight spatial tangents; scale/opacity use independent temporal component velocities. Spatial speeds are nonnegative; nonspatial component speeds preserve sign. No expression is installed.

Motion blur `true` enables the layer and composition switches and sets a 180° shutter. `false` does not disable blur previously enabled by another operation. A new track may be appended before/after an existing keyed span, preserving previous keys; touching or overlapping its span is rejected. Automatic replacement of earlier animation is deliberately unsupported.

Sprint 8's separate [animation editor](animation-editor.md) supports explicit guarded replacement/curve edits and blur settings. These APIs require saved-version/state hashes and declared scope/policies; they do not weaken the legacy motion_apply/motion_batch overlap guards.

## Static transform request

Use the same target IDs plus `values`, containing at least one of: `position: [x,y]`, `anchor: [x,y]`, `scale: [xPercent,yPercent]`, `rotation: degrees`, `opacity: percent`. Coordinates are limited to ±100000 px; scale >0–1000%; rotation ±36000°; opacity 0–100%. Three-dimensional targets are refused. Enabled expressions and any existing keys on touched properties are protected. Set an anchor deliberately: changing it changes the visual pivot without automatic position compensation.

## Verified 10-second example

The live MCP test creates a new 1920×1080/30 fps/10 s project and applies:

1. Static centered position/anchor, 100% scale, 0° rotation, 100% opacity in a new version.
2. Slide from the left by 420 px, 0.3–1.2 s, 6% overshoot.
3. Scale pop 82→106→100%, 0.3–1.2 s, on a separate property.
4. Fade across 0–10 s: 0.6 s entry, hold until 9 s, 1 s exit.
5. Smooth zoom 100→108%, 2–8 s, after the scale-pop interval.

The test checks disk round-trips, all previous AEP hashes, source snapshots, native keys/interpolation/ease data, blur switches, opacity hold/exit and rejection of overlapping/keyed replacement requests. Rendering/visual QA and arbitrary existing-project editing are later sprints.

AE API references: [Property](https://ae-scripting.docsforadobe.dev/property/property/), [KeyframeEase](https://ae-scripting.docsforadobe.dev/other/keyframeease/), [CompItem](https://ae-scripting.docsforadobe.dev/item/compitem/). Actual 25.5 execution, not documentation alone, is the acceptance evidence recorded in `test-report.md`.
