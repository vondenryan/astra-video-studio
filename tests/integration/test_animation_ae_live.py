"""Sprint 8: guarded entry refinement, curved trajectory, retime and preserved exit."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.config import Settings
from astra_video_studio.media.ffmpeg import inspect_binary


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS') != '1', reason='Opt-in guarded native animation editor')
def test_entry_curve_retime_and_preserved_exit():
    settings = Settings.from_env()
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'astra_video_studio.mcp_server'], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                versions = {}
                async def call(name, payload, blocked=False, wrapped=True):
                    result = await session.call_tool(name, {'request': payload} if wrapped else payload)
                    if blocked:
                        assert result.isError or result.structuredContent['status'] in ('failed', 'blocked'), result
                        return result
                    assert not result.isError, result.content
                    data = result.structuredContent
                    assert data['status'] in (('succeeded', 'queued', 'running', 'prepared') if name == 'job_status' else ('succeeded', 'queued')), data
                    if data.get('project_path'):
                        p = Path(data['project_path']); versions[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
                    return data
                created = await call('project_create', {'name': 'Astra — Editor de Curvas', 'title': 'CURVAS EDITÁVEIS', 'width': 960, 'height': 540, 'fps': 24, 'duration': 5, 'font_size': 60})
                base = {'project_id': created['project_id'], 'composition_id': created['data']['compositions'][0]['composition_id'].split(':')[-1]}
                title = created['data']['compositions'][0]['layers'][0]['layer_id'].split(':')[-1]
                target = base | {'layer_id': title}
                sentinel = await call('layer_create', base | {'layer': {'name': 'Sentinel untouched', 'text': 'CAMADA PRESERVADA', 'font_size': 24, 'color': [0.4, 0.5, 0.6], 'position': [480, 440]}})
                sentinel_id = sentinel['data']['layer_id']
                probes = []
                for number in (1, 2):
                    probe = await call('layer_create', base | {'layer': {'name': f'Anticipation fixture {number}', 'text': 'ANTECIPAÇÃO', 'font_size': 20, 'position': [480, 100 + number * 40]}})
                    probes.append(probe['data']['layer_id'])
                await call('stagger_layers', base | {'layer_ids': probes, 'skill': 'anticipate_settle', 'duration': 1.5, 'interval': 0.2, 'params': {'distance_px': 120, 'anticipation_ratio': 0.08, 'overshoot': 0.05}})
                for identifier in probes:
                    await call('layer_remove', base | {'layer_id': identifier})
                await call('motion_batch', {'motions': [target | {'skill': 'slide_in', 'duration': 1, 'params': {'distance_px': 280, 'overshoot': 0}}, target | {'skill': 'scale_pop', 'duration': 1, 'params': {'initial_scale': 90, 'overshoot': 0.03}}, target | {'skill': 'fade_in_out', 'duration': 5, 'params': {'fade_in': 0.5, 'fade_out': 1}}]})
                async def inspect():
                    return await call('animation_inspect', base | {'layer_ids': [title, sentinel_id], 'sample_times': [0.5, 1, 2, 4.5]})
                def track(state, name, identifier=title):
                    return next(t for t in state['data']['animation_state']['tracks'] if t['property'] == name and t['layer_id'] == identifier)
                def guard(state, name, a=0, b=24, policy='preserve_boundaries'):
                    return target | {'property': name, 'base_sha256': state['data']['animation_state']['base_sha256'], 'expected_track_sha256': track(state, name)['track_sha256'], 'start_frame': a, 'end_frame': b, 'boundary_policy': policy}
                state = await inspect()
                await call('keyframes_edit', guard(state, 'position', 96, 120, 'allow_change') | {'mode': 'insert', 'keys': [{'frame': 96, 'value': [480, 270]}, {'frame': 120, 'value': [760, 270]}]})
                baseline = await inspect(); stale_hash = track(baseline, 'position')['track_sha256']
                await call('keyframes_edit', guard(baseline, 'position') | {'base_sha256': '0' * 64, 'mode': 'update', 'keys': [{'frame': 0, 'value': [200, 270]}]}, blocked=True)
                baseline_comp = copy.deepcopy(baseline['data']['compositions'][0])
                exit_keys = copy.deepcopy(track(baseline, 'position')['track']['keys'][-2:])
                async def render():
                    submission = await call('preview_render', base | {'duration': 5, 'max_width': 960})
                    deadline = time.monotonic() + 300
                    while time.monotonic() < deadline:
                        job = await call('job_status', {'operation_id': submission['job_id']}, wrapped=False)
                        if job['status'] not in ('queued', 'running', 'prepared'): return job['result']['data']
                        await asyncio.sleep(2)
                    pytest.fail('Preview timed out')
                before_preview = await render()
                await call('keyframes_edit', guard(baseline, 'position') | {'mode': 'update', 'keys': [{'frame': 0, 'value': [210, 270]}]}, blocked=True)
                # Exercise insert/update/move/remove/replace on a separate title property.
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 0, 48, 'allow_change') | {'mode': 'insert', 'keys': [{'frame': 0, 'value': [0]}, {'frame': 48, 'value': [0]}]})
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 0, 48) | {'mode': 'insert', 'keys': [{'frame': 24, 'value': [4]}]})
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 0, 48) | {'mode': 'update', 'keys': [{'frame': 24, 'value': [5]}]})
                state = await inspect()
                await call('easing_set', guard(state, 'rotation', 0, 48) | {'edits': [{'frame': 0, 'out_type': 'hold'}, {'frame': 24, 'in_type': 'hold', 'out_type': 'hold'}]})
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 24, 25, 'allow_change') | {'mode': 'move', 'shift_frames': 6})
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 30, 31, 'allow_change') | {'mode': 'remove'})
                state = await inspect()
                await call('keyframes_edit', guard(state, 'rotation', 0, 48) | {'mode': 'replace', 'keys': [{'frame': 0, 'value': [0]}, {'frame': 48, 'value': [0]}]})
                state = await inspect()
                await call('easing_set', guard(state, 'position') | {'edits': [{'frame': 0, 'out_ease': [{'speed': 400, 'influence': 50}]}, {'frame': 24, 'in_ease': [{'speed': 0, 'influence': 50}]}]})
                state = await inspect()
                await call('easing_set', guard(state, 'position') | {'expected_track_sha256': stale_hash, 'edits': [{'frame': 0, 'out_type': 'linear'}]}, blocked=True)
                await call('motion_path_set', guard(state, 'position') | {'edits': [{'frame': 0, 'out_tangent': [80, -150]}, {'frame': 24, 'in_tangent': [-80, -150]}]})
                curved = await inspect()
                curve_sample = next(s['value'] for s in track(curved, 'position')['track']['samples'] if s['time'] == 0.5)
                assert curve_sample[1] < 260
                def retime(state, start=0, duration=48):
                    return base | {'base_sha256': state['data']['animation_state']['base_sha256'], 'start_frame': 0, 'end_frame': 24, 'boundary_policy': 'allow_change', 'new_start_frame': start, 'new_duration_frames': duration, 'rounding': 'nearest', 'duration_policy': 'preserve_composition', 'targets': [{'layer_id': title, 'property': name, 'expected_track_sha256': track(state, name)['track_sha256']} for name in ('position', 'scale')]}
                await call('animation_retime', retime(curved, 96, 24), blocked=True)
                await call('animation_retime', retime(curved))
                retimed = await inspect()
                moved_sample = next(s['value'] for s in track(retimed, 'position')['track']['samples'] if s['time'] == 1)
                assert moved_sample == pytest.approx(curve_sample, abs=0.2)
                for mode in (True, False):
                    state = await inspect()
                    q = base | {'base_sha256': state['data']['animation_state']['base_sha256'], 'expected_composition_sha256': state['data']['animation_state']['composition_sha256'], 'layer_ids': [title], 'composition_enabled': True, 'layers_enabled': True,
                        'shutter_angle': 270 if mode else baseline_comp['shutter_angle'], 'shutter_phase': -135 if mode else baseline_comp['shutter_phase'],
                        'samples_per_frame': 24 if mode else baseline_comp['blur_samples'], 'adaptive_sample_limit': 64 if mode else baseline_comp['blur_adaptive_limit']}
                    await call('motion_blur_set', q)
                final = await inspect()
                assert track(final, 'position')['track']['keys'][-2:] == exit_keys
                for name in ('position', 'scale', 'rotation', 'opacity'):
                    old = track(baseline, name, sentinel_id)['track']; new = track(final, name, sentinel_id)['track']
                    assert new == old
                assert track(final, 'opacity')['track'] == track(baseline, 'opacity')['track']
                after_preview = await render()
                ffmpeg = inspect_binary('ffmpeg', settings.ffmpeg).path
                def frame_rgb(preview):
                    return subprocess.run([ffmpeg, '-v', 'error', '-i', preview['video_path'], '-ss', '4.5', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
                a, b = frame_rgb(before_preview), frame_rgb(after_preview)
                assert len(a) == len(b) == 960 * 540 * 3
                error = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
                assert error < 2, error
                for path, sha in versions.items(): assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
                evidence = {'project_id': base['project_id'], 'composition_id': base['composition_id'], 'project_path': final['project_path'], 'before_preview': before_preview, 'after_preview': after_preview, 'preserved_versions': len(versions), 'exit_rgb_mean_absolute_error': error, 'curve_sample_before_retime': curve_sample, 'curve_sample_after_retime': moved_sample, 'exit_keys_preserved': True}
                settings.contained_path('sprint8-acceptance.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    asyncio.run(asyncio.wait_for(exercise(), timeout=1000))
