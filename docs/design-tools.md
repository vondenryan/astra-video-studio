# Typography, vectors and identity — Sprint 7

Ten tools extend the local server to 42 MCP tools. They use controlled native templates, typed JSON, source snapshots, immutable AEP versions and save/reopen verification. No new dependency, paid service or raster conversion is introduced.

## Tools

| Tool | Main input | Result |
| --- | --- | --- |
| `fonts_list` | request.query, limit, optional include_locations/include_project_context | Available AE fonts with PostScript names, IDs and capabilities. File locations and project context are explicitly requested. |
| `text_style_set` | target IDs, optional font/font_size/tracking/fill/leading/alignment/box_size/ranges | Verified typography and optional character-range styles |
| `text_animator_apply` | target IDs, based_on, position, scale, opacity, start_time, duration | Appended native word/character entry with range-selector keys |
| `shape_path_set` | target IDs, path, optional group_id/name | New managed Bezier group or replacement of its static geometry |
| `shape_style_set` | target/group IDs, fill/stroke/enabled/opacity/width | Solid paint controls; unsupported gradient requests fail explicitly |
| `shape_trim_apply` | target/group IDs, start_time/duration, start_percent/end_percent/offset | Appended native Trim Paths and editable linear end keys |
| `shape_morph_apply` | target/group IDs, end_path, start_time/duration | Linear native morph of compatible static paths |
| `vector_import` | target shape IDs, approved source_path, scale | Copied strict-subset SVG and editable native shape groups |
| `design_tokens_set` | name, colors, typography, spacing_ratio, safe_area | Immutable local token record with SHA-256; no AE edit |
| `layout_apply` | project/composition IDs, token_id, profile, bindings, arrangement | New landscape/square/portrait version with fit/reflow and bounds checks |

CLI names use hyphens and `--request` JSON. Use a persistent MCP host for queued previews. All mutation responses are OperationResult; tokens return TokenRecord. Failed native execution or verification never promotes a version.

## Fonts and text

Call `fonts_list` first. Font selection is `{ "postscript_name": "Arial-BoldMT", "font_id": 6 }`, using IDs actually returned on the current AE session. The example ID is not portable. `font_id` is optional for a unique PostScript name; use it to disambiguate duplicates. A stored token with a session-specific ID can require a new token record after AE restarts. Missing, substitute or ambiguous fonts are refused before mutation rather than assigned by an unchecked string. Glyph coverage/fallback for every writing system is not guaranteed by font availability alone.

Set `include_locations=true` to obtain each font's native `location` when available, otherwise null. This identifies the file to verify independently. A location alone establishes no byte hash. Set `include_project_context=true` to include the active saved path, dirty flag and item count. Both flags default to false. These opt-in fields support coordinated lossless-reference capture without adding a new tool or changing a project.

`text_style_set` supports font size 8–500 px, tracking −100–500, RGB fill in [0,1], explicit leading 1–1000 and left/center/right alignment. Requested font sizes are normalized to **0.01 px**, consistently in native assignment and verification. This avoids AE retaining an old value for a very small requested size change.

By default a text style edit recenters a static anchor on the mid-composition bounds. Set `recenter_anchor=false` to keep the existing pivot. Other transforms are preserved. Animated source documents, stored project expressions and truncated style inspection are protected.

Create paragraph text through the existing `layer_create` request:

```json
{"request":{"project_id":"<id>","composition_id":"<id>","layer":{"kind":"text","name":"Subtitle","text":"Identidade em movimento.\nDireção, forma e precisão.","text_box":[1200,170],"font_size":32}}}
```

Omit `text_box` to create point text. Creation does not silently fit paragraph font size. `box_size` changes an existing paragraph box; conversion between point and box layers is not exposed. AE's `boxOverflow` is inspected. Style edits reject overflow by default; `overflow_policy="report"` deliberately permits a diagnostic overflowing version. Layout always rejects box overflow.

Character `ranges` use zero-based **Unicode code-point** indices, end exclusive, up to 500 code points and 30 nonoverlapping ranges. Python converts them to the UTF-16 offsets used by AE. Font, font size, tracking and fill can vary per range. Inspection returns compact style runs and detects truncation. Paragraph leading/alignment remain layer-level controls in this interface.

```json
{"request":{"project_id":"<id>","composition_id":"<id>","layer_id":"<id>","font":{"postscript_name":"Arial-BoldMT"},"font_size":88,"ranges":[{"start":0,"end":5,"font_size":92,"fill":[0.294,0.863,1]}]}}
```

`text_animator_apply` appends an animator; it does not replace earlier ones. `based_on` is `words` or `characters`. Position is limited to ±2000 px, scale 1–400%, opacity 0–100. Range Start is keyed 0→100 so the initial offset/opacity/scale progressively stops affecting the text. XY scale follows the request; Z remains 100 in 2D. Intervals are frame-quantized and must remain inside the layer lifetime. Native keys, selector and values are inspected after reopen. This is an entry primitive, not a general text-animation editor.

## Shape groups, paths, paint and morph

Create an empty native shape layer with `layer_create.layer={"kind":"shape","shape":"empty",...}`. Add paths with `shape_path_set`. Responses expose `created_group_id`; later shape tools require that ID plus project/composition/layer IDs.

Managed vector groups have UUIDs in their names because AE properties do not expose the same persistent native identity as layers. Duplicate group names/IDs are refused. Existing ordinary rectangle/ellipse groups remain inspected and preserved, but advanced tools target their own managed single-path groups. A duplicated layer can retain group IDs because they are scoped to the layer.

