"""Sprint 7 native editable brand card, fonts, vectors and responsive layouts."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.config import Settings


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS') != '1', reason='Opt-in native design acceptance')
def test_editable_brand_card_typography_vectors_and_portrait():
    settings = Settings.from_env()
    asset = settings.contained_path('fixtures/' + uuid4().hex + '/logo.svg')
    asset.parent.mkdir(parents=True, exist_ok=False)
    asset.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><path d="M100 10 L190 180 L145 180 L100 90 L55 180 L10 180 Z" fill="#4bdcff"/><path d="M72 145 L128 145 L138 165 L62 165 Z" fill="#ffffff"/></svg>', encoding='utf-8')
    asset_hash = hashlib.sha256(asset.read_bytes()).hexdigest()
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'astra_video_studio.mcp_server'], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                versions = {}
                async def call(name, request, blocked=False):
                    response = await session.call_tool(name, {'request': request})
                    if blocked:
                        assert response.isError or response.structuredContent['status'] == 'failed', response
                        return response
                    assert not response.isError, response.content
                    result = response.structuredContent
                    if 'status' in result: assert result['status'] in ('succeeded', 'queued'), result
                    if result.get('project_path'):
                        p = Path(result['project_path'])
                        versions[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
                    return result
                fonts = await call('fonts_list', {'query': 'Arial', 'limit': 30})
                installed = {f['postscript_name']: f for f in fonts['data']['fonts']}
                assert {'ArialMT', 'Arial-BoldMT'} <= installed.keys()
                regular = {k: installed['ArialMT'][k] for k in ('postscript_name', 'font_id')}
                bold = {k: installed['Arial-BoldMT'][k] for k in ('postscript_name', 'font_id')}
                created = await call('project_create', {'name': 'Astra Pro — Brand Card', 'title': 'ASTRA STUDIO', 'width': 1920, 'height': 1080, 'fps': 24, 'duration': 5, 'font_size': 88})
                project = created['project_id']; comp = created['data']['compositions'][0]['composition_id'].split(':')[-1]
                title = created['data']['compositions'][0]['layers'][0]['layer_id'].split(':')[-1]
                base = {'project_id': project, 'composition_id': comp}
                await call('text_style_set', base | {'layer_id': title, 'font': {'postscript_name': 'ASTRA_Font_Does_Not_Exist_12345'}, 'font_size': 88}, blocked=True)
                await call('text_style_set', base | {'layer_id': title, 'font': bold, 'font_size': 88, 'tracking': 30, 'leading': 104, 'alignment': 'center', 'fill': [0.95, 0.97, 1], 'ranges': [{'start': 0, 'end': 5, 'fill': [0.294, 0.863, 1], 'font_size': 92}]})
                subtitle = await call('layer_create', base | {'layer': {'name': 'Brand subtitle', 'kind': 'text', 'text': 'Identidade em movimento.\nDireção, forma e precisão.', 'text_box': [1200, 170], 'font_size': 34, 'position': [960, 650]}})
                subtitle_id = subtitle['data']['layer_id']
                styled = await call('text_style_set', base | {'layer_id': subtitle_id, 'font': regular, 'font_size': 32, 'leading': 42, 'alignment': 'center', 'fill': [0.7, 0.79, 0.85]})
                text = next(l for l in styled['data']['compositions'][0]['layers'] if l['layer_id'].endswith(subtitle_id))
                assert text['text_style']['box_text'] and not text['text_style']['box_overflow']
                overflow = await call('layer_create', base | {'layer': {'name': 'Overflow fixture', 'text': 'Texto longo com acentos: ação, direção e precisão. ' * 6, 'text_box': [160, 30], 'font_size': 32}})
                overflow_id = overflow['data']['layer_id']
                await call('text_style_set', base | {'layer_id': overflow_id, 'leading': 40}, blocked=True)
                report = await call('text_style_set', base | {'layer_id': overflow_id, 'leading': 40, 'recenter_anchor': False, 'overflow_policy': 'report'})
                over = next(l for l in report['data']['compositions'][0]['layers'] if l['layer_id'].endswith(overflow_id))
                assert over['text_style']['box_overflow']
                await call('layer_remove', base | {'layer_id': overflow_id})
                logo = await call('layer_create', base | {'layer': {'name': 'Editable SVG mark', 'kind': 'shape', 'shape': 'empty', 'position': [960, 220]}})
                logo_id = logo['data']['layer_id']
                vector = await call('vector_import', base | {'layer_id': logo_id, 'source_path': str(asset), 'scale': 1.3})
                assert vector['data']['vector_asset']['editable_native_paths']
                assert Path(vector['data']['vector_asset']['path']).read_bytes() == asset.read_bytes()
                line = await call('layer_create', base | {'layer': {'name': 'Bezier accent', 'kind': 'shape', 'shape': 'empty', 'position': [960, 850]}})
                line_id = line['data']['layer_id']
                path = {'vertices': [[-180, 0], [0, -65], [180, 0]], 'in_tangents': [[0, 0], [-80, 0], [0, 0]], 'out_tangents': [[0, 0], [80, 0], [0, 0]], 'closed': False}
                shape = await call('shape_path_set', base | {'layer_id': line_id, 'path': path, 'name': 'Brand arc'})
                group = shape['data']['created_group_id']
                group_target = base | {'layer_id': line_id, 'group_id': group}
                await call('shape_style_set', group_target | {'stroke': [0.294, 0.863, 1], 'stroke_width': 8, 'fill_enabled': False})
                await call('shape_style_set', group_target | {'gradient': [[1, 0, 0], [0, 0, 1]]}, blocked=True)
                await call('shape_morph_apply', group_target | {'end_path': {'vertices': [[0, 0], [1, 1]]}}, blocked=True)
                end = path | {'vertices': [[-180, 0], [0, -30], [180, 0]]}
                await call('shape_morph_apply', group_target | {'end_path': end, 'start_time': 0.3, 'duration': 1.1})
                await call('shape_trim_apply', group_target | {'start_time': 0.2, 'duration': 1.3})
                await call('text_animator_apply', base | {'layer_id': title, 'based_on': 'words', 'position': [0, 30], 'scale': 96, 'opacity': 0, 'start_time': 0.2, 'duration': 1})
                await call('text_animator_apply', base | {'layer_id': subtitle_id, 'based_on': 'characters', 'position': [0, 12], 'start_time': 0.4, 'duration': 1.1})
                bg = await call('layer_create', base | {'layer': {'name': 'Brand background', 'kind': 'solid', 'size': [1920, 1080], 'color': [0.015, 0.025, 0.05], 'position': [960, 540]}})
                bg_id = bg['data']['layer_id']
                await call('layer_update', base | {'layer_id': bg_id, 'after_layer_id': title})
                # Original title is the bottom content layer; background now sits below it.
                tokens = await call('design_tokens_set', {'name': 'Astra Brand', 'colors': {'foreground': [0.7, 0.79, 0.85], 'accent': [0.294, 0.863, 1]}, 'typography': {'body': {'font': regular, 'size_ratio': 0.02963, 'tracking': 0, 'color': 'foreground'}}, 'spacing_ratio': 0.025, 'safe_area': [0.08, 0.08, 0.08, 0.08]})
                bindings = [{'layer_id': bg_id, 'role': 'background'}, {'layer_id': logo_id, 'x': 0.5, 'y': 0.22, 'max_width': 0.24, 'max_height': 0.25}, {'layer_id': title, 'x': 0.5, 'y': 0.44, 'max_width': 0.8, 'max_height': 0.14}, {'layer_id': subtitle_id, 'x': 0.5, 'y': 0.64, 'max_width': 0.8, 'max_height': 0.16, 'typography_token': 'body'}, {'layer_id': line_id, 'x': 0.5, 'y': 0.81, 'max_width': 0.65, 'max_height': 0.12}]
                layout = base | {'token_id': tokens['token_id'], 'profile': 'landscape', 'bindings': bindings}
                square = await call('layout_apply', layout | {'profile': 'square'})
                assert square['data']['compositions'][0]['width'] == square['data']['compositions'][0]['height'] == 1080
                compact = [dict(b) if b.get('role') == 'background' else dict(b, max_width=0.15) for b in bindings]
                await call('layout_apply', layout | {'bindings': compact, 'arrangement': 'distribute_horizontal'})
                for arrangement in ('align_left', 'align_right', 'align_center', 'distribute_vertical', 'bindings'):
                    landscape = await call('layout_apply', layout | {'arrangement': arrangement})
                async def render(width):
                    preview = await call('preview_render', base | {'duration': 3, 'max_width': width})
                    deadline = time.monotonic() + 300
                    while time.monotonic() < deadline:
                        response = await session.call_tool('job_status', {'operation_id': preview['job_id']})
                        result = response.structuredContent
                        if result['status'] not in ('queued', 'running', 'prepared'): break
                        await asyncio.sleep(2)
                    assert result['status'] == 'succeeded', result
                    return result['result']['data']
                landscape_preview = await render(960)
                portrait = await call('layout_apply', layout | {'profile': 'portrait'})
                portrait_preview = await render(540)
                for value in (landscape, portrait):
                    for layer in value['data']['compositions'][0]['layers']:
                        if layer['text']:
                            assert not layer['text_style']['box_overflow'] and not layer['text_style']['font_missing']
                assert portrait_preview['verification']['height'] == 960
                for path, expected in versions.items(): assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
                assert hashlib.sha256(asset.read_bytes()).hexdigest() == asset_hash
                evidence = {'project_id': project, 'composition_id': comp, 'landscape_aep': landscape['project_path'], 'portrait_aep': portrait['project_path'], 'landscape_preview': landscape_preview, 'portrait_preview': portrait_preview, 'preserved_versions': len(versions), 'tokens': tokens, 'source_svg': str(asset)}
                settings.contained_path('sprint7-acceptance.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                print(json.dumps(evidence, indent=2))
    asyncio.run(asyncio.wait_for(exercise(), timeout=1000))
