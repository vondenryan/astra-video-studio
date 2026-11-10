"""Test-only service fixture behind the real production MCP presentation layer.

Never imports/discovers/launches AE, submits JSX or renders a video.
"""
import json
from astra_video_studio import mcp_server
from astra_video_studio.jobs import Job
from astra_video_studio.schemas import OperationResult


def fixture_create(self, request):
    fixtures = json.loads(self.settings.contained_path('fixtures.json').read_text(encoding='utf-8'))
    failed = request.title == 'failure'
    data = fixtures['40' if failed else request.title]
    job = Job(self.settings, 'fixture_only')
    result = OperationResult(operation_id=job.id, status='failed' if failed else 'succeeded',
        project_id='3'*32, data=data, error='fixture diagnostic ' * 1000 if failed else None)
    job.record(result.status, result=result.model_dump())
    return result


mcp_server.ProjectManager.create = fixture_create
mcp_server.main()
