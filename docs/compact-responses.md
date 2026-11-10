# Stint 9.1 — bounded MCP responses and on-demand inspection

Stint9.1 introduced **55 tools**; Sprint11 now exposes **65 tools**. This is a host-presentation change: existing Python services, snapshots, full verification, version promotion and original job journals retain complete state. No native metadata is discarded to make a response smaller. The later [Stint 9.2 native transport](native-result-transport.md) separately changes how complete AE evidence reaches those services.

## Default response

Rich MCP tools now accept the top-level keyword `response_mode`, default `compact`. It applies to tools returning operation results, job status, Director executions and Director plans. Other small structured contracts remain unchanged.

Compact output includes status, operational/version IDs, small scalar summaries, counts and an `evidence` reference:

```json
{
  "response_mode": "compact",
  "operation_id": "<operation UUID>",
  "status": "succeeded",
  "data": {
    "counts": {"compositions": 1, "layers": 40, "keys": 2400, "samples": 1000},
    "detail_available": true
  },
  "evidence": {"sha256": "<64 hex characters>", "path": "<workspace>/responses/<hash>.json", "bytes": 123456, "schema_version": 1}
}
```

The example is illustrative, not a native acceptance measurement. New-layer/composition IDs and version/plan hashes remain available as small scalar fields when supplied by the service. The first composition/layer ID can bootstrap a new project. Animation inspection returns a bounded first five track hash summaries; query additional tracks explicitly. Revision summaries show bounded actions/changed paths/conflicts and total counts, with complete requests in evidence. Large diagnostics retain their original content in evidence; the compact error is limited to 1,024 characters.

The **8 KiB budget** measures the serialized MCP `CallToolResult`, including **both structuredContent and text content**. It excludes the small JSON-RPC transport envelope. Text-only hosts receive the same compact JSON rather than another pretty-printed full scene. An unusually large summary falls back to smaller counts/reference metadata; omitted summary detail is marked. Job polling returns at most the last three events and total event count, with the nested operation compacted too.

## Complete evidence and compatibility

Evidence is stored as `workspace/responses/<SHA-256>.json`, with schema version, original result, result kind and provenance. The hash covers exact file bytes. The file is fully written/flushed and published through an exclusive same-filesystem hard link; existing evidence is verified/reused instead of replaced. This requires filesystem hard-link support (tested on this Windows host). Identical polling snapshots reuse their reference; changed job state creates a different immutable reference. Earlier snapshots remain readable. There is no automatic evidence cleanup.

Publication/integrity failures retain the existing service journal/plan and report the returned operation identity and status. A presentation error is not permission to repeat a mutation. Inspect the original operation first.

For old callers that require full scene arrays, explicitly request:

```json
{"project_id": "<UUID>", "response_mode": "full"}
```

For tools taking `request`, put `response_mode` alongside `request`, not inside it. The **full structured payload preserves the original fields exactly**, including strict Director-plan schemas. Its evidence reference is in MCP `_meta.astra_evidence`, outside that legacy structured schema. Full mode is intentionally unbounded by the compact-response budget and may consume considerable context. The CLI equivalent is `--response-mode full`; its original complete JSON shape is preserved too. Internal service callers retain their existing full return types without any flag.

## Paged inspection

`operation_query` accepts an evidence hash, never an arbitrary path. `project_query` creates a reference from an explicitly described project-state source. Both return `EvidencePage` with `items`, `total`, `offset`, `next_offset`, `evidence` and `provenance`. Limits are **1–50 items and 16 KiB per serialized MCP result**, including text and structured copies. Byte limits can shorten a page below the requested item count.

Available sections:

| Section | Rows |
| --- | --- |
| `compositions` | Composition identity, dimensions, FPS, duration and layer count. |
| `layers` (default) | Layer identity, name, short text, lifetime/flags and animation summary. Long text is explicitly marked. |
| `transforms` | One selected track: time-zero value, flags, key/sample counts and full semantic track hash. No key/sample arrays. |
| `keys`, `samples` | Individual native keys or sampled values, only when explicitly selected. |
| `effects`, `masks` | Individual inspected effect/mask records. |
| `text_style`, `style_runs` | Typography metadata or individual character-style runs. |
| `operations`, `changes`, `conflicts`, `fonts`, `events` | Corresponding original result/journal entries. |
| `plan_elements`, `plan_actions` | Director plan elements or actions for complete intent review. |
| `fields` | Data-field names/types/counts and bounded scalar values. |

Filters: optional `composition_id`, `layer_ids` (up to 50), `properties` (position/anchor/scale/rotation/opacity), plus integer `offset` and `limit`. Sections for keys and samples never become implicit when requesting a transform summary. Filters refer to stable IDs; unsupported fields/sections are rejected.

Example project-track query:

