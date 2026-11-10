# Existing projects — Sprint 3

## Open-copy contract

`project_open_copy(request={"source_path": "incoming/client.aep"})` accepts an existing `.aep`, at least 64 bytes, within the workspace or trusted operator-configured `ASTRA_IMPORT_ROOTS`. Resolve symlinks/traversal before checking read roots. External roots are environment configuration, never tool arguments or per-call approval booleans. Relative paths are workspace-relative. `.aepx` and other formats are outside this increment.

Copy the source into an exclusive `projects/<UUID>/` directory as `original-source.aep` and `project.aep`. Compare SHA-256 of source/backup/copy before opening and again after AE acknowledges the copy. No original is opened for editing or saved. A malformed AEP can still fail inside AE; a suffix/size check is not a parser. Failures and timeouts are explicit and preserve artifacts.

An empty untitled or unchanged Astra-managed active project may be closed. If the requested source is already active and clean, the explicit open-copy request also permits closing that source to open its working copy. Unsaved source edits or unrelated untracked projects remain protected. No save dialog is dismissed automatically.

Opening uses AE's normal `app.open`, not project import. Item/Layer native IDs are documented to persist across save/reopen, while importing into another project assigns new IDs. The first inspection creates sidecar UUID maps keyed by these native IDs, leaving all comments untouched. Duplicate names/comments remain legal. IDs are returned using the existing `astra:composition:<UUID>` / `astra:layer:<UUID>` format; the prefix is an API representation and is not written into imported client comments.

## Editing and explicit saving

Transform/motion tools resolve targets through the sidecar map. They require the latest verified saved copy to be active and clean; compare its hash; snapshot the parent; save changes into a new version; reopen; verify target changes and all non-target inspected layers/compositions. Only after verification does `project.json.current_version` advance. Unsupported camera/light/3D targets and missing properties remain inspectable but are not editable by 2D tools. Locked targets and separated position dimensions are refused. Detection uses concrete types/properties because host inheritance checks were unreliable for TextLayer/AVLayer in live testing.

`project_save(project_id)` is an explicit request to preserve the active managed project state, including unsaved manual changes. It snapshots the prior disk state, saves to an exclusive version, reopens it, verifies the inspected composition/layer/media state, and extends UUID mappings for new native IDs. Seed mappings from the last verified state so a duplicated layer inserted before its original cannot claim its UUID. Existing comments remain unchanged. The prior disk files are never overwritten. If manual edits happen between inspection and saving, verification may fail; the saved output is retained for review rather than silently promoted.

Inspection reports source comments, locked/enabled/3D/editable status, parenting IDs, timing, available/separated transforms, native keys/ease and file-footage references provided by AE. The source AEP alone does not package linked assets. AE can access linked media/expressions when opening a trusted project; these application-internal reads are not sandboxed by Python's source-path validator. Missing media, fonts, plugins or modal dialogs can affect fidelity/opening. No collect/relink/plugin repair or visual fidelity claim is made here.

The selective-edit guarantee is checked against the inspector's metadata (including all other layers/compositions and unchanged source hashes). It is not a pixel-perfect render comparison or exhaustive serialization of every effect/mask/plugin setting. Transform templates touch only the chosen transform properties, with requested composition/layer blur changes for motion.

## Verification procedure

Opt-in `tests/integration/test_existing_ae_live.py` creates a real ordinary source with two compositions, repeated layer names, client comments, a locked sentinel and a camera. Its generated source is a disposable fixture, not a client-supplied production project. The test opens a copy via MCP, rejects the locked target, sets only the selected title's opacity/rotation and checks other metadata and source bytes. It then deliberately simulates manual rename/duplication inside that managed test copy, explicitly saves it via MCP and verifies stable IDs and preserved prior file hashes. Fixture script injections exist only in the opt-in test process and are not exposed through any product tool.

References: [Layer.id](https://ae-scripting.docsforadobe.dev/layer/layer/), [Application/project opening](https://ae-scripting.docsforadobe.dev/general/application/). Actual evidence is in `test-report.md`.
