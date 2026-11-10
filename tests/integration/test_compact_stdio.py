"""Real MCP protocol with explicit saved-state/service fixtures; no AE execution."""
import asyncio
import json
import os
from pathlib import Path
import sys
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.responses import encoded, COMPACT_BYTES, PAGE_BYTES


def fixture(count):
    return {'fixture_only': True, 'project_dirty': False, 'compositions': [{
        'composition_id': 'astra:composition:' + '2'*32, 'name': 'Simulated state', 'fps': 24, 'duration': 5, 'width': 960, 'height': 540,
        'layers': [{'layer_id': 'astra:layer:' + f'{i+10:032x}', 'name': f'Layer {i}', 'text': 'Fixture',
            'transforms': {name: {'available': True, 'value': [10, 20], 'keys': [{'time': n/24, 'value': [n, i]} for n in range(12)],
                'samples': [{'time': n, 'value': [i, n]} for n in range(5)], 'expression_enabled': False, 'separated': False}
                for name in ('position', 'anchor', 'scale', 'rotation', 'opacity')},
            'animation_summary': {'key_count': 60, 'expressions': 0}} for i in range(count)]}], 'footage': []}


@pytest.mark.integration
def test_compact_mutations_paging_polling_and_explicit_legacy_mode(tmp_path):
    fixtures = {str(n): fixture(n) for n in (3, 40, 80)}
    write_json(tmp_path/'fixtures.json', fixtures)
    directory = tmp_path/'projects'/('3'*32); directory.mkdir(parents=True)
    source = directory/'project.aep'; source.write_bytes(b'fixture-not-real-AEP'*20)
    write_json(directory/'project.json', {'status': 'succeeded', 'sha256': digest(source), 'result': {
        'operation_id': '4'*32, 'status': 'succeeded', 'project_id': '3'*32, 'data': fixtures['80']}})
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=[str(Path('tests/fixtures/compact_mcp_server.py').resolve())], env=dict(os.environ, ASTRA_WORKSPACE=str(tmp_path)))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert len(listing.tools) == 77
                rich = next(t for t in listing.tools if t.name == 'project_create')
                assert rich.inputSchema['properties']['response_mode']['default'] == 'compact'
                sizes = {}
                last = None
                for count in (3, 40, 80):
                    response = await session.call_tool('project_create', {'request': {'title': str(count)}})
                    assert not response.isError, response.content
                    raw = response.structuredContent; last = raw
                    size = len(encoded(response.model_dump(mode='json', exclude_none=True)))
                    assert size <= COMPACT_BYTES
                    assert raw['data']['counts']['layers'] == count
                    assert 'compositions' not in raw['data']
                    assert json.loads(response.content[0].text) == raw
                    journal = json.loads((tmp_path/'jobs'/raw['operation_id']/'job.json').read_text())
                    assert len(journal['result']['data']['compositions'][0]['layers']) == count
                    sizes[count] = size
                assert max(sizes.values()) - min(sizes.values()) < 100
                from astra_video_studio.local_client import resolve_response
                from astra_video_studio.config import Settings
                from astra_video_studio.responses import RECEIPT_BYTES
                receipt = await session.call_tool('project_create', {'request': {'title': '80'}, 'response_mode': 'receipt'})
                assert not receipt.isError
                assert len(encoded(receipt.model_dump(mode='json', exclude_none=True))) <= RECEIPT_BYTES
                assert 'compositions' not in receipt.structuredContent['data']
                assert len(resolve_response(Settings(tmp_path), receipt)['data']['compositions'][0]['layers']) == 80
                # Dozens of simulated changes retain bounded protocol output.
                for _ in range(40):
                    response = await session.call_tool('project_create', {'request': {'title': '80'}})
                    assert not response.isError
                    assert len(encoded(response.model_dump(mode='json', exclude_none=True))) <= COMPACT_BYTES
                full = await session.call_tool('project_create', {'request': {'title': '80'}, 'response_mode': 'full'})
                assert len(full.structuredContent['data']['compositions'][0]['layers']) == 80
                assert 'response_mode' not in full.structuredContent and 'evidence' not in full.structuredContent
                assert full.meta['astra_evidence']['sha256']
                assert len(encoded(full.structuredContent)) > 100_000
                poll = await session.call_tool('job_status', {'operation_id': last['operation_id']})
                assert not poll.isError and 'compositions' not in poll.structuredContent['result']['data']
                assert len(encoded(poll.model_dump(mode='json', exclude_none=True))) <= COMPACT_BYTES
                # Saved query performs no AE calls and labels its state explicitly.
                saved = await session.call_tool('project_query', {'request': {'project_id': '3'*32, 'limit': 50}})
                assert not saved.isError, saved.content
                page = saved.structuredContent
                assert page['provenance']['state'] == 'verified_saved_version'
                ids = [x['layer_id'] for x in page['items']]
                while page['next_offset'] is not None:
                    response = await session.call_tool('operation_query', {'request': {'evidence_sha256': page['evidence']['sha256'], 'offset': page['next_offset'], 'limit': 50}})
                    assert not response.isError, response.content
                    assert len(encoded(response.model_dump(mode='json', exclude_none=True))) <= PAGE_BYTES
                    page = response.structuredContent
                    ids.extend(x['layer_id'] for x in page['items'])
                assert len(ids) == len(set(ids)) == 80
                selector = {'evidence_sha256': last['evidence']['sha256'], 'layer_ids': [f'{10:032x}'], 'properties': ['position']}
                for section, expected in [('transforms', 1), ('keys', 12), ('samples', 5)]:
                    response = await session.call_tool('operation_query', {'request': selector | {'section': section}})
                    assert not response.isError and response.structuredContent['total'] == expected
                failed = await session.call_tool('project_create', {'request': {'title': 'failure'}})
                assert failed.structuredContent['status'] == 'failed'
                assert len(failed.structuredContent['error']) == 1024
                invalid = await session.call_tool('operation_query', {'request': selector | {'path': 'outside'}})
                assert invalid.isError
                # Validation rejects mode before executing even a fixture service.
                jobs_before = len(list((tmp_path/'jobs').iterdir()))
                invalid = await session.call_tool('project_create', {'request': {'title': '80'}, 'response_mode': 'unknown'})
                assert invalid.isError and len(list((tmp_path/'jobs').iterdir())) == jobs_before
    asyncio.run(asyncio.wait_for(exercise(), timeout=90))


@pytest.mark.integration
def test_cli_uses_same_compact_policy_and_explicit_full_mode(tmp_path):
    directory = tmp_path/'jobs'/('1'*32); directory.mkdir(parents=True)
    write_json(directory/'job.json', {'operation_id': '1'*32, 'action': 'fixture', 'status': 'succeeded', 'events': [{'status': 'succeeded'}],
        'result': {'operation_id': '1'*32, 'status': 'succeeded', 'data': fixture(80)}})
    def run(mode):
        output = subprocess.run([sys.executable, '-m', 'astra_video_studio.cli', 'job-status', '--job-id', '1'*32, '--response-mode', mode],
                                env=dict(os.environ, ASTRA_WORKSPACE=str(tmp_path)), capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert output.returncode == 0, output.stderr
        return output.stdout, json.loads(output.stdout)
    text, compact = run('compact')
    assert len(text.encode('utf-8')) <= COMPACT_BYTES
    assert compact['response_mode'] == 'compact'
    assert 'compositions' not in compact['result']['data']
    _, full = run('full')
    assert len(full['result']['data']['compositions'][0]['layers']) == 80