```json
{"request": {
  "project_id": "<project UUID>",
  "composition_id": "<composition UUID>",
  "layer_ids": ["<layer UUID>"],
  "properties": ["position"],
  "section": "transforms",
  "limit": 5
}}
```

Default `project_query.refresh=false` reads **verified saved-version metadata**, checks its AEP hash and labels `unsaved_manual_edits_included=false`. It does not contact AE and is not evidence of the current unsaved UI state. `expected_source_sha256` can pin the source version.

`refresh=true` performs one read-only native inspection through the unchanged bridge and labels `live_ae_read`, operation ID and dirty-state flag. It neither saves nor captures manual edits. An existing bridge quarantine is respected. Continue paging the returned immutable reference with `operation_query`; repeatedly refreshing the project would create different snapshots if the live state changes.

Example next page or explicit keys:

```json
{"request": {
  "evidence_sha256": "<hash from prior evidence>",
  "section": "keys",
  "layer_ids": ["<layer UUID>"],
  "properties": ["position"],
  "offset": 0,
  "limit": 20
}}
```

Follow `next_offset` until null. A single item too large for the byte budget produces an explicit `item_exceeds_byte_budget` marker and increments `omitted_oversized_items`; its original remains in the evidence file/full response. Keys/samples can be queried independently instead of requesting entire tracks. This increment does not provide arbitrary JSON-pointer or general shape-vertex subdivision.

## Fewer calls and remaining limits

Use existing `motion_batch`, `stagger_layers` and bounded revision patches for actual native batches. Reuse an evidence hash to inspect multiple sections instead of reading AE again. Keep the MCP host alive for queued renders. Reload an already running MCP server after its work finishes to load the new contracts; this update does not require restarting the AE bridge.

**Stint 9.2 is now accepted separately:** the default native protocol uses an 8 KiB acknowledgement and complete 16 MiB-bounded evidence file; its revision estimate includes generated key growth. Explicit legacy inline mode retains the old 2 MB/1.2 MB bounds. Compact host responses do not remove native inspection/verification cost, guarantee arbitrary project size or bypass unknown execution. Stint 9.1 itself changed no JSX transport, renderer or pending marker. Audio remains Sprint 10.


## Stint9.3 diagnostics and host acceptance

studio_status now exposes mcp_runtime (process identity, package/interpreter paths and versions, policy9.3 and startup source hash). Rich responses carry _meta.astra_presentation with runtime identity, tool and effective mode. These bytes count toward the8 KiB compact budget. Full mode adds this metadata without changing its legacy structured payload. Output-schema defaults now agree with compact input defaults. Effective mode does not distinguish an omitted argument from one the SDK inserted as its default; capture raw arguments to tell them apart.

The startup hash describes observed package source bytes, not host routing or running bytecode. Calling a fresh CLI does not identify an existing MCP connection. Local fixture validation passed the three reviewed tools at3/5/40/80 layers; the operator reported9.3 in Claude Desktop. Final affected-host acceptance remains pending. See [scope, evidence and safe acceptance steps](host-response-acceptance.md). No AE transport limit, internal verification, native timeout or query page budget changed.


## Sprint10 audio evidence

New audio OperationResults use the same8KiB envelope, immutable evidence and full compatibility option. Standard summaries expose audio_clips_count/audio_markers_count/sync_events_count without implicit arrays. New explicit query sections are audio_clips/audio_markers/sync_events. Clips/timeline cues are available from audio_state_sha256, source cues from marker_set_sha256, and sync_events from the operation evidence.sha256. Existing query budgets remain16KiB. Native transport is unchanged. See [audio contracts](audio-tools.md).


## Sprint11 final presets and packages

render_presets_list/delivery_collect/delivery_validate retain the compact/full/evidence policy. New explicit query section render_presets pages the two preset records; default only exposes counts/scalars/references. Final submissions reuse the small submission/job-status contracts. Sequence frame hashes live in a separate manifest rather than an implicit response array. No native ACK/evidence ceiling or response byte budget was raised.

## Opt-in orchestration receipts — 2026-11-10

Rich results also accept `response_mode="receipt"` (CLI `--response-mode receipt`). The complete MCP result envelope, including both representations and presentation metadata, is capped at3KiB. It retains status/IDs/evidence with fewer summary fields; polling omits events and the nested result. Complete service evidence/journals remain unchanged. Default compact stays8KiB and full keeps its exact legacy structured payload.

Local controllers with access to the same workspace may use `astra_video_studio.local_client.resolve_response(settings,response)` to read and verify immutable evidence without an additional MCP call. It derives the contained filename from SHA, checks size/hash/schema/identity/status and rechecks the hash after reading. It never resends a mutation. Remote hosts use compact plus filtered/paged operation_query; receipt is not a remote arbitrary-file reader. `created_layers` is a new bounded query section; grouped creation also exposes its up-to20 role/UUID mappings in compact mode. See [creation optimization](creation-optimization.md).
