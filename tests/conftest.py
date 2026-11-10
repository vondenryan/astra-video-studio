"""Historical AE tests deliberately request legacy full host output.

Presentation/scalability tests separately exercise the default compact protocol.
No flag enables native testing; the existing explicit ASTRA_RUN_AE_TESTS gate stays.
"""
import inspect
import pytest


@pytest.fixture(autouse=True)
def legacy_native_protocol(request, monkeypatch):
    if not request.node.get_closest_marker('ae_live'): return
    from mcp import ClientSession
    from astra_video_studio import mcp_server
    original = ClientSession.call_tool
    async def call(self, name, arguments=None, *args, **kwargs):
        function = getattr(mcp_server, name, None)
        if function and 'response_mode' in inspect.signature(function).parameters:
            arguments = dict(arguments or {})
            arguments.setdefault('response_mode', 'full')
        return await original(self, name, arguments, *args, **kwargs)
    monkeypatch.setattr(ClientSession, 'call_tool', call)
