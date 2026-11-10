"""Opt-in native effects/masks + aerender/FFmpeg preview through MCP."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get("ASTRA_RUN_AE_TESTS") != "1", reason="Opt-in native rendering test")
def test_effects_masks_and_decodable_mp4_through_mcp():
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "astra_video_studio.mcp_server"], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                async def call(name, arguments):
                    response = await session.call_tool(name, arguments)
                    assert not response.isError, response.content
                    return response.structuredContent
                async def edit(name, request):
                    result = await call(name, {"request": request})
                    assert result["status"] == "succeeded", result
                    return result
                created = await edit("project_create", {"name": "Astra Preview - Sprint 4", "width": 960, "height": 540, "fps": 24, "duration": 3, "font_size": 52})
                comp = created["data"]["compositions"][0]
                layer = comp["layers"][0]
                ids = {"project_id": created["project_id"], "composition_id": comp["composition_id"].split(":")[-1], "layer_id": layer["layer_id"].split(":")[-1]}
                original = Path(created["project_path"]).read_bytes()
                await edit("effect_apply", ids | {"effect": "fill", "params": {"color": [0.3, 0.85, 1]}})
                blurred = await edit("effect_apply", ids | {"effect": "gaussian_blur", "params": {"amount": 0.8, "repeat_edges": True}})
                assert len(blurred["data"]["compositions"][0]["layers"][0]["effects"]) == 2
                bounds = layer["bounds"]
                await edit("mask_create", ids | {"bounds": [bounds["left"] - 30, bounds["top"] - 30, bounds["width"] + 60, bounds["height"] + 60], "feather": 2})
                masked = await edit("mask_create", ids | {"shape": "ellipse", "bounds": [bounds["left"] - 200, bounds["top"] - 200, 40, 40], "mode": "subtract"})
                assert len(masked["data"]["compositions"][0]["layers"][0]["masks"]) == 2
                await edit("motion_apply", ids | {"skill": "slide_in", "start_time": 0.2, "duration": 0.7, "params": {"distance_px": 180, "overshoot": 0.04}})
                animated = await edit("motion_apply", ids | {"skill": "fade_in_out", "duration": 3, "params": {"fade_in": 0.5, "fade_out": 0.5}})
                saved_hash = hashlib.sha256(Path(animated["project_path"]).read_bytes()).hexdigest()
                queued = await call("preview_render", {"request": {"project_id": ids["project_id"], "composition_id": ids["composition_id"], "duration": 3, "max_width": 960}})
                assert queued["status"] == "queued"
                deadline = time.monotonic() + 420
                while time.monotonic() < deadline:
                    state = await call("job_status", {"operation_id": queued["job_id"]})
                    if state["status"] not in ("prepared", "queued", "running"):
                        break
                    await asyncio.sleep(1)
                assert state["status"] == "succeeded", state
                result = state["result"]
                data = result["data"]
                assert data["verification"]["frame_count"] == 72
                assert data["verification"]["duration"] == pytest.approx(3, abs=0.05)
                assert all(Path(p).is_file() for p in [data["video_path"], *data["samples"]])
                assert hashlib.sha256(Path(animated["project_path"]).read_bytes()).hexdigest() == saved_hash
                assert Path(created["project_path"]).read_bytes() == original
                restored = await call("composition_inspect", {"project_id": ids["project_id"]})
                assert restored["status"] == "succeeded" and restored["project_path"] == animated["project_path"]
                print(f"project_id={ids['project_id']}\nproject_path={animated['project_path']}\npreview_job={queued['job_id']}\npreview_path={data['video_path']}")
    asyncio.run(asyncio.wait_for(exercise(), timeout=600))
