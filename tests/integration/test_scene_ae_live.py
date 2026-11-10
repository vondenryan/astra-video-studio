"""Sprint 6: native scene graph, three precomps, relations and immutable versions."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.config import Settings


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS') != '1', reason='Opt-in native scene operations')
def test_three_scenes_parenting_mattes_and_versions():
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'astra_video_studio.mcp_server'], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                versions = {}
                async def call(name, request, blocked=False):
                    response = await session.call_tool(name, {'request': request})
                    if blocked:
                        assert response.isError, response
                        return response
                    assert not response.isError, response.content
                    result = response.structuredContent
                    assert result['status'] in ('succeeded', 'queued'), result
                    if result.get('project_path'):
                        path = Path(result['project_path'])
                        versions[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                    return result
                created = await call('project_create', {'name': 'Astra Pro — Master', 'title': 'CENA 01 / ESTRUTURA', 'width': 960, 'height': 540, 'fps': 24, 'duration': 20, 'font_size': 48})
                project = created['project_id']
                master = created['data']['compositions'][0]['composition_id'].split(':')[-1]
                title = created['data']['compositions'][0]['layers'][0]['layer_id'].split(':')[-1]
                target = {'project_id': project, 'composition_id': master}
                await call('composition_update', target | {'background': [0.015, 0.025, 0.05]})
                await call('layer_update', target | {'layer_id': title, 'out_frame': 144})
                duplicate = await call('layer_duplicate', target | {'layer_id': title, 'name': 'Disposable duplicate'})
                duplicate_id = duplicate['data']['created_layer_id']
                await call('layer_update', target | {'layer_id': duplicate_id, 'after_layer_id': title, 'blend_mode': 'screen', 'shift_frames': 6})
                for blend in ('multiply', 'add', 'normal'):
                    await call('layer_update', target | {'layer_id': duplicate_id, 'blend_mode': blend})
                await call('layer_remove', target | {'layer_id': duplicate_id})
                null = await call('null_create', target | {'name': 'Scene controller'})
                null_id = null['data']['created_layer_id']
                await call('layer_transform', target | {'layer_id': null_id, 'values': {'position': [100, 50], 'scale': [110, 110], 'rotation': 10}})
                await call('layer_parent', target | {'layer_id': title, 'parent_layer_id': null_id, 'policy': 'preserve_world'})
                await call('layer_remove', target | {'layer_id': null_id}, blocked=True)
                await call('layer_parent', target | {'layer_id': null_id, 'parent_layer_id': title, 'policy': 'preserve_local'}, blocked=True)
                await call('layer_parent', target | {'layer_id': title, 'policy': 'preserve_local'})
                await call('layer_parent', target | {'layer_id': title, 'parent_layer_id': null_id, 'policy': 'preserve_local'})
                matte = await call('layer_create', target | {'layer': {'kind': 'shape', 'name': 'Title matte', 'size': [900, 320], 'position': [480, 270], 'color': [1, 1, 1]}})
                matte_id = matte['data']['layer_id']
                await call('layer_update', target | {'layer_id': matte_id, 'enabled': False})
                for mode in ('alpha', 'luma', 'alpha_inverted', 'luma_inverted', 'none', 'alpha'):
                    args = target | {'layer_id': title, 'mode': mode}
                    if mode != 'none': args['matte_layer_id'] = matte_id
                    await call('track_matte_set', args)
                await call('layer_remove', target | {'layer_id': matte_id}, blocked=True)
                await call('precompose_layers', target | {'name': 'Scene 01', 'layer_ids': [title]}, blocked=True)
                precomp = await call('precompose_layers', target | {'name': 'Scene 01', 'layer_ids': [title, null_id, matte_id]})
                scene1 = precomp['data']['created_composition_id']
                scene1_layer = precomp['data']['created_layer_id']
                await call('composition_layer_add', {'project_id': project, 'composition_id': scene1, 'source_composition_id': master}, blocked=True)
                await call('layer_update', target | {'layer_id': scene1_layer, 'out_frame': 144})
                scene_ids = [scene1]
                for index, start in ((2, 144), (3, 312)):
                    comp = await call('composition_create', {'project_id': project, 'name': f'Scene 0{index}', 'width': 960, 'height': 540, 'fps': 24, 'duration': 7, 'background': [0.015, 0.025, 0.05]})
                    comp_id = comp['data']['created_composition_id']
                    scene_ids.append(comp_id)
                    child = {'project_id': project, 'composition_id': comp_id}
                    text = await call('layer_create', child | {'layer': {'name': f'Title 0{index}', 'text': f'CENA 0{index} / EDITÁVEL', 'font_size': 48, 'position': [480, 270]}})
                    await call('composition_update', child | {'fps': 30, 'fps_policy': 'preserve_frames'})
                    await call('composition_update', child | {'fps': 24, 'fps_policy': 'preserve_frames'})
                    await call('composition_update', child | {'fps': 30, 'fps_policy': 'preserve_seconds'})
                    await call('composition_update', child | {'fps': 24, 'fps_policy': 'preserve_seconds'})
                    await call('composition_update', child | {'duration': 2}, blocked=True)
                    if index == 2:
                        animated = child | {'layer_id': text['data']['layer_id']}
                        await call('motion_apply', animated | {'skill': 'slide_in', 'start_time': 0.25, 'duration': 0.8, 'params': {'distance_px': 180, 'overshoot': 0.03}})
                        await call('layer_update', animated | {'shift_frames': 1}, blocked=True)
                        await call('composition_update', child | {'fps': 30, 'fps_policy': 'preserve_frames'}, blocked=True)
                    await call('composition_layer_add', target | {'source_composition_id': comp_id, 'name': f'Scene 0{index}', 'start_frame': start})
                final = await call('composition_update', {'project_id': project, 'composition_id': scene_ids[1], 'name': 'Scene 02 — revised', 'background': [0.02, 0.08, 0.11]})
                assert len(final['data']['compositions']) == 4
                master_data = next(c for c in final['data']['compositions'] if c['composition_id'].endswith(master))
                assert len(master_data['layers']) == 3 and master_data['duration'] == 20
                assert all(layer['source_kind'] == 'composition' for layer in master_data['layers'])
                moved = next(c for c in final['data']['compositions'] if c['composition_id'].endswith(scene1))
                assert {l['layer_id'].split(':')[-1] for l in moved['layers']} == {title, null_id, matte_id}
                preview = await call('preview_render', target | {'start_time': 6, 'duration': 3, 'max_width': 960})
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    response = await session.call_tool('job_status', {'operation_id': preview['job_id']})
                    state = response.structuredContent
                    if state['status'] not in ('queued', 'running', 'prepared'): break
                    await asyncio.sleep(2)
                assert state['status'] == 'succeeded', state
                for path, expected in versions.items():
                    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
                evidence = {'project_id': project, 'master_id': master, 'scene_ids': scene_ids, 'project_path': final['project_path'], 'preview': state['result']['data'], 'preserved_versions': len(versions)}
                settings = Settings.from_env()
                settings.contained_path('sprint6-acceptance.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                print(json.dumps(evidence, indent=2))
    asyncio.run(asyncio.wait_for(exercise(), timeout=700))
