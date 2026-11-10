# Stint 9.2 — small native acknowledgements and complete file-backed evidence

The default native result protocol is **artifact-v1**. The idle inbox, generated UUID delivery, operation allowlist, machine mutex and deferred acknowledgement stay in place. No new public tool, arbitrary JSX/path input, network service or dependency was added. There are still 55 tools.

## Publication and verification

1. The trusted operation executes through the existing idle dispatcher. All mutation/source-snapshot/protection rules still apply.
2. AE serializes the **complete** original result (`operation_id`, status, data, error) in a versioned envelope to `jobs/<UUID>/native-result.incomplete.json`. Native verification data and revision intermediate inspections are retained, not summarized.
3. AE closes the UTF-8 file, checks its actual byte length, then computes SHA-256 over a chunked **binary reread**. This covers actual file bytes, including any BOM, rather than UTF-16 string code units. The fixed ES3 implementation uses no shell or external code.
4. AE renames the completed file to `native-result.json`, refusing existing temporary/final files. It then schedules the existing deferred callback to publish the small `result.json` acknowledgement after the invocation returns.
5. Python requires the expected protocol and matching operation UUID. It accepts only the fixed filename, strictly bounded integer byte count and SHA-256 descriptor. It reads only the corresponding job-owned file within the configured workspace, checks length/hash and stable file metadata, parses strict UTF-8 JSON and compares envelope identity/status with the acknowledgement.
6. Only then is the **full original result** returned to existing Python services. Their normal semantic verification/save-reopen checks and version promotion remain unchanged. The journal retains `native_evidence` (path, bytes, SHA-256, protocol), and the native evidence is an artifact. Stint 9.1 independently controls compact host responses.

Acknowledgement shape:

```json
{
  "operation_id": "<generated job UUID>",
  "status": "succeeded",
  "protocol": "artifact-v1",
  "evidence": {
    "file": "native-result.json",
    "bytes": 2098834,
    "sha256": "<64 hex characters>"
  }
}
```

The filename is an exact protocol constant, not a caller-selectable file path. Duplicate JSON keys, non-finite JSON numbers, mismatched protocol/UUID/status, invalid hashes, changed/truncated files and invalid envelopes are refused.

## Bounds and deadlines

| Channel | Bound |
| --- | ---: |
| Native artifact-v1 acknowledgement | 8 KiB |
| Complete native evidence file | 16 MiB |
| Compact MCP result, text + structured | 8 KiB |
| Paged MCP inspection, text + structured | 16 KiB |

These are independent channels. The old 2 MB acknowledgement is not enlarged: the default protocol replaces its embedded full payload with a small authenticated descriptor. A separate explicit evidence bound controls file reads and native publication. This is not an unlimited-scene or performance guarantee.

The existing 60-second runner deadline is unchanged. Native hashing and full inspections still cost time proportional to evidence size. Live acceptance exercised just over 2 MB; it does **not** establish that every 16 MiB result or arbitrary project finishes within the deadline. Unknown/late execution still enters quarantine.

Artifact-mode revision preflight estimates complete per-step inspections plus prepared/generated track growth and an envelope reserve against the 16 MiB bound. It checks again at application before manual capture or native writes. Existing schema/key/operator bounds and complete verification are unchanged. Split a patch that exceeds the estimate. The runtime still checks the actual produced file even when the estimate passed.

## Failures and recovery

- A normal native failure with complete matching evidence returns `failed`, retains the full diagnostic and follows the existing no-promotion rules. Its acknowledgement can clear the operation marker because evidence and execution identity are verified.
- Missing, corrupt, oversized, changed or mismatched evidence is not success, even when a small acknowledgement exists. The host retains `ae-pending.json`, the job and available artifacts, reports the verification reason and blocks subsequent submissions.
- A native publication failure produces a small diagnostic acknowledgement with `publication_error`, but **no valid descriptor**. It cannot authorize promotion or release quarantine. The incomplete file remains for inspection.
- No automatic downgrade, retry, pending-marker deletion, AEP rollback or AE termination is introduced. Confirm the actual job/AE outcome before manual recovery, including any late acknowledgement.
- The independent `preview-pending.json` guard still blocks new uncertain renders. Read-only transport acceptance did not clear/recover the previously pending render or start another one.

## Compatibility and migration

`ASTRA_AE_RESULT_TRANSPORT` is an operator environment setting: `artifact-v1` (default) or `inline-v1` (legacy). It is not a tool parameter and `.env.example` is reference only. The legacy mode retains the 2,000,000-byte inline acknowledgement bound and 1,200,000-byte revision estimate. Never auto-fallback from invalid artifact evidence to inline data.

Old jobs are not rewritten. Their original inline `result.json` remains valid historical evidence. New artifact-mode jobs have a small `result.json`; consumers requiring original native detail should read verified `native-result.json` or the complete service journal. Public service result data and explicit full MCP output retain their prior shape.

The existing reviewed idle dispatcher works with both per-job formats; another bootstrap is not required by this update. Reload an already running MCP host after its work finishes to load new Python code. An old host reading the updated template without a protocol flag still receives its legacy inline response. Preserve unresolved native/render markers during any reload.

## Acceptance scope

Native acceptance used real AE through real stdio MCP, with a reviewed **read-only font-result fixture** adding a large controlled payload. It checked a complete result over 2 MB, small acknowledgement, Unicode round-trip, matching native/Python hashes, full internal journal data, a known native failure and unchanged active-project metadata/source bytes. It did not create/open/save/edit/render projects. A separate production `project_query(refresh=true)` used the default protocol and unmodified production template to read the actual active project.

Functional tests cover strict parsing, bounds, malformed/missing/changed evidence, stale/wrong identity, no downgrade, complete failure diagnostics, quarantine/no-resend, legacy compatibility, revision budgeting and SHA vectors (including binary/Unicode/BOM/chunk boundaries). Larger native scenes, maximum-file-size timing, render execution and artistic approval are separate acceptance scopes.
