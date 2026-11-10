"""Native ACK/evidence acceptance through real stdio MCP; no project mutation."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.config import Settings
from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.ae_bridge.result_artifacts import ACK_MAX_BYTES, EVIDENCE_MAX_BYTES
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.responses import encoded


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS') != '1', reason='Opt-in read-only native evidence transport acceptance')
def test_real_ae_large_result_small_ack_and_unchanged_project():
    settings = Settings.from_env()
    assert not settings.contained_path('ae-pending.json').exists(), 'Do not submit while a native operation is uncertain'
    state = IdleTransport(settings).state()
    assert state and not state.get('active_job'), 'Known session must already have a fresh idle heartbeat; no automatic restart'
    markers = {name: digest(settings.workspace/name) for name in ('preview-pending.json',) if (settings.workspace/name).exists()}
    async def exercise():
        env = dict(os.environ, ASTRA_AE_RESULT_TRANSPORT='artifact-v1')
        params = StdioServerParameters(command=sys.executable, args=[str(Path('tests/fixtures/native_artifact_mcp_server.py').resolve())], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                operations = []
                async def probe(query, expected_status='succeeded'):
                    response = await session.call_tool('fonts_list', {'request': {'query': query, 'limit': 1}, 'response_mode': 'compact'})
                    assert not response.isError, response.content
                    host = response.structuredContent
                    assert host['status'] == expected_status, host
                    assert len(encoded(response.model_dump(mode='json', exclude_none=True))) <= 8192
                    directory = settings.contained_path('jobs/' + host['operation_id'])
                    ack_raw = (directory/'result.json').read_bytes()
                    ack = json.loads(ack_raw.decode('utf-8-sig'))
                    raw = (directory/'native-result.json').read_bytes()
                    journal = json.loads((directory/'job.json').read_text(encoding='utf-8'))
                    assert len(ack_raw) < ACK_MAX_BYTES
                    assert ack['operation_id'] == host['operation_id'] and ack['protocol'] == 'artifact-v1'
                    assert ack['evidence']['bytes'] == len(raw) <= EVIDENCE_MAX_BYTES
                    assert hashlib.sha256(raw).hexdigest() == ack['evidence']['sha256'] == journal['native_evidence']['sha256']
                    result = json.loads(raw.decode('utf-8-sig'))['result']
                    if expected_status == 'failed': assert 'EXPECTED_READ_ONLY_NATIVE_FIXTURE_FAILURE' in result['error']
                    assert journal['result']['data'] == result['data']
                    assert result['data']['fixture_unicode'] == 'Ação 😀 日本語\nLine two'
                    record = {'operation_id': host['operation_id'], 'ack_bytes': len(ack_raw), 'evidence_bytes': len(raw), 'sha256': ack['evidence']['sha256'],
                              'mcp_bytes': len(encoded(response.model_dump(mode='json', exclude_none=True))), 'evidence_path': str(directory/'native-result.json')}
                    operations.append(record)
                    return result['data']
                baseline = await probe('AstraTransportBaselineFixture')
                source = None; source_sha = None
                if baseline['active_project_fixture']['file']:
                    try:
                        source = settings.import_path(baseline['active_project_fixture']['file'])
                        source_sha = digest(source)
                    except ValueError: pass  # Do not add read roots to inspect an external active source.
                large = await probe('AstraTransportLargeFixture')
                assert operations[-1]['evidence_bytes'] > 2_000_000
                assert len(large['transport_fixture']['payload']) == 16 * 2**17
                assert large['transport_fixture']['payload'] == '0123456789ABCDEF' * 2**17
                failed = await probe('AstraTransportFailureFixture', expected_status='failed')
                after = await probe('AstraTransportAfterFixture')
                assert baseline['active_project_fixture'] == large['active_project_fixture'] == failed['active_project_fixture'] == after['active_project_fixture']
                if source: assert digest(source) == source_sha
                for name, sha in markers.items(): assert digest(settings.workspace/name) == sha
                assert not settings.contained_path('ae-pending.json').exists()
                write_json(settings.contained_path('stint9-2-native-acceptance-' + operations[0]['operation_id'] + '.json'), {'scope': 'Real AE read-only font jobs with reviewed large-result and failure fixtures; no project edit/save/open/render',
                    'operations': operations, 'active_project_metadata_unchanged': True, 'active_project_state': after['active_project_fixture'],
                    'owned_active_source_path': str(source) if source else None, 'owned_active_source_sha256': source_sha,
                    'external_source_bytes_not_read': source is None, 'retained_preview_pending': markers, 'project_mutation_performed': False,
                    'render_performed': False, 'visual_review_performed': False})
    asyncio.run(asyncio.wait_for(exercise(), timeout=240))
