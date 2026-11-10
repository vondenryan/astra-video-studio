"""Read-only process identity for diagnosing stale or misrouted MCP connections."""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import sys
from uuid import uuid4


POLICY_VERSION = '9.3'


@lru_cache(maxsize=1)
def _identity():
    package = Path(__file__).resolve().parent
    fingerprint = hashlib.sha256()
    for source in sorted((*package.rglob('*.py'), *package.rglob('*.jsx'))):
        fingerprint.update(source.relative_to(package).as_posix().encode('utf-8') + b'\0')
        fingerprint.update(source.read_bytes() + b'\0')
    return {
        'runtime_id': uuid4().hex,
        'pid': os.getpid(),
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'python_executable': sys.executable,
        'package_path': str(package),
        'package_version': version('astra-video-studio'),
        'mcp_version': version('mcp'),
        'presentation_policy': POLICY_VERSION,
        'startup_source_sha256': fingerprint.hexdigest(),
        'fingerprint_scope': 'package Python/JSX bytes observed at MCP startup; not proof of host routing',
    }


def runtime_identity():
    # Callers cannot modify the cached identity; never read host configs or env secrets.
    return dict(_identity())


def presentation_metadata(tool, mode):
    identity = runtime_identity()
    return {'astra_presentation': {
        'runtime_id': identity['runtime_id'],
        'startup_source_sha256': identity['startup_source_sha256'],
        'policy_version': POLICY_VERSION,
        'tool': tool,
        'effective_mode': mode,
    }}
