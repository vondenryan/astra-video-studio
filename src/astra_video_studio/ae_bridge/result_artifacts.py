"""Fixed per-job native evidence, authenticated by a small matching acknowledgement.

No path is supplied by a tool or accepted from AE. Limits apply independently to
the acknowledgement and complete evidence; invalid evidence keeps quarantine.
"""
import hashlib
import json
import os
import re

PROTOCOL = 'artifact-v1'
ACK_MAX_BYTES = 8192
INLINE_MAX_BYTES = 2_000_000
EVIDENCE_MAX_BYTES = 16 * 1024 * 1024
EVIDENCE_FILE = 'native-result.json'


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def parse_json(raw):
    def nonfinite(value): raise ValueError('Non-finite JSON number')
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs, parse_constant=nonfinite)


def validate_result(value, operation_id):
    if not isinstance(value, dict) or value.get('operation_id') != operation_id:
        raise ValueError('Native operation identity mismatch')
    if value.get('status') not in ('succeeded', 'failed') or not isinstance(value.get('data'), dict):
        raise ValueError('Invalid complete native result')
    if value['status'] == 'failed' and not isinstance(value.get('error'), str):
        raise ValueError('Native failure has no diagnostic')
    return value


def load_artifact(settings, directory, operation_id, ack):
    if not isinstance(ack, dict) or ack.get('operation_id') != operation_id or ack.get('protocol') != PROTOCOL:
        raise ValueError('Acknowledgement identity/protocol mismatch; no downgrade allowed')
    if ack.get('publication_error'):
        raise ValueError('Native evidence publication failed: ' + str(ack['publication_error'])[:1024])
    if set(ack) != {'operation_id', 'status', 'protocol', 'evidence'} or ack['status'] not in ('succeeded', 'failed'):
        raise ValueError('Invalid native acknowledgement schema')
    info = ack['evidence']
    if not isinstance(info, dict) or set(info) != {'file', 'bytes', 'sha256'} or info['file'] != EVIDENCE_FILE:
        raise ValueError('Only the fixed job-owned evidence filename is allowed')
    if type(info['bytes']) is not int or not 1 <= info['bytes'] <= EVIDENCE_MAX_BYTES:
        raise ValueError('Native evidence size declaration exceeds its separate bound')
    if not isinstance(info['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', info['sha256']):
        raise ValueError('Invalid native evidence hash')
    path = settings.contained_path(str((directory / EVIDENCE_FILE).relative_to(settings.workspace)))
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size != info['bytes']: raise ValueError('Native evidence length mismatch')
        raw = stream.read(EVIDENCE_MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or (after.st_size, after.st_mtime_ns, after.st_ino) != (current.st_size, current.st_mtime_ns, current.st_ino):
        raise ValueError('Native evidence changed while reading')
    if len(raw) != info['bytes'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
        raise ValueError('Native evidence hash/length mismatch')
    envelope = parse_json(raw)
    if not isinstance(envelope, dict) or set(envelope) != {'schema_version', 'protocol', 'result'} or type(envelope.get('schema_version')) is not int or envelope['schema_version'] != 1 or envelope.get('protocol') != PROTOCOL:
        raise ValueError('Invalid native evidence envelope')
    result = validate_result(envelope['result'], operation_id)
    if result['status'] != ack['status']: raise ValueError('Native evidence/acknowledgement status mismatch')
    return result, {'protocol': PROTOCOL, 'path': str(path), 'sha256': info['sha256'], 'bytes': len(raw)}


def revision_evidence_estimate(state, contexts):
    """Conservative estimate including generated keys and per-step inspections."""
    base = len(json.dumps(state, ensure_ascii=True, allow_nan=False).encode('ascii'))
    growth = sum(len(json.dumps(ctx, ensure_ascii=True, allow_nan=False).encode('ascii')) * (len(contexts) - index + 1)
                 for index, ctx in enumerate(contexts))
    return base * (len(contexts) + 2) + growth + 65536
