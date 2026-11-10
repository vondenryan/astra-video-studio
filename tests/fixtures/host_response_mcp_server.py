"""Only this test subprocess replaces the three reviewed services. Never runs AE."""
import json

from astra_video_studio import mcp_server
from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.jobs import Job
from astra_video_studio.schemas import OperationResult


def forbidden(*args, **kwargs):
    raise AssertionError('Native execution is forbidden in host presentation fixtures')


def result(service, action):
    data = json.loads(service.settings.contained_path('host-fixture.json').read_text(encoding='utf-8'))
    job = Job(service.settings, 'fixture_' + action)
    value = OperationResult(operation_id=job.id, status='succeeded', project_id='3'*32, data=data)
    job.record('succeeded', result=value.model_dump(mode='json'))
    return value


def layer_create(self, request):
    return result(self, 'layer_create')


def text_style(self, action, request):
    assert action == 'text_style_set'
    return result(self, action)


def motion_apply(self, request):
    return result(self, 'motion_apply')


BridgeRunner.run = forbidden
mcp_server.LayerService.create = layer_create
mcp_server.DesignService.apply = text_style
mcp_server.MotionService.apply = motion_apply
mcp_server.main()
