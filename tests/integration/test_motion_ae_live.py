"""Opt-in Sprint 2 MCP → AE → save/reopen motion validation."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get("ASTRA_RUN_AE_TESTS") != "1", reason="Opt-in real AE motion test")
def test_ten_second_motion_saved_editable_through_mcp():
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "astra_video_studio.mcp_server"], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                async def call(name, arguments):
                    response = await session.call_tool(name, arguments)
                    assert not response.isError, response.content
                    result = response.structuredContent
                    assert result["status"] == "succeeded", result
                    return result
                created = await call("project_create", {"request": {"name": "Astra Motion - Sprint 2", "duration": 10}})
                comp = created["data"]["compositions"][0]
                layer = comp["layers"][0]
                target = {"project_id": created["project_id"], "composition_id": comp["composition_id"].split(":")[-1], "layer_id": layer["layer_id"].split(":")[-1]}
                protected = {created["project_path"]: hashlib.sha256(Path(created["project_path"]).read_bytes()).hexdigest()}
                transformed = await call("layer_transform", {"request": target | {"values": {"position": [960, 540], "anchor": layer["anchor"][:2], "scale": [100, 100], "rotation": 0, "opacity": 100}}})
                protected[transformed["project_path"]] = hashlib.sha256(Path(transformed["project_path"]).read_bytes()).hexdigest()
                motions = [
                    {"skill": "slide_in", "start_time": 0.3, "duration": 0.9, "params": {"distance_px": 420, "overshoot": 0.06}},
                    {"skill": "scale_pop", "start_time": 0.3, "duration": 0.9, "params": {"initial_scale": 82, "overshoot": 0.06}},
                    {"skill": "fade_in_out", "start_time": 0, "duration": 10, "params": {"fade_in": 0.6, "fade_out": 1}},
                    {"skill": "smooth_zoom", "start_time": 2, "duration": 6, "params": {"initial_scale": 100, "final_scale": 108}},
                ]
                for motion in motions:
                    result = await call("motion_apply", {"request": target | motion})
                    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in protected.items())
                    protected[result["project_path"]] = hashlib.sha256(Path(result["project_path"]).read_bytes()).hexdigest()
                    snapshot = Path(result["project_path"]).parent / "source-snapshot.aep"
                    assert snapshot.is_file()
                inspected = await call("composition_inspect", {"project_id": target["project_id"]})
                comp = inspected["data"]["compositions"][0]
                layer = comp["layers"][0]
                assert comp["duration"] == 10 and comp["motion_blur"] and layer["motion_blur"]
                transforms = layer["transforms"]
                assert len(transforms["position"]["keys"]) >= 3
                assert len(transforms["scale"]["keys"]) >= 6
                assert transforms["opacity"]["keys"][0]["value"] == 0
                assert transforms["opacity"]["keys"][-1]["value"] == 0
                assert any(s["value"] == 100 for s in transforms["opacity"]["samples"])
                assert not any(t["expression_enabled"] for t in transforms.values())
                # Reapplying overlapping motion must fail before producing a new version.
                rejected = await session.call_tool("motion_apply", {"request": target | motions[0]})
                assert rejected.isError
                rejected_static = await session.call_tool("layer_transform", {"request": target | {"values": {"opacity": 50}}})
                assert rejected_static.isError
                assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in protected.items())
                print(f"project_id={target['project_id']}\nproject_path={result['project_path']}")
    asyncio.run(asyncio.wait_for(exercise(), timeout=420))
