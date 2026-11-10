"""Opt-in: creates TWO new AEPs, reopens each, and leaves the second in AE."""
import hashlib
import os
import asyncio
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from astra_video_studio.config import Settings
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import ProjectCreateRequest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get("ASTRA_RUN_AE_TESTS") != "1", reason="Opt-in AE integration; set ASTRA_RUN_AE_TESTS=1")
def test_create_reopen_inspect_and_repeat_without_overwrite(monkeypatch):
    from pathlib import Path
    manager = ProjectManager(Settings.from_env())
    request = ProjectCreateRequest()
    first = manager.create(request)
    assert first.status == "succeeded", first.model_dump()
    first_bytes = Path(first.project_path).read_bytes()
    assert len(first_bytes) > 64
    inspected = manager.inspect(first.project_id)
    assert inspected.status == "succeeded", inspected.model_dump()
    assert inspected.data["compositions"][0]["layers"][0]["text"] == request.title
    second = manager.create(request)
    assert second.status == "succeeded", second.model_dump()
    assert first.project_path != second.project_path
    assert hashlib.sha256(first_bytes).digest() == hashlib.sha256(Path(first.project_path).read_bytes()).digest()
    second_inspected = manager.inspect(second.project_id)
    assert second_inspected.status == "succeeded", second_inspected.model_dump()
    assert second_inspected.data["compositions"][0]["layers"][0]["layer_id"] != inspected.data["compositions"][0]["layers"][0]["layer_id"]
    second_hash = hashlib.sha256(Path(second.project_path).read_bytes()).digest()
    # Treat the currently open project as untracked: the AE-side guard must refuse
    # replacement without changing its saved file or creating another AEP.
    monkeypatch.setattr(manager, "managed_paths", lambda: [])
    rejected = manager.create(request)
    assert rejected.status == "failed"
    assert "ACTIVE_PROJECT_PROTECTED" in rejected.error
    assert not Path(rejected.project_path).exists()
    assert hashlib.sha256(Path(second.project_path).read_bytes()).digest() == second_hash


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get("ASTRA_RUN_AE_TESTS") != "1", reason="Opt-in AE integration; set ASTRA_RUN_AE_TESTS=1")
def test_live_creation_through_mcp_stdio():
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "astra_video_studio.mcp_server"], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                created = await session.call_tool("project_create", {"request": {"name": "Astra Sprint 1", "title": "ASTRA VIDEO STUDIO"}})
                assert not created.isError
                result = created.structuredContent
                assert result["status"] == "succeeded", result
                inspected = await session.call_tool("composition_inspect", {"project_id": result["project_id"]})
                assert not inspected.isError
                assert inspected.structuredContent["status"] == "succeeded"
                assert inspected.structuredContent["data"]["compositions"][0]["layers"][0]["position"][:2] == [960, 540]
                journal = await session.call_tool("job_status", {"operation_id": result["operation_id"]})
                assert not journal.isError
                assert journal.structuredContent["status"] == "succeeded"
    asyncio.run(asyncio.wait_for(exercise(), timeout=150))
