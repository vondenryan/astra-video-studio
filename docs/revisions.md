# Sprint 9 — property revisions and manual collaboration

Host responses now default to the [Stint 9.1 compact contract](compact-responses.md). Use filtered queries for state/detail or explicit top-level response_mode=full when an older client requires complete payloads. Internal revision verification and immutable plans remain full.

Five tools extend the local stdio MCP to 53 tools: `revision_plan`, `revision_apply`, `version_compare`, `version_restore`, `director_revision_plan`. These tools never expose arbitrary JSX or shell execution.

## Workflow

1. Inspect the active verified managed project. Use its current AEP SHA-256 as `base_sha256`. Explicitly `project_save` any existing unsaved edits before planning.
2. `revision_plan` takes `project_id`, `base_sha256`, an `instruction` for history, and 1–8 discriminated typed `operations`. It inspects the project, preflights the entire patch and stores a new immutable `workspace/revisions/<UUID>/plan.json`. It returns `revision_id`, `plan_sha256`, target paths, expected property fingerprints and preservation policy. Planning does not change the AEP.
3. `revision_apply` takes `revision_id`, `plan_sha256`, `expected_current_sha256` and explicit `capture_manual` (default false). The current disk version must still match its verified record. A newer verified version may be used if the patch's property/dependency fingerprints still match. Unrelated changes are retained.
4. Compatible unsaved changes made after planning require `capture_manual=true`, or a separate `project_save`. Capture saves/reopens a new version first. Changed patch properties return `blocked` with identifiable paths and expected/actual hashes, before capture or mutation. Nothing is resolved by silent overwriting.
5. The patch executes in one native undo group against a new AEP. Each intermediate inspected state is verified with the contracts below; the saved/reopened result is compared to the final step. Only complete successful verification promotes the current manifest. A failed or uncertain attempt is retained and cannot be submitted again. Create a fresh plan after resolving its outcome.

The instruction string in `revision_plan` is a history label; it is not parsed as code or unrestricted natural language. The host translates intent to the typed operations.

## Typed operations

Every operation has `{ "action": "...", "request": { ... } }`; request identities must all match the outer project. Existing schemas remain closed.

| Action | Scope and protections |
| --- | --- |
| `content_set` | `project_id`, `composition_id`, `layer_id`, `text` (1–500 Unicode code points). Static, nonempty, one-paragraph text, installed font, uniform inspected character styles, no text animators. Replaces document text while preserving its current character style and anchor; no automatic recentering. Rejects mixed styles, source-text animation, expressions and box overflow. |
| `text_style_set` | Sprint 7 schema and verifier, including installed font resolution, code-point ranges, optional recentering and overflow policy. The text/style document is guarded as one native write unit; unrelated layout is retained. |
| `layer_transform` | Existing static 2D transform schema. Individual selected transform tracks are guarded. Keys, separation and expressions cannot be replaced. |
| `layer_update` | Sprint 6 timing-only subset (`start_frame`, `in_frame`, `out_frame`, `shift_frames`); static-layer restrictions remain. Reorder/rename/visibility changes are outside this patch operation. |
| `keyframes_edit`, `easing_set`, `motion_path_set`, `animation_retime` | Complete Sprint 8 request schemas, expected track state, explicit frame window/boundary policy and rounding. Manual 2D transform tracks only. Each source base hash must equal the revision base. |

Timing and animation patches are separate: a six-frame **entry** delay uses selected position keys and leaves layer lifetime unchanged. A static layer timing shift changes its lifetime under the Sprint 6 rules.

Overlapping writes to the same property are refused, even if seemingly compatible. Content and style changes to the same document require separate plans. Timing cannot be combined with other operations on that layer. Anchor recentering participates in overlap checks. Under the default [Stint 9.2 artifact transport](native-result-transport.md), conservative preflight includes complete per-step inspections and generated track growth against the separate 16 MiB file bound; it is checked again before capture/application. Explicit legacy inline mode retains its 1.2 MB estimate. Split patches that exceed the active bound. There is no general merge engine.

Property guards include stable native identity, target editability/lock/parent/lifetime and composition FPS/duration. Animation guards cover the entire selected track, not just one key. Content guards cover text; compatible manual color and anchor edits remain eligible and are checked against the captured source during verification. Stored project expressions are protected throughout.

## History and restore

`workspace/revisions/<UUID>/plan.json` is immutable and hash checked. `attempt.json` records a single application reservation, expected current hash, optional manual-capture operation and output version. `result.json` records that attempt's result; it is not reused for another attempt. Native job artifacts retain per-step inspected evidence. The version record links the revision, parent, snapshot and output hash. Earlier plans, AEPs, manual captures and failed outputs remain available.

`version_compare` accepts `project_id`, `left`, `right`: either a version UUID or `initial`. It verifies the selected saved hashes and reports paths with before/after inspected values. Derived transform samples and world-basis probes are omitted. This is a metadata comparison, not proof of binary or visual equivalence. AEP fields not exposed by inspection are not semantically compared.

`version_restore` accepts `project_id`, `version_id`, `expected_current_sha256`, `reason`. It refuses unsaved edits: explicitly save them first. It snapshots the current AEP and opens a new byte-identical copy of the chosen verified version, verifies the copied bytes and inspected state, then promotes the new version. It never saves over the chosen version or removes intervening history. Restore does not collect or restore externally changed media files.

Manual edits should remain unsaved until `project_save`/explicit capture. An AEP changed in place on disk fails its prior verified hash; the revision engine refuses to treat that file as an immutable historical version.

## Director route

`director_revision_plan` targets one explicitly named layer and emits a patch plan through `Director.revision_patch`. The complete local Portuguese grammar is:

```text
trocar título para "NOVO TEXTO"; atrasar entrada 6 frames entre 0 e 24
```

Each semicolon-separated clause must fully match either `trocar título para "TEXT"` or `atrasar entrada N frames entre A e B` (case-insensitive). Delay moves **position** keys only, with explicit `allow_change` boundary policy visible in the resulting plan. It does not infer an entry window, change opacity/scale or accept extra words. Unknown clauses reject the whole request without a partial plan. Broader requests use host-generated typed operations.

The pre-existing `scene_revise`/`scene_execute` route still explicitly rebuilds a clean owned Director scene and protects intervening manual edits. It is a distinct operation; the property-patch route does not invoke it as a fallback.

## Verification limits

Matching AE acknowledgements, AEP/snapshot integrity, native metadata, render decoding and sampled visual review are separate evidence. A successful patch does not assert artistic quality, automatic C1 continuity, general expression editing, arbitrary property support or full-video human playback. Native timeouts retain `ae-pending.json`; no retry or interactive AE termination is allowed. Only known synchronous native failures restore their checked-clean source.
