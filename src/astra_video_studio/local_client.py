"""Verified local evidence resolution for stdio orchestrators, never a remote file tool."""
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json


def resolve_response(settings,response,expected_kind=None):
    """Load a completed result locally without another MCP call or a full wire payload.

    Must never be used to retry a mutation if decoding/presentation fails.
    The caller still checks the returned service status and verification fields.
    """
    if response.isError:raise ValueError('MCP returned an error; inspect its journal before any retry')
    payload=response.structuredContent
    if not isinstance(payload,dict):raise ValueError('Structured MCP response missing; do not retry automatically')
    reference=payload.get('evidence')
    if not reference:return payload  # Small legacy values, e.g. design token records.
    sha=reference.get('sha256','')
    if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid response evidence hash')
    path=settings.contained_path('responses/'+sha+'.json')
    # Never follow a path supplied by the result; derive the fixed owned path.
    if path.stat().st_size!=reference['bytes'] or digest(path)!=sha:raise ValueError('Response evidence size/hash conflict; no retry')
    record=read_json(path)
    if record.get('schema_version')!=1 or expected_kind and record.get('kind')!=expected_kind:raise ValueError('Response evidence kind/schema mismatch')
    raw=record['result']
    for key in ('operation_id','execution_id','plan_id','status'):
        if key in payload and payload[key]!=raw.get(key):raise ValueError('Receipt/evidence identity or status mismatch')
    if digest(path)!=sha:raise ValueError('Evidence changed while reading')
    return raw