`PathData` contains `vertices`, `in_tangents`, `out_tangents`, `closed`. There are 2–256 vertices, at least 3 for closed paths, matching tangent counts and coordinates within ±20000 px. Missing tangents become zero tangents. Group geometry is in local layer coordinates. Stroke width is >0–200 px; fill/stroke opacities are 0–100. Paint can be enabled/disabled explicitly.

Trim Paths adds two linear End keys over the requested frame interval. Existing Trim Paths operators are protected. Morph adds two native Shape keys to a static Bezier path; vertex count and closure must match. The caller must supply meaningful vertex ordering; there is no automatic topology matching. Existing path keys are protected. Style editing also protects animated paint.

**Gradient limitation:** this bridge does not expose a supported serialization/editing contract for native gradient color stops. The gradient request is explicitly rejected before mutation, and `fonts_list.data.capabilities.gradient_color_editing` is false. Solid fill/stroke are supported. This does not claim that AE itself cannot create gradients, and there is no silent bitmap fallback.

## SVG subset and boundaries

`vector_import` requires a nonempty UTF-8 `.svg` in the workspace or operator-configured approved roots. It reads a bounded payload once, parses and copies those exact bytes into owned assets, checks that the source did not change, then creates native Bezier geometry. Source/copy hashes are checked again after execution. The AEP contains editable paths rather than linked SVG footage. No browser or external resource loader is used.

Supported: SVG/g containers with inherited solid styles; path commands M/L/H/V/C/Q/Z in absolute/relative form; polygon, polyline, rectangle, circle and ellipse. Quadratic curves convert mathematically to cubic tangents. A positive viewBox defines coordinates; geometry is centered on it and multiplied by the requested scale. Root width/height are not used as an external viewport.

Supported paints are hex RGB, black, white or none, fill/stroke opacity, stroke width, nonzero winding, butt caps and miter joins. There is no automatic visual interpretation of unsupported SVG features.

Transforms, nested SVG viewports, arcs, shorthand curves, compound subpaths/holes, gradients, CSS outside the allowlist, scripts, event handlers, external references, image/use/foreignObject elements, alternate namespaces and DTD/entities are rejected. Title/description metadata may contain plain text only. Other vector formats such as AI/EPS are not exposed by this import tool. It does not promise arbitrary Illustrator/SVG compatibility.

Bounds: 2 MB source, 512 elements, depth 16, 32 native groups and 4096 total vertices, with individual PathData limits. Unsupported geometry fails before AE mutation. Source and copied SVG hashes are checked after successful execution.

## Tokens and responsive layouts

Tokens live under `workspace/design-tokens/<id>/`, with immutable content, SHA-256 and record. Modified content is rejected; create a new token set for revisions. Colors use named RGB values. Typography tokens select a real font, tracking, a color key and font size relative to the shorter composition dimension. Spacing and safe-area values are explicit ratios. This is a local identity system, not a font installer or global AE preference change.

Profiles are `landscape` 1920×1080, `square` 1080×1080 and `portrait` 1080×1920. Each binding specifies layer ID, normalized center x/y, max_width/max_height, optional typography token and `content`/`background` role.

```json
{"request":{"project_id":"<id>","composition_id":"<id>","token_id":"<id>","profile":"portrait","bindings":[{"layer_id":"<title-id>","x":0.5,"y":0.4,"max_width":0.8,"max_height":0.15}]}}
```

Bind every enabled visual layer; omit disabled layers and nulls. Bindings require supported unparented 2D targets, zero rotation and static, unseparated position/anchor/scale/rotation. Existing text animators, Trim Paths and morphs may remain editable because layout does not replace their keys.

Layout fits content with a positive uniform scale, centers the anchor, repositions in composition-relative coordinates, and reflows paragraph boxes. It may apply explicitly selected typography tokens; without one, character styles are preserved. Text is not automatically shrunk until it fits a box: overflow is an error. Backgrounds scale to cover the frame and may extend beyond it.

`arrangement` supports `bindings`, `align_left`, `align_center`, `align_right`, `distribute_horizontal` and `distribute_vertical`. Distribution follows binding order, uses rendered bounds and enforces minimum token spacing. Safe area uses [left,top,right,bottom] fractions. Native checks and Python verification compare the mid-composition local bounds and requested placement/spacing.

These checks are bounded layout verification, not proof of collision-free motion at every frame. Full temporal review, arbitrary parented/rotated layouts, automatic art direction and replacement of existing transform animation remain outside Sprint 7.

## Failure behavior and evidence

Each mutation compares the saved state with preflight, writes only a new AEP, reopens it and verifies edited content plus retained inspected metadata. A known synchronous native design error preserves the job-owned output and restores the source that was checked clean immediately before mutation. A post-reopen verification failure retains the existing unpromoted-file protection. Unknown execution/timeouts keep quarantine; there is no retry or termination of interactive AE.

The inspector includes text style runs/overflow, native text animators, shape geometry/paint/Trim Paths/morph keys and local bounds. It verifies the controlled subset, not every possible client plugin or text attribute. Review frames must actually be viewed before recording observations.

API references: [FontsObject](https://ae-scripting.docsforadobe.dev/text/fontsobject/), [TextDocument](https://ae-scripting.docsforadobe.dev/text/textdocument/), [CharacterRange](https://ae-scripting.docsforadobe.dev/text/characterrange/), [text match names](https://ae-scripting.docsforadobe.dev/matchnames/layer/textlayer/), [shape match names](https://ae-scripting.docsforadobe.dev/matchnames/layer/shapelayer/). Acceptance is based on actual AE 25.5 execution, not documentation alone.
