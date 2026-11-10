"""Opt-in: create an ordinary multi-layer AEP, open a copy and edit only a target."""
import asyncio
import copy
import hashlib
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.ae_bridge.templates import render_script
from astra_video_studio.config import Settings
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import ProjectCreateRequest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get("ASTRA_RUN_AE_TESTS") != "1", reason="Opt-in existing-project AE test")
def test_existing_project_copy_selective_edit_and_explicit_save():
    settings = Settings.from_env()
    fixture_dir = settings.contained_path("fixtures/" + uuid4().hex)
    fixture_dir.mkdir(parents=True, exist_ok=False)
    source = fixture_dir / "client-source.aep"
    fixture_code = '''
            comp.comment = 'Client composition notes';
            title.name = 'Repeated layer name'; title.comment = 'Original client title comment';
            var sentinel = comp.layers.addText('KEEP THIS UNCHANGED');
            sentinel.name = 'Repeated layer name'; sentinel.comment = 'Preserve this comment';
            sentinel.property('ADBE Transform Group').property('ADBE Opacity').setValue(37);
            sentinel.locked = true;
            var secondary = project.items.addComp('Secondary client composition', 1280, 720, 1, 5, 30);
            secondary.comment = 'Other composition notes';
            var secondaryText = secondary.layers.addText('SECONDARY MUST NOT CHANGE');
            secondaryText.comment = 'Other layer notes';
            secondary.layers.addCamera('Review Camera', [640, 360]);
'''
    def fixture_template(action, payload):
        return render_script(action, payload).replace("            project.save(target);", fixture_code + "\n            project.save(target);", 1)
    with patch("astra_video_studio.ae_bridge.runner.render_script", side_effect=fixture_template):
        made = BridgeRunner(settings).run("create", {"request": ProjectCreateRequest(name="Client source", title="CLIENT TITLE").model_dump(), "project_path": source.as_posix(), "composition_id": uuid4().hex, "layer_id": uuid4().hex, "managed_paths": ProjectManager(settings).managed_paths()})
    assert made.status == "succeeded", made.model_dump()
    source_bytes = source.read_bytes()
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
                opened = await call("project_open_copy", {"request": {"source_path": str(source)}})
                assert Path(opened["project_path"]).read_bytes() == source_bytes
                assert Path(opened["data"]["backup_path"]).read_bytes() == source_bytes
                baseline = opened["data"]["compositions"]
                assert len(baseline) == 2 and len(baseline[0]["layers"]) == 2
                assert baseline[0]["comment"] == 'Client composition notes'
                comp = baseline[0]
                target = next(l for l in comp["layers"] if l["text"] == "CLIENT TITLE")
                locked = next(l for l in comp["layers"] if l["text"] == "KEEP THIS UNCHANGED")
                assert locked["locked"]
                ids = {"project_id": opened["project_id"], "composition_id": comp["composition_id"].split(":")[-1], "layer_id": target["layer_id"].split(":")[-1]}
                blocked = await session.call_tool("layer_transform", {"request": ids | {"layer_id": locked["layer_id"].split(":")[-1], "values": {"opacity": 0}}})
                assert blocked.isError
                edited = await call("layer_transform", {"request": ids | {"values": {"opacity": 55, "rotation": 8}}})
                current = edited["data"]["compositions"]
                assert current[1] == baseline[1]
                assert next(l for l in current[0]["layers"] if l["layer_id"] == locked["layer_id"]) == locked
                changed = next(l for l in current[0]["layers"] if l["layer_id"] == target["layer_id"])
                assert changed["transforms"]["opacity"]["value"] == 55 and changed["transforms"]["rotation"]["value"] == 8
                assert changed["comment"] == target["comment"]
                assert source.read_bytes() == source_bytes and Path(opened["project_path"]).read_bytes() == source_bytes
                edited_hash = hashlib.sha256(Path(edited["project_path"]).read_bytes()).hexdigest()
                # Simulate explicit manual edits ONLY in this throwaway managed copy.
                # This trusted fixture injection is not available through a product tool.
                snippet = '''
        var manualComp = app.project.item(1);
        var originalTitle = null;
        for (var mi = 1; mi <= manualComp.numLayers; mi++) {
            if (manualComp.layer(mi).id === __TARGET_NATIVE__) { originalTitle = manualComp.layer(mi); }
        }
        if (!originalTitle) { throw new Error('Fixture target missing'); }
        originalTitle.name = 'Manually revised title';
        originalTitle.duplicate().name = 'Manual duplicate';
'''.replace("__TARGET_NATIVE__", str(target["ae_id"]))
                def manual_template(action, payload):
                    marker = '        /*ASTRA_RESULT_COLLECTION*/'
                    script = render_script(action, payload)
                    assert script.count(marker) == 1, 'Manual fixture insertion point missing/ambiguous'
                    return script.replace(marker, snippet + "\n" + marker, 1)
                manifest, active = ProjectManager(settings).load(ids["project_id"])
                with patch("astra_video_studio.ae_bridge.runner.render_script", side_effect=manual_template):
                    manual = BridgeRunner(settings).run("inspect", {"project_path": active.as_posix(), "id_map": manifest["id_map"]})
                assert manual.status == "succeeded" and manual.data["project_dirty"]
                saved = await call("project_save", {"project_id": ids["project_id"]})
                assert len(saved["data"]["compositions"][0]["layers"]) == 3
                saved_target = next(l for l in saved["data"]["compositions"][0]["layers"] if l["layer_id"] == target["layer_id"])
                assert saved_target["name"] == 'Manually revised title'
                assert len({l["layer_id"] for l in saved["data"]["compositions"][0]["layers"]}) == 3
                assert hashlib.sha256(Path(edited["project_path"]).read_bytes()).hexdigest() == edited_hash
                assert source.read_bytes() == source_bytes
                inspected = await call("composition_inspect", {"project_id": ids["project_id"]})
                assert inspected["data"]["compositions"] == saved["data"]["compositions"]
                print(f"source_path={source}\nproject_id={ids['project_id']}\nproject_path={saved['project_path']}")
    asyncio.run(asyncio.wait_for(exercise(), timeout=360))
