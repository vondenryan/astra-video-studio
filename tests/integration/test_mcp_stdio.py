import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest


@pytest.mark.integration
def test_real_stdio_handshake_tool_schema_and_call(tmp_path):
    async def exercise():
        env = dict(os.environ, ASTRA_WORKSPACE=str(tmp_path))
        params = StdioServerParameters(command=sys.executable, args=["-m", "astra_video_studio.mcp_server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "Astra Video Studio"
                listing = await session.list_tools()
                assert {tool.name for tool in listing.tools} == {"studio_status", "project_create", "composition_inspect", "job_status", "layer_transform", "motion_apply", "project_open_copy", "project_save", "effect_apply", "mask_create", "preview_render", "job_cancel", "layer_create", "media_import", "stagger_layers", "motion_batch", "scene_plan", "scene_execute", "scene_status", "scene_revise", "visual_review", "reference_analyze", "composition_create", "composition_update", "precompose_layers", "composition_layer_add", "null_create", "layer_duplicate", "layer_update", "layer_remove", "layer_parent", "track_matte_set", "fonts_list", "text_style_set", "text_animator_apply", "shape_path_set", "shape_style_set", "shape_trim_apply", "shape_morph_apply", "vector_import", "design_tokens_set", "layout_apply", "animation_inspect", "keyframes_edit", "easing_set", "motion_path_set", "animation_retime", "motion_blur_set", "revision_plan", "revision_apply", "version_compare", "version_restore", "director_revision_plan", "operation_query", "project_query", "audio_inspect", "audio_clip_set", "audio_markers_create", "timeline_markers_set", "audio_sync_plan", "audio_preview_render", "render_presets_list", "render_submit", "delivery_collect", "delivery_validate", "brief_validate", "storyboard_plan", "storyboard_execute", "storyboard_status", "storyboard_revise", "review_samples_create", "storyboard_review", "queue_inspect", "job_reconcile", "project_dependencies", "workspace_cleanup_plan", "layers_create"}
                assert listing.tools[0].outputSchema
                assert all(tool.outputSchema for tool in listing.tools)
                result = await session.call_tool("studio_status", {})
                assert not result.isError
                assert result.structuredContent["bridge_status"] == "not_validated"
                assert result.structuredContent["workspace"]["writable"]
                assert result.structuredContent["operation_id"]
                runtime = result.structuredContent['mcp_runtime']
                assert runtime['presentation_policy'] == '9.3'
                assert runtime['pid'] > 0 and len(runtime['startup_source_sha256']) == 64
                assert runtime['python_executable'] == sys.executable
                invalid = await session.call_tool("project_create", {"request": {"width": 0}})
                assert invalid.isError
                assert not (tmp_path / "jobs").exists()
                for tool, request in (
                    ('composition_update', {'project_id': '0' * 32, 'composition_id': '1' * 32, 'fps': 30}),
                    ('layer_parent', {'project_id': '0' * 32, 'composition_id': '1' * 32, 'layer_id': '2' * 32, 'policy': 'guess'}),
                    ('track_matte_set', {'project_id': '0' * 32, 'composition_id': '1' * 32, 'layer_id': '2' * 32, 'mode': 'alpha'}),
                ):
                    rejected = await session.call_tool(tool, {'request': request})
                    assert rejected.isError
                assert not (tmp_path / 'jobs').exists()
                unknown = await session.call_tool("job_status", {"operation_id": "0" * 32})
                assert unknown.isError
    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
