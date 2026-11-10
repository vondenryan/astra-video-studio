"""Public three-tool routes, exact wire budgets, and explicit compatibility mode.

Running this file directly writes a uniquely owned acceptance record under workspace.
It is a fixture-only MCP client, not proof of acceptance in the external Claude host.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.jobs import write_json
from astra_video_studio.responses import encoded, COMPACT_BYTES, PAGE_BYTES


TOOLS = ('layer_create', 'text_style_set', 'motion_apply')


def scene(count):
    layers = []
    for i in range(count):
        path = {'vertices': [[n, n+1] for n in range(32)], 'closed': True}
        layers.append({
            'layer_id': 'astra:layer:' + f'{i+10:032x}', 'name': f'Fixture {i}', 'text': 'AÇÃO',
            'transforms': {p: {'value': [i, 10], 'keys': [{'time': n/24, 'value': [i, n]} for n in range(12)],
                'samples': [{'time': n/24, 'value': [i, n]} for n in range(5)]}
                for p in ('position', 'anchor', 'scale', 'rotation', 'opacity')},
            'masks': [{'path': path, 'opacity': 100}],
            'shape_state': {'groups': [{'path': path, 'fill': [1, 0, 0]}]},
            'text_style': {'font': 'FixtureFont', 'font_size': 64, 'style_runs': [{'start': 0, 'end': 4}]},
        })
    return {'fixture_only': True, 'compositions': [{'composition_id': 'astra:composition:' + '2'*32,
        'layers': layers, 'fps': 24, 'duration': 5}], 'footage': []}


def arguments(tool):
    base = {'project_id': '3'*32, 'composition_id': '2'*32}
    if tool == 'layer_create': return {'request': base | {'layer': {'kind': 'text', 'text': 'Fixture'}}}
    base['layer_id'] = f'{10:032x}'
    return {'request': base | ({'font_size': 64} if tool == 'text_style_set' else {'skill': 'slide_in'})}


async def exercise(root):
    root.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'fixture-only real stdio MCP; no AE/native writes; not the affected external host',
              'affected_host_acceptance': 'pending', 'measurements': [], 'runtime_ids': [],
              'budgets': {'compact_bytes': COMPACT_BYTES, 'page_bytes': PAGE_BYTES}}
    for count in (3, 5, 40, 80):
        workspace = root/str(count)
        workspace.mkdir()
        data = scene(count)
        write_json(workspace/'host-fixture.json', data)
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path('tests/fixtures/host_response_mcp_server.py').resolve())],
            env=dict(os.environ, ASTRA_WORKSPACE=str(workspace)))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                listing = await session.list_tools()
                schemas = {t.name: t.inputSchema for t in listing.tools}
                outputs = {t.name: t.outputSchema for t in listing.tools}
                write_json(workspace/'schema.json', {'server': init.serverInfo.model_dump(mode='json'),
                    'tools': {t: schemas[t] for t in TOOLS}})
                runtime_ids = set()
                for tool in TOOLS:
                    assert schemas[tool]['properties']['response_mode']['default'] == 'compact'
                    assert outputs[tool]['properties']['response_mode']['default'] == 'compact'
                    for mode in ('omitted', 'compact', 'full'):
                        args = arguments(tool)
                        if mode != 'omitted': args['response_mode'] = mode
                        response = await session.call_tool(tool, args)
                        assert not response.isError, response.content
                        raw = response.model_dump(mode='json', exclude_none=True)
                        size = len(encoded(raw))
                        payload = response.structuredContent
                        assert json.loads(response.content[0].text) == payload
                        meta = response.meta['astra_presentation']
                        assert meta['tool'] == tool and meta['policy_version'] == '9.3'
                        assert meta['effective_mode'] == ('compact' if mode == 'omitted' else mode)
                        runtime_ids.add(meta['runtime_id'])
                        record = {'layers': count, 'tool': tool, 'requested_mode': mode,
                            'effective_mode': meta['effective_mode'], 'wire_bytes': size,
                            'text_bytes': len(response.content[0].text.encode('utf-8')),
                            'structured_bytes': len(encoded(payload)), 'runtime': meta,
                            'arguments': args, 'wire_sha256': hashlib.sha256(encoded(raw)).hexdigest()}
                        write_json(workspace/f'{tool}-{mode}.json', raw)
                        if mode == 'full':
                            assert payload['data'] == data
                            assert 'response_mode' not in payload
                            ref = response.meta['astra_evidence']
                        else:
                            assert size <= COMPACT_BYTES
                            assert payload['data']['counts']['layers'] == count
                            assert payload['data']['counts']['keys'] == count*60
                            assert payload['data']['counts']['samples'] == count*25
                            assert 'compositions' not in payload['data']
                            ref = payload['evidence']
                        evidence = Path(ref['path']).read_bytes()
                        assert len(evidence) == ref['bytes']
                        assert hashlib.sha256(evidence).hexdigest() == ref['sha256']
                        original = json.loads(evidence)['result']
                        assert original['data'] == data  # masks, shapes, styles and every key remain complete
                        journal = json.loads((workspace/'jobs'/payload['operation_id']/'job.json').read_text())
                        assert journal['result'] == original
                        record['evidence'] = ref
                        report['measurements'].append(record)
                        if mode == 'omitted':
                            ids, offset = [], 0
                            while offset is not None:
                                page = await session.call_tool('operation_query', {'request': {
                                    'evidence_sha256': ref['sha256'], 'offset': offset, 'limit': 50}})
                                assert not page.isError
                                assert len(encoded(page.model_dump(mode='json', exclude_none=True))) <= PAGE_BYTES
                                p = page.structuredContent
                                assert all('transforms' not in row and 'masks' not in row for row in p['items'])
                                ids.extend(row['layer_id'] for row in p['items'])
                                offset = p['next_offset']
                            assert len(ids) == len(set(ids)) == count
                            for section, total in (('keys', 12), ('samples', 5)):
                                page = await session.call_tool('operation_query', {'request': {
                                    'evidence_sha256': ref['sha256'], 'layer_ids': [f'{10:032x}'],
                                    'properties': ['position'], 'section': section}})
                                assert not page.isError and page.structuredContent['total'] == total
                                assert len(encoded(page.model_dump(mode='json', exclude_none=True))) <= PAGE_BYTES
                assert len(runtime_ids) == 1
                report['runtime_ids'].extend(runtime_ids)
                # Invalid mode must fail before even a fixture mutation creates a job.
                before = len(list((workspace/'jobs').iterdir()))
                invalid = await session.call_tool('layer_create', arguments('layer_create') | {'response_mode': 'unexpected'})
                assert invalid.isError and len(list((workspace/'jobs').iterdir())) == before
    assert len(set(report['runtime_ids'])) == 4
    compact = [r['wire_bytes'] for r in report['measurements'] if r['requested_mode'] != 'full']
    report['compact_range_bytes'] = [min(compact), max(compact)]
    report['compact_cumulative_bytes'] = sum(compact)
    report['explicit_full_cumulative_bytes'] = sum(r['wire_bytes'] for r in report['measurements'] if r['requested_mode'] == 'full')
    report['result'] = 'local_fixture_acceptance_passed_external_host_pending'
    write_json(root/'acceptance.json', report)
    return report


@pytest.mark.integration
def test_reviewed_tool_routes_and_response_modes(tmp_path):
    report = asyncio.run(asyncio.wait_for(exercise(tmp_path), timeout=90))
    assert len(report['measurements']) == 36


if __name__ == '__main__':
    destination = Path('workspace')/('stint9-3-' + uuid4().hex)
    report = asyncio.run(asyncio.wait_for(exercise(destination), timeout=90))
    print(json.dumps({'acceptance': str((destination/'acceptance.json').resolve()),
        'result': report['result'], 'compact_range_bytes': report['compact_range_bytes']}))
